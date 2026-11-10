import copy
import struct
import pytest
from test_mesh import textured_glb_fixture, glb


def rig_fixture():
    doc, binary = textured_glb_fixture()
    blob = bytearray(binary)
    def add(values, code, kind, components, count):
        while len(blob)%4:blob.append(0)
        begin=len(blob)
        for row in values:blob.extend(struct.pack('<'+code*components,*row))
        view=len(doc['bufferViews']);doc['bufferViews'].append({'buffer':0,'byteOffset':begin,'byteLength':len(blob)-begin})
        index=len(doc['accessors']);doc['accessors'].append({'bufferView':view,'componentType':{'f':5126,'H':5123}[code],'count':count,'type':kind})
        return index
    joints=add([(0,1,0,0)]*3,'H','VEC4',4,3)
    weights=add([(.5,.5,0,0)]*3,'f','VEC4',4,3)
    bind=add([(1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1)]*2,'f','MAT4',16,2)
    primitive=doc['meshes'][0]['primitives'][0]
    primitive['attributes'].update(JOINTS_0=joints,WEIGHTS_0=weights)
    doc['nodes']=[{'mesh':0,'skin':0},{'children':[2]},{'translation':[0,1,0]}]
    doc['skins']=[{'joints':[1,2],'inverseBindMatrices':bind}]
    doc['buffers'][0]['byteLength']=len(blob)
    return doc,bytes(blob),weights


def test_rig_validation_requires_real_weights_hierarchy_and_bind_matrices():
    from rig_runtime import validate_rigged_glb
    doc,blob,weights=rig_fixture()
    assert validate_rigged_glb(glb(doc,blob))['bones']==2
    bad=copy.deepcopy(doc);bad['nodes'][2]['children']=[1]
    with pytest.raises(ValueError,match='hierarchy'):validate_rigged_glb(glb(bad,blob))
    bad=copy.deepcopy(doc);bad['skins'][0]['joints']=[1,1]
    with pytest.raises(ValueError,match='joint'):validate_rigged_glb(glb(bad,blob))
    offset=doc['bufferViews'][doc['accessors'][weights]['bufferView']]['byteOffset']
    corrupt=bytearray(blob);struct.pack_into('<f',corrupt,offset,0.1)
    with pytest.raises(ValueError,match='weight'):validate_rigged_glb(glb(doc,corrupt))
    corrupt=bytearray(blob);struct.pack_into('<f',corrupt,offset,float('nan'))
    with pytest.raises(ValueError,match='weight'):validate_rigged_glb(glb(doc,corrupt))
    static,binary=textured_glb_fixture()
    with pytest.raises(ValueError,match='skin'):validate_rigged_glb(glb(static,binary))


