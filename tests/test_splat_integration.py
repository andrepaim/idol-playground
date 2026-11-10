"""Integration contracts for approved splat-derived meshes; no optional CUDA imports."""
import copy
import json
import struct
import time
import pytest
from fastapi.testclient import TestClient
from test_mesh import textured_glb_fixture,glb


def colored_fixture():
    doc,binary=textured_glb_fixture();blob=bytearray(binary)
    while len(blob)%4:blob.append(0)
    offset=len(blob);blob.extend(struct.pack('<12f',*([.3,.1,.05,1]*3)))
    view=len(doc['bufferViews']);doc['bufferViews'].append({'buffer':0,'byteOffset':offset,'byteLength':48})
    index=len(doc['accessors']);doc['accessors'].append({'bufferView':view,'componentType':5126,'type':'VEC4','count':3})
    primitive=doc['meshes'][0]['primitives'][0]
    primitive['attributes'].pop('TEXCOORD_0');primitive['attributes']['COLOR_0']=index
    doc.pop('images');doc.pop('textures')
    doc['materials']=[{'extensions':{'KHR_materials_unlit':{}},'pbrMetallicRoughness':{}}]
    doc['buffers'][0]['byteLength']=len(blob)
    return doc,bytes(blob),offset


def test_vertex_appearance_is_validated_without_requiring_uv_textures():
    from mesh_runtime import validate_glb
    doc,binary,offset=colored_fixture()
    assert validate_glb(glb(doc,binary))['appearance']=='vertex_colors'
    invalid=bytearray(binary);struct.pack_into('<f',invalid,offset,float('nan'))
    with pytest.raises(ValueError,match='color'):validate_glb(glb(doc,invalid))
    invalid=bytearray(binary);struct.pack_into('<f',invalid,offset,1.2)
    with pytest.raises(ValueError,match='color'):validate_glb(glb(doc,invalid))
    missing=copy.deepcopy(doc);missing['meshes'][0]['primitives'][0]['attributes'].pop('COLOR_0')
    with pytest.raises(ValueError):validate_glb(glb(missing,binary))


@pytest.fixture
def conversion(monkeypatch,tmp_path):
    import app as server
    source='a'*32;folder=tmp_path/source;folder.mkdir()
    (folder/'object.ply').write_bytes(b'original splat fixture')
    job={'id':source,'state':'complete','settings':{'seed':7,'num_gaussians':262144},'files':{'object.ply':'/outputs/'+source+'/object.ply'}}
    (folder/'job.json').write_text(json.dumps(job))
    monkeypatch.setattr(server,'OUTPUTS',tmp_path)
    monkeypatch.setattr(server,'jobs',{})
    monkeypatch.setattr(server,'active_job',None)
    monkeypatch.setattr(server,'job_progress',{})
    monkeypatch.setattr(server,'mesh_cancellations',{})
    monkeypatch.setattr(server,'splat_backend_installed',lambda:True,raising=False)
    monkeypatch.setattr(server,'splat_models_ready',lambda:True,raising=False)
    monkeypatch.setattr(server,'release_idol',lambda:None)
    return TestClient(server.app),server,source,folder


def test_existing_splat_conversion_validates_setup_and_source(conversion,monkeypatch):
    client,server,source,folder=conversion
    assert client.post('/api/jobs/missing/mesh').status_code==404
    monkeypatch.setattr(server,'splat_backend_installed',lambda:False)
    assert client.post(f'/api/jobs/{source}/mesh').status_code==503
    monkeypatch.setattr(server,'splat_backend_installed',lambda:True)
    monkeypatch.setattr(server,'active_job','busy')
    assert client.post(f'/api/jobs/{source}/mesh').status_code==409
    monkeypatch.setattr(server,'active_job',None)
    assert client.post(f'/api/jobs/{source}/mesh',data={'surface_quality':'impossible'}).status_code==422
    (folder/'object.ply').unlink()
    assert client.post(f'/api/jobs/{source}/mesh').status_code==409


