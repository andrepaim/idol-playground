"""Opt-in private authoring routes. All worker launches stay on the service loop."""
import asyncio
import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, Response

from character_coordinator import StageBlocked, StageBusy
from character_input import InputSettings, AnatomySettings, MAX_UPLOAD
from character_service import CharacterMissing, CharacterConflict, CharacterIntegrity, InvalidImage
from character_store import CommitUncertain
from worker_leases import ResourceBusy, OwnershipError


class CharacterUploadLimit:
    def __init__(self,app): self.app=app

    async def __call__(self,scope,receive,send):
        if scope['type']!='http' or not (scope['path']=='/api/characters' or scope['path'].startswith('/api/characters/')):
            return await self.app(scope,receive,send)
        async def private_send(message):
            if message['type']=='http.response.start':
                headers=list(message.get('headers',[]))
                present={key.lower() for key,_ in headers}
                for key,value in ((b'cache-control',b'no-store'),(b'x-content-type-options',b'nosniff')):
                    if key not in present: headers.append((key,value))
                message={**message,'headers':headers}
            await send(message)
        if scope['method']!='POST' or scope['path']!='/api/characters':
            return await self.app(scope,receive,private_send)
        total=0
        async def bounded_receive():
            nonlocal total
            message=await receive()
            if message['type']=='http.request':
                total+=len(message.get('body',b''))
                if total>MAX_UPLOAD+64*1024:
                    raise HTTPException(413,'Choose an image up to 20 MiB.')
            return message
        await self.app(scope,bounded_receive,private_send)


async def service(request: Request):
    value=getattr(request.app.state,'character_service',None)
    if value is None: raise HTTPException(404,'Character authoring is not enabled.')
    if request.url.hostname not in ('127.0.0.1','localhost','::1'):
        raise HTTPException(403,'Use the loopback host for local character authoring.')
    origin=request.headers.get('origin')
    if request.method not in ('GET','HEAD') and origin is not None and origin!=str(request.base_url).rstrip('/'):
        raise HTTPException(403,'Use the local application origin for character changes.')
    return value


def call(function,*args,**kwargs):
    try: return function(*args,**kwargs)
    except CharacterMissing: raise HTTPException(404,'Character or artifact not found.') from None
    except InvalidImage as error: raise HTTPException(422,str(error)) from None
    except (CharacterConflict,CharacterIntegrity,StageBlocked,StageBusy,ResourceBusy,OwnershipError) as error:
        raise HTTPException(409,str(error)) from None
    except CommitUncertain:
        raise HTTPException(503,'A disk commit needs reconciliation. Files were preserved; resolve storage and restart.') from None
    except (OSError,RuntimeError):
        raise HTTPException(503,'Character processing needs local storage or service recovery. Files were preserved.') from None
    except ValueError:
        raise HTTPException(422,'Check the character identity, image crop and supported review fields.') from None


router=APIRouter(prefix='/api/characters',tags=['characters'])


@router.post('')
async def create(request_id: str=Form(...,pattern='^[0-9a-f]{32}$'),image: UploadFile=File(...),authoring=Depends(service)):
    data=await image.read(MAX_UPLOAD+1)
    if len(data)>MAX_UPLOAD: raise HTTPException(413,'Choose an image up to 20 MiB.')
    record,created=call(authoring.create,request_id,data)
    return JSONResponse(record,status_code=202 if created else 200,headers={'Cache-Control':'no-store'})


@router.get('')
async def list_characters(authoring=Depends(service)):
    return call(authoring.list)


@router.get('/{identifier}')
async def status(identifier: str,authoring=Depends(service)):
    return call(authoring.status,identifier)


@router.post('/{identifier}/input',status_code=202)
async def review_input(identifier: str,settings: InputSettings,authoring=Depends(service)):
    return call(authoring.start,identifier,'input',settings.model_dump(mode='json'))


@router.post('/{identifier}/assessment',status_code=202)
async def review_anatomy(identifier: str,settings: AnatomySettings,authoring=Depends(service)):
    return call(authoring.start,identifier,'assessment',settings.model_dump(mode='json'))


@router.post('/{identifier}/stages/{stage}/retry',status_code=202)
async def retry(identifier: str,stage: str,settings: dict,authoring=Depends(service)):
    return call(authoring.start,identifier,stage,settings)


@router.post('/{identifier}/cancel',status_code=202)
async def cancel(identifier: str,authoring=Depends(service)):
    return call(authoring.cancel,identifier)


@router.get('/{identifier}/artifacts/{stage}/{name}')
async def artifact(identifier: str,stage: str,name: str,authoring=Depends(service)):
    data=call(authoring.artifact,identifier,stage,name)
    media='image/png' if name=='prepared.png' else 'application/json' if name.endswith('.json') else 'application/octet-stream'
    headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Content-Security-Policy':"default-src 'none'"}
    if name=='original.bin': headers['Content-Disposition']='attachment; filename="original.bin"'
    return Response(data,media_type=media,headers=headers)


async def monitor(authoring):
    while True:
        if authoring.ready:
            try: authoring.poll()
            except Exception:
                logging.error('Character completion needs reconciliation; original files preserved.')
        await asyncio.sleep(.1)
