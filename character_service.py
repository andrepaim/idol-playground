"""Private opt-in character service. Registered stages are CPU-only for now."""
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading

from character_contracts import DEPENDENCIES, new_character
from character_executor import Adapter, StageExecutor
from character_input import InputSettings, AnatomySettings, inspect_image, checked_input, validate_input, validate_assessment, MAX_UPLOAD
from character_store import CharacterStore, CommitUncertain

PUBLIC_NAMES = {'input':{'original.bin','prepared.png','input.json'},'assessment':{'assessment.json'}}


class CharacterMissing(ValueError):
    pass


class CharacterConflict(ValueError):
    pass


class CharacterIntegrity(ValueError):
    pass


class InvalidImage(ValueError):
    pass


class CharacterService:
    def __init__(self,root,resource):
        if sys.platform!='linux' or not hasattr(os,'pidfd_open'):
            raise RuntimeError('Local character stages require Linux/WSL with pidfd support.')
        root=Path(root)
        root.parent.mkdir(parents=True,mode=0o700,exist_ok=True)
        self.store=CharacterStore(root)
        self._thread=threading.get_ident()
        self._claims={}
        self._blocked=False
        self._closed=False
        worker=Path(__file__).parent/'backends/characters/worker.py'
        def command(context):
            configuration={'parameters':context.parameters}
            if context.claim.stage=='input':
                request=self._request(context.claim.identifier)
                self.store.read_artifact(context.claim.identifier,request['original'],limit=MAX_UPLOAD)
                configuration.update(source=str(self.store.root/context.claim.identifier/request['original']['path']),sha256=request['sha256'])
            else:
                configuration['image']=str(context.inputs['input:prepared.png'])
            config=context.workspace/'_worker.json'
            descriptor=os.open(config,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
            with os.fdopen(descriptor,'w') as stream:
                json.dump(configuration,stream,sort_keys=True,allow_nan=False)
                stream.flush();os.fsync(stream.fileno())
            return [sys.executable,str(worker),context.claim.stage,str(config)]
        adapters={
            'input':Adapter('input',{'adapter':'local-image-v1'},('original.bin','prepared.png','input.json'),command,validate_input,contextual=True),
            'assessment':Adapter('assessment',{'adapter':'manual-anatomy-v1'},('assessment.json',),command,validate_assessment,contextual=True),
        }
        self.executor=StageExecutor(self.store,resource,adapters)

    @property
    def ready(self):
        return not (self._closed or self._blocked or self.executor._blocked)

    def _owner(self):
        if threading.get_ident()!=self._thread:
            raise RuntimeError('Character mutations must run on the persistent service thread.')
        if not self.ready:
            raise RuntimeError('Character service needs restart/reconciliation before new work.')

    def _record(self,identifier):
        new_character(identifier)
        try: record=self.store.load(identifier)
        except (OSError,ValueError) as error:
            raise CharacterIntegrity('Character metadata needs repair; files were preserved.') from error
        if record is None: raise CharacterMissing('Character not found.')
        return record

    def _request(self,identifier):
        self._record(identifier)
        try:
            value=json.loads(self.store._read_metadata(f'{identifier}/request.json'))
            if (not isinstance(value,dict) or set(value)!={'schema_version','id','sha256','original','image'}
                    or type(value['schema_version']) is not int or value['schema_version']!=1 or value['id']!=identifier
                    or not isinstance(value['sha256'],str) or not re.fullmatch('[0-9a-f]{64}',value['sha256'])
                    or value['sha256']!=value['original']['sha256']):
                raise ValueError('Invalid request identity.')
            probe=new_character(identifier);probe['stages']['input']['outputs']=[value['original']]
            from character_contracts import validate_character
            validate_character(probe)
            if (not isinstance(value['image'],dict) or set(value['image'])!={'width','height','format'}
                    or any(type(value['image'][key]) is not int or value['image'][key]<16 for key in ('width','height'))
                    or value['image']['width']*value['image']['height']>25_000_000 or value['image']['format'] not in ('PNG','JPEG','WEBP')):
                raise ValueError('Invalid request image metadata.')
            return value
        except (OSError,ValueError,TypeError,KeyError) as error:
            raise CharacterIntegrity('Upload identity needs repair; original files were preserved.') from error

    def create(self,identifier,data):
        try:
            return self._create(identifier,data)
        except CommitUncertain:
            self._blocked=True
            raise

    def _create(self,identifier,data):
        self._owner()
        new_character(identifier)
        try: info=inspect_image(data)
        except ValueError as error: raise InvalidImage(str(error)) from error
        digest=sha256(data).hexdigest()
        record=self.store.load(identifier)
        created=False
        if record is None:
            self.store.save(new_character(identifier),expected_revision=None)
        request_path=self.store.root/identifier/'request.json'
        if request_path.exists() or request_path.is_symlink():
            request=self._request(identifier)
            if request['sha256']!=digest:
                raise CharacterConflict('This request identity already belongs to another image. Start a new character.')
        else:
            if self._record(identifier)['stages']['input']['attempt']!=0:
                raise CharacterIntegrity('Request identity is missing; preserve and repair existing character files.')
            with tempfile.TemporaryDirectory(prefix='idol-character-upload-') as temporary:
                source=Path(temporary)/'original.bin';source.write_bytes(data)
                original=self.store.publish_artifacts(identifier,'input',1,source.parent,['original.bin'])[0]
            request={'schema_version':1,'id':identifier,'sha256':digest,'original':original,'image':info}
            try: self.store._atomic(request_path,json.dumps(request,sort_keys=True,allow_nan=False).encode())
            except CommitUncertain:
                self._blocked=True
                raise
            created=True
        record=self._record(identifier)
        if record['stages']['input']['attempt']==0:
            self.start(identifier,'input',InputSettings().model_dump(mode='json'))
        return self.status(identifier),created

    def start(self,identifier,stage,parameters):
        self._owner()
        self.poll()
        request=self._request(identifier)
        if stage=='input':
            parameters=checked_input(parameters,request['image'])
            names={};external={'upload':request['sha256']}
        elif stage=='assessment':
            parameters=AnatomySettings.model_validate(parameters).model_dump(mode='json')
            names={'input':['prepared.png']};external=None
        else:
            raise ValueError('This stage is not available in the local character workflow yet.')
        claim=self.executor.start(identifier,stage,parameters,names,external_inputs=external)
        if not claim.cached: self._claims[identifier]=claim
        return self.status(identifier)

    def poll(self):
        self._owner()
        for identifier,claim in list(self._claims.items()):
            try: self.executor.wait(claim,timeout=0)
            except subprocess.TimeoutExpired: continue
            except CommitUncertain:
                self._blocked=True
                raise
            except Exception:
                # Detailed worker logs remain private. Persisted state and safe
                # validator codes, rather than raw exceptions, explain failure.
                try: state=self._record(identifier)['stages'][claim.stage]['state']
                except Exception:
                    self._blocked=True
                    raise RuntimeError('Worker metadata needs reconciliation.') from None
                if state=='running':
                    self._blocked=True
                    raise RuntimeError('Worker completion needs reconciliation.') from None
            self._claims.pop(identifier,None)

    def cancel(self,identifier):
        self._owner()
        self._record(identifier)
        claim=self._claims.get(identifier)
        if claim is None: raise CharacterConflict('This character has no active stage to cancel.')
        self.executor.cancel(claim)
        self._claims.pop(identifier,None)
        return self.status(identifier)

    def status(self,identifier):
        record=self._record(identifier)
        original=None
        try: original=self._request(identifier)['original']
        except CharacterIntegrity: pass
        stages={}
        for name,stage in record['stages'].items():
            artifacts=[]
            for artifact in stage['outputs']:
                filename=Path(artifact['path']).name
                if filename in PUBLIC_NAMES.get(name,set()):
                    artifacts.append({'name':filename,'bytes':artifact['bytes'],
                                      'url':f'/api/characters/{identifier}/artifacts/{name}/{filename}'})
            if name=='input' and original is not None and not any(item['name']=='original.bin' for item in artifacts):
                artifacts.append({'name':'original.bin','bytes':original['bytes'],
                                  'url':f'/api/characters/{identifier}/artifacts/input/original.bin'})
            stages[name]={'state':stage['state'],'attempt':stage['attempt'],'validation_passed':stage['validation_passed'],'artifacts':artifacts}
        return {'schema_version':1,'id':identifier,'revision':record['revision'],'ready':self.ready,
                'available_stages':['input','assessment'],'stages':stages}

    def list(self):
        characters=[]
        for path in sorted(self.store.root.iterdir()):
            if not re.fullmatch('[0-9a-f]{32}',path.name): continue
            try: characters.append(self.status(path.name))
            except CharacterMissing: continue
            except CharacterIntegrity: characters.append({'id':path.name,'error':'corrupt_record'})
        return {'characters':characters}

    def artifact(self,identifier,stage,name):
        record=self._record(identifier)
        if stage not in DEPENDENCIES or name not in PUBLIC_NAMES.get(stage,set()):
            raise CharacterMissing('Artifact not found.')
        matches=[item for item in record['stages'][stage]['outputs'] if Path(item['path']).name==name]
        if stage=='input' and name=='original.bin' and not matches:
            matches=[self._request(identifier)['original']]
        if len(matches)!=1: raise CharacterMissing('Artifact not found.')
        try: return self.store.read_artifact(identifier,matches[0],limit=MAX_UPLOAD)
        except (OSError,ValueError) as error:
            raise CharacterIntegrity('Artifact bytes failed verification. Preserve the source and retry the affected stage.') from error

    def close(self):
        if self._closed: return
        if threading.get_ident()!=self._thread:
            raise RuntimeError('Close the character service on its owner thread.')
        self.executor.close()
        self._claims.clear();self._closed=True
