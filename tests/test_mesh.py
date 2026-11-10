import json
import struct

import pytest


def test_mesh_assets_require_source_models_and_encoder(tmp_path, monkeypatch):
    import mesh_setup
    monkeypatch.setattr(mesh_setup, 'MODEL_ROOT', tmp_path)
    assert not mesh_setup.models_ready()
    for name, source in mesh_setup.SOURCES.items():
        folder=tmp_path/name
        folder.mkdir()
        for relative in source['required']:
            target=folder/relative
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(b'fixture')
        (folder/'.download-complete').write_text(source['revision'])
    src=tmp_path/'triposr-source'
    src.mkdir()
    (src/'.source-complete').write_text(mesh_setup.SOURCE_REVISION)
    (src/'tsr').mkdir()
    (src/'tsr/system.py').write_text('# fixture')
    bg=tmp_path/'rembg/u2net.onnx'
    bg.parent.mkdir()
    bg.write_bytes(b'fixture')
    assert mesh_setup.models_ready()
    (tmp_path/'triposr-dino/config.json').unlink()
    assert not mesh_setup.models_ready()


def glb(document, binary=b''):
    encoded=json.dumps(document).encode()
    encoded+=b' '*((-len(encoded))%4)
    data=struct.pack('<I4s',len(encoded),b'JSON')+encoded
    if binary:
        binary+=bytes((-len(binary))%4)
        data+=struct.pack('<I4s',len(binary),b'BIN\0')+binary
    return struct.pack('<4sII',b'glTF',2,12+len(data))+data


def textured_glb_fixture():
    from io import BytesIO
    from PIL import Image
    image=BytesIO()
    Image.new('RGB',(2,2),'red').save(image,format='PNG')
    binary=struct.pack('<9f',0,0,0,1,0,0,0,1,0)+struct.pack('<6f',0,0,1,0,0,1)+struct.pack('<3H',0,1,2)+image.getvalue()
    valid={'asset':{'version':'2.0'},'buffers':[{'byteLength':len(binary)}],
           'meshes':[{'primitives':[{'attributes':{'POSITION':0,'TEXCOORD_0':1},'indices':2,'material':0}]}],
           'accessors':[{'count':3,'bufferView':0,'componentType':5126,'type':'VEC3'},
                        {'count':3,'bufferView':1,'componentType':5126,'type':'VEC2'},
                        {'count':3,'bufferView':2,'componentType':5123,'type':'SCALAR'}],
           'images':[{'bufferView':3,'mimeType':'image/png'}],
           'bufferViews':[{'buffer':0,'byteOffset':0,'byteLength':36},
                          {'buffer':0,'byteOffset':36,'byteLength':24},
                          {'buffer':0,'byteOffset':60,'byteLength':6},
                          {'buffer':0,'byteOffset':66,'byteLength':len(image.getvalue())}],
           'textures':[{'source':0}], 'materials':[{'pbrMetallicRoughness':{'baseColorTexture':{'index':0}}}]}
    return valid,binary


def test_glb_validation_requires_embedded_mesh_uvs_and_texture():
    from mesh_runtime import validate_glb
    valid,binary=textured_glb_fixture()
    assert validate_glb(glb(valid,binary))['triangles']==1
    with pytest.raises(ValueError):
        validate_glb(glb({'asset':{'version':'2.0'}}))
    valid['images'][0]={'uri':'owner-file.png'}
    with pytest.raises(ValueError,match='embedded'):
        validate_glb(glb(valid,binary))
    with pytest.raises(ValueError):
        validate_glb(b'glTF truncated')


def test_worker_failure_is_reported_and_cancellation_reaps_process(tmp_path):
    import sys
    import threading
    from mesh_runtime import run_worker, MeshCancelled
    events=[]
    with pytest.raises(RuntimeError,match='exit code 7'):
        run_worker([sys.executable,'-c','raise SystemExit(7)'],tmp_path,events.append,threading.Event(),timeout=5)
    cancel=threading.Event()
    cancel.set()
    with pytest.raises(MeshCancelled):
        run_worker([sys.executable,'-c','import time;time.sleep(60)'],tmp_path,events.append,cancel,timeout=5)