def test_rig_api_validates_source_setup_and_preserves_static_job(monkeypatch,tmp_path):
    import app as server
    import time
    from fastapi.testclient import TestClient
    source='a'*32
    folder=tmp_path/source;folder.mkdir()
    doc,blob=textured_glb_fixture();(folder/'object.glb').write_bytes(glb(doc,blob))
    original={'id':source,'state':'complete','output_type':'mesh','settings':{'seed':42}}
    monkeypatch.setattr(server,'OUTPUTS',tmp_path)
    monkeypatch.setattr(server,'jobs',{source:original.copy()})
    monkeypatch.setattr(server,'active_job',None)
    monkeypatch.setattr(server,'job_progress',{})
    monkeypatch.setattr(server,'mesh_cancellations',{})
    monkeypatch.setattr(server,'rig_backend_installed',lambda:False,raising=False)
    monkeypatch.setattr(server,'rig_models_ready',lambda:True,raising=False)
    client=TestClient(server.app)
    assert client.post('/api/jobs/missing/rig').status_code==404
    assert client.post('/api/jobs/'+source+'/rig').status_code==503
    monkeypatch.setattr(server,'rig_backend_installed',lambda:True)
    monkeypatch.setattr(server,'active_job','occupied')
    assert client.post('/api/jobs/'+source+'/rig').status_code==409
    monkeypatch.setattr(server,'active_job',None)
    def worker(input_path,output,seed,emit,cancel):
        assert input_path==folder/'object.glb'
        assert seed==42
        emit({'stage':'skeleton','message':'Predicting bones'})
        for name in ('rigged.glb','rigged.fbx','character.blend','rig.json'):(output/name).write_bytes(b'fixture')
        return {'rigged':True,'bones':23,'triangles':1}
    monkeypatch.setattr(server,'generate_rig',worker,raising=False)
    monkeypatch.setattr(server,'release_idol',lambda:None)
    response=client.post('/api/jobs/'+source+'/rig')
    assert response.status_code==202,response.text
    job_id=response.json()['id']
    for _ in range(100):
        job=client.get('/api/jobs/'+job_id).json()
        if job['state']!='running' and server.active_job is None:break
        time.sleep(.01)
    assert job['state']=='complete',job
    assert job['rig']['rigged'] and job['source_job']==source
    assert set(job['files'])=={'rigged.glb','rigged.fbx','character.blend','rig.json'}
    assert server.jobs[source]==original
    assert (folder/'object.glb').read_bytes()==glb(doc,blob)
    server.jobs.pop(job_id)
    assert client.get('/api/jobs/'+job_id).json()['rig']['bones']==23


def test_rig_orchestrator_stops_after_a_failed_phase(monkeypatch,tmp_path):
    import rig_runtime as runtime
    import threading
    source=tmp_path/'source.glb';source.write_bytes(b'original')
    folder=tmp_path/'job';folder.mkdir()
    seen=[]
    def worker(command,log_folder,emit,cancel,**kwargs):
        phase=command[command.index('--phase')+1]
        seen.append(phase)
        assert kwargs['env']['HF_HUB_OFFLINE']=='1'
        assert kwargs['env']['WANDB_MODE']=='disabled'
        if phase=='skeleton':raise RuntimeError('Skeleton failed')
    monkeypatch.setattr(runtime,'run_worker',worker)
    with pytest.raises(RuntimeError,match='Skeleton failed'):
        runtime.generate_rig(source,folder,42,lambda e:None,threading.Event())
    assert seen==['rig_prepare','skeleton']
    assert source.read_bytes()==b'original'
    assert (folder/'input.glb').read_bytes()==b'original'


def test_rig_eta_uses_its_own_successful_history(tmp_path):
    from mesh_progress import MeshProgress
    from rig_runtime import PHASES
    now=[0.0]
    history=tmp_path/'rig-timings.json'
    p=MeshProgress({},lambda **e:None,history,clock=lambda:now[0],stages=PHASES,
                   baseline=dict.fromkeys(PHASES,10),scales={})
    p.event({'stage':'skeleton'})
    now[0]=4
    assert p.snapshot()['eta_seconds']==46
    p.event({'stage':'skinning'})
    now[0]=10;p.finish()
    q=MeshProgress({},lambda **e:None,history,stages=PHASES,baseline=dict.fromkeys(PHASES,10),scales={})
    assert q.estimates['skeleton']==pytest.approx(4)
    assert q.estimates['skinning']==pytest.approx(6)


def test_rig_export_rejects_invalid_bind_and_joint_references():
    from rig_runtime import validate_rigged_glb
    doc,blob,_=rig_fixture()
    bad=copy.deepcopy(doc);bad['skins'][0]['joints']=[1,999]
    with pytest.raises(ValueError,match='reference'):validate_rigged_glb(glb(bad,blob))
    bind=doc['accessors'][doc['skins'][0]['inverseBindMatrices']]
    offset=doc['bufferViews'][bind['bufferView']]['byteOffset']
    corrupt=bytearray(blob);struct.pack_into('<16f',corrupt,offset,*([0]*16))
    with pytest.raises(ValueError,match='bind matrix'):validate_rigged_glb(glb(doc,corrupt))