def test_existing_splat_conversion_persists_result_and_keeps_source(conversion,monkeypatch):
    client,server,source,folder=conversion
    original=(folder/'job.json').read_bytes()
    doc,blob,_=colored_fixture()
    calls=[]
    def worker(splat_path,output,settings,emit,cancel,**kwargs):
        calls.append(splat_path)
        assert splat_path==folder/'object.ply'
        assert settings['surface_quality']=='fine' and settings['component_mode']=='largest'
        emit({'stage':'capture','step':12,'total_steps':72,'message':'Rendering images'})
        (output/'object.glb').write_bytes(glb(doc,blob))
        return {'backend':'idol-splat','triangles':1,'appearance':'vertex_colors','rigged':False}
    monkeypatch.setattr(server,'generate_splat_mesh',worker,raising=False)
    response=client.post(f'/api/jobs/{source}/mesh')
    assert response.status_code==202,response.text
    job_id=response.json()['id']
    for _ in range(100):
        job=client.get('/api/jobs/'+job_id).json()
        if job['state']!='running' and server.active_job is None:break
        time.sleep(.01)
    assert job['state']=='complete',job
    assert calls==[folder/'object.ply']
    assert job['mesh']['backend']=='idol-splat' and job['source_job']==source
    assert job['files']['object.glb']==f'/outputs/{job_id}/object.glb'
    assert (folder/'object.ply').read_bytes()==b'original splat fixture'
    assert (folder/'job.json').read_bytes()==original
    server.jobs.clear()
    assert client.get('/api/jobs/'+job_id).json()['mesh']['appearance']=='vertex_colors'


def test_recent_results_include_persisted_splats_without_leaking_input_details(conversion):
    client,server,source,folder=conversion
    response=client.get('/api/jobs')
    assert response.status_code==200
    rows=response.json()['jobs']
    assert rows[0]['id']==source and rows[0]['output_type']=='splat'
    assert 'settings' not in rows[0] and 'files' not in rows[0]
    assert client.get('/api/jobs?limit=5000').status_code==422


def test_upload_routes_to_isolated_splat_mesh_with_idol_settings(conversion,monkeypatch):
    from io import BytesIO
    from PIL import Image
    client,server,source,folder=conversion
    monkeypatch.setattr(server,'splat_idol_installed',lambda:True)
    monkeypatch.setattr(server,'models_ready',lambda:True)
    seen=[]
    def worker(splat_path,output,settings,emit,cancel,*,image_path):
        assert splat_path is None and image_path==output/'input.png'
        seen.append(settings)
        (output/'object.glb').write_bytes(b'fixture')
        emit({'stage':'capture','step':1,'total_steps':72})
        return {'backend':'idol-splat','triangles':1,'appearance':'vertex_colors'}
    monkeypatch.setattr(server,'generate_splat_mesh',worker)
    image=BytesIO();Image.new('RGB',(16,16),'red').save(image,format='PNG')
    response=client.post('/api/generate',data={'output_type':'mesh','mesh_backend':'idol','mode':'synthetic','steps':'10','seed':'9'},
                         files={'image':('test.png',image.getvalue(),'image/png')})
    assert response.status_code==202,response.text
    for _ in range(100):
        job=client.get('/api/jobs/'+response.json()['id']).json()
        if job['state']!='running' and server.active_job is None:break
        time.sleep(.01)
    assert job['state']=='complete',job
    assert seen[0]['steps']==10 and seen[0]['seed']==9 and seen[0]['mode']=='synthetic'
    assert job['mesh_backend']=='idol'