def test_worker_timeout_and_structured_error_are_actionable(tmp_path):
    import sys
    import threading
    from mesh_runtime import run_worker
    with pytest.raises(RuntimeError,match='timed out'):
        run_worker([sys.executable,'-c','import time;time.sleep(60)'],tmp_path,lambda event:None,threading.Event(),timeout=.1)
    with pytest.raises(RuntimeError,match='GPU memory'):
        run_worker([sys.executable,'-c', 'print(\'IDOL_EVENT {"event":"error","message":"GPU memory unavailable"}\');raise SystemExit(1)'],
                   tmp_path,lambda event:None,threading.Event(),timeout=5)


def test_mesh_readiness_does_not_require_idol(monkeypatch):
    import app as server
    monkeypatch.setattr(server,'find_spec',lambda name:None)
    monkeypatch.setattr(server,'mesh_backend_installed',lambda:True)
    monkeypatch.setattr(server,'mesh_models_ready',lambda:True)
    state=server.status()
    assert not state['ready']
    assert state['mesh']['ready']


def test_mesh_form_settings_and_busy_validation(monkeypatch, tmp_path):
    import app as server
    from fastapi.testclient import TestClient
    from io import BytesIO
    from PIL import Image
    monkeypatch.setattr(server,'status',lambda:{'ready':False,'mesh':{'ready':True}})
    monkeypatch.setattr(server,'OUTPUTS',tmp_path)
    monkeypatch.setattr(server,'active_job','other-job')
    image=BytesIO()
    Image.new('RGB',(20,20),'orange').save(image,format='PNG')
    client=TestClient(server.app)
    def submit(**settings):
        return client.post('/api/generate',files={'image':('test.png',image.getvalue(),'image/png')},
                           data={'output_type':'mesh',**settings})
    assert submit(target_faces=17).status_code==422
    assert submit(texture_resolution=999).status_code==422
    assert submit(mesh_resolution=999).status_code==422
    assert submit().status_code==409
    monkeypatch.setattr(server,'active_job',None)
    monkeypatch.setattr(server,'status',lambda:{'ready':True,'mesh':{'ready':False}})
    assert submit().status_code==503


def test_cancelled_mesh_is_not_replaced_by_a_new_gpu_job(monkeypatch):
    import app as server
    import threading
    from fastapi.testclient import TestClient
    event=threading.Event()
    monkeypatch.setattr(server,'jobs',{'mesh':{'state':'running','output_type':'mesh'}})
    monkeypatch.setattr(server,'mesh_cancellations',{'mesh':event})
    monkeypatch.setattr(server,'active_job','mesh')
    client=TestClient(server.app)
    assert client.post('/api/jobs/mesh/cancel').status_code==202
    assert event.is_set()
    assert server.active_job=='mesh'
    assert client.post('/api/jobs/missing/cancel').status_code==404


def test_mesh_job_completes_with_download_and_persisted_metadata(monkeypatch,tmp_path):
    import app as server
    from fastapi.testclient import TestClient
    from io import BytesIO
    from PIL import Image
    import time
    monkeypatch.setattr(server,'OUTPUTS',tmp_path)
    monkeypatch.setattr(server,'active_job',None)
    monkeypatch.setattr(server,'pipeline',None)
    monkeypatch.setattr(server,'jobs',{})
    monkeypatch.setattr(server,'mesh_cancellations',{})
    monkeypatch.setattr(server,'job_progress',{})
    monkeypatch.setattr(server,'status',lambda:{'ready':False,'mesh':{'ready':True}})
    monkeypatch.setattr(server,'mesh_models_ready',lambda:True)
    valid,binary=textured_glb_fixture()
    def worker(path,settings,emit,cancel):
        assert settings['target_faces']==25000
        assert not cancel.is_set()
        emit({'stage':'extract','message':'Extracting','step':50,'total_steps':100})
        (path.parent/'object.glb').write_bytes(glb(valid,binary))
        (path.parent/'mesh.json').write_text('{}')
        emit({'stage':'export','message':'Saving'})
        return {'triangles':1,'vertices':3,'texture_resolution':512,'rigged':False}
    monkeypatch.setattr(server,'generate_mesh',worker)
    image=BytesIO();Image.new('RGB',(20,20),'blue').save(image,format='PNG')
    client=TestClient(server.app)
    response=client.post('/api/generate',data={'output_type':'mesh'},files={'image':('subject.png',image.getvalue(),'image/png')})
    assert response.status_code==202
    job_id=response.json()['id']
    for _ in range(200):
        result=client.get('/api/jobs/'+job_id).json()
        if result['state']!='running' and server.active_job is None:
            break
        time.sleep(.01)
    assert result['state']=='complete',result
    assert result['output_type']=='mesh'
    assert result['mesh']['rigged'] is False
    assert result['files']['object.glb'].endswith('/object.glb')
    assert (tmp_path/job_id/'object.glb').is_file()
    server.jobs.clear()
    assert client.get('/api/jobs/'+job_id).json()['mesh']['triangles']==1


def test_idol_cache_is_collected_before_mesh_worker(monkeypatch):
    import app as server
    import sys,types,weakref
    class Cached:
        def __init__(self):
            self.cycle=self
    monkeypatch.setattr(server,'pipeline',Cached())
    reference=weakref.ref(server.pipeline)
    calls=[]
    monkeypatch.setitem(sys.modules,'torch',types.SimpleNamespace(cuda=types.SimpleNamespace(empty_cache=lambda:calls.append('released'))))
    server.release_idol()
    assert reference() is None
    assert calls==['released']


def test_mesh_eta_measures_samples_and_learns_resolution_scaling(tmp_path):
    from mesh_progress import MeshProgress
    stamp=[0.0]
    events=[]
    settings={'mesh_resolution':192,'texture_resolution':1024,'target_faces':25000}
    path=tmp_path/'timings.json'
    p=MeshProgress(settings,lambda **event:events.append(event),path,clock=lambda:stamp[0])
    p.event({'stage':'extract','step':0,'total_steps':100})
    stamp[0]=2
    p.event({'stage':'extract','step':25,'total_steps':100})
    assert events[-1]['eta_seconds']==25
    assert events[-1]['eta_basis']=='measured'
    stamp[0]=8;p.event({'stage':'texture'})
    stamp[0]=12;p.event({'stage':'export'})
    stamp[0]=13;p.finish()
    q=MeshProgress({**settings,'mesh_resolution':256},lambda **event:None,path,clock=lambda:stamp[0])
    assert q.estimates['extract']==pytest.approx(8*(256/192)**3)
    path.write_text('[]')
    assert MeshProgress(settings,lambda **event:None,path).snapshot()['eta_seconds'] is None


def test_background_download_rejects_bad_checksum(tmp_path,monkeypatch):
    import mesh_setup
    from io import BytesIO
    monkeypatch.setattr(mesh_setup,'MODEL_ROOT',tmp_path)
    monkeypatch.setattr(mesh_setup.urllib.request,'urlopen',lambda *a,**kw:BytesIO(b'corrupt'))
    with pytest.raises(RuntimeError,match='checksum'):
        mesh_setup.download_background()
    assert not (tmp_path/'rembg/u2net.onnx').exists()
    assert not (tmp_path/'rembg/u2net.partial').exists()


def test_worker_cancellation_reaps_the_started_child(tmp_path):
    import sys,threading,os
    from mesh_runtime import run_worker,MeshCancelled
    cancellation=threading.Event()
    seen=[]
    command=[sys.executable,'-c','import json,os,time;print("IDOL_EVENT "+json.dumps({"event":"started","pid":os.getpid()}),flush=True);time.sleep(60)']
    def event(data):
        seen.append(data['pid'])
        cancellation.set()
    with pytest.raises(MeshCancelled):
        run_worker(command,tmp_path,event,cancellation,timeout=5)
    assert seen
    with pytest.raises(ProcessLookupError):
        os.kill(seen[0],0)