def test_cancelled_conversion_keeps_gpu_slot_until_worker_has_exited(conversion,monkeypatch):
    import threading
    from mesh_runtime import MeshCancelled
    client,server,source,folder=conversion
    entered=threading.Event();release=threading.Event()
    def worker(path,output,settings,emit,cancel,**kwargs):
        entered.set();cancel.wait(timeout=5)
        release.wait(timeout=5)
        raise MeshCancelled('cancelled')
    monkeypatch.setattr(server,'generate_splat_mesh',worker)
    response=client.post(f'/api/jobs/{source}/mesh');job_id=response.json()['id']
    assert entered.wait(timeout=2)
    assert client.post(f'/api/jobs/{job_id}/cancel').status_code==202
    assert server.active_job==job_id
    assert client.post(f'/api/jobs/{source}/mesh').status_code==409
    release.set()
    for _ in range(100):
        state=client.get('/api/jobs/'+job_id).json()
        if state['state']!='running' and server.active_job is None:break
        time.sleep(.01)
    assert state['state']=='cancelled'
    assert (folder/'object.ply').read_bytes()==b'original splat fixture'


def test_vertex_color_rig_still_requires_valid_joints_and_skin():
    from rig_runtime import validate_rigged_glb
    from test_rig import rig_fixture
    doc,binary,weight_index=rig_fixture()
    colored,blob,_=colored_fixture()
    # Keep the rig geometry and skin accessors, append its own COLOR_0 storage.
    data=bytearray(binary)
    while len(data)%4:data.append(0)
    begin=len(data);data.extend(struct.pack('<12f',*([.3,.1,.05,1]*3)))
    view=len(doc['bufferViews']);doc['bufferViews'].append({'buffer':0,'byteOffset':begin,'byteLength':48})
    attribute=len(doc['accessors']);doc['accessors'].append({'bufferView':view,'componentType':5126,'type':'VEC4','count':3})
    attrs=doc['meshes'][0]['primitives'][0]['attributes'];attrs.pop('TEXCOORD_0');attrs['COLOR_0']=attribute
    doc.pop('images');doc.pop('textures');doc['materials']=colored['materials'];doc['buffers'][0]['byteLength']=len(data)
    result=validate_rigged_glb(glb(doc,data))
    assert result['bones']==2 and result['appearance']=='vertex_colors' and result['textures']==0
    attrs.pop('WEIGHTS_0')
    with pytest.raises(ValueError,match='skin'):validate_rigged_glb(glb(doc,data))


def test_failed_phase_stops_conversion_and_keeps_original(monkeypatch,tmp_path):
    import splat_mesh_runtime as runtime
    import threading
    original=tmp_path/'original.ply';original.write_bytes(b'source')
    folder=tmp_path/'job';folder.mkdir()
    calls=[]
    def worker(command,*args,**kwargs):
        phase=command[command.index('--phase')+1];calls.append(phase)
        if phase=='stereo':raise RuntimeError('Depth failure')
    monkeypatch.setattr(runtime,'run_worker',worker)
    with pytest.raises(RuntimeError,match='Depth failure'):
        runtime.generate_splat_mesh(original,folder,{'surface_quality':'fine','component_mode':'largest'},lambda event:None,threading.Event())
    assert calls==['capture','stereo'] and original.read_bytes()==b'source'
    assert (folder/'source.ply').read_bytes()==b'source'


def test_stereo_setup_checksum_failure_preserves_cached_data(monkeypatch,tmp_path):
    import splat_mesh_setup as setup
    from io import BytesIO
    monkeypatch.setattr(setup,'MODEL_ROOT',tmp_path)
    source=tmp_path/'source';source.mkdir()
    monkeypatch.setattr(setup.subprocess,'run',lambda *a,**kw:None)
    monkeypatch.setattr(setup.subprocess,'check_output',lambda command,**kw:'' if 'status' in command else setup.SOURCE_REVISION)
    monkeypatch.setattr(setup.urllib.request,'urlopen',lambda *a,**kw:BytesIO(b'corrupt download'))
    with pytest.raises(RuntimeError,match='checksum'):setup.ensure_models()
    assert not (tmp_path/'DLNR_Middlebury.pth').exists()
    assert not (tmp_path/'DLNR_Middlebury.partial').exists()
    (tmp_path/'DLNR_Middlebury.pth').write_bytes(b'existing invalid file')
    with pytest.raises(RuntimeError,match='checksum'):setup.ensure_models()
    assert (tmp_path/'DLNR_Middlebury.pth').read_bytes()==b'existing invalid file'
