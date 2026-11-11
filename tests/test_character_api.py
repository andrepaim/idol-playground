"""Opt-in API with real PIL workers, disposable stores, synthetic images only."""
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import json
import time

from fastapi.testclient import TestClient
from PIL import Image
import pytest

import app as server
from character_service import CharacterService

IDENTITY='a'*32


def picture(color='orange'):
    stream=BytesIO();Image.new('RGBA',(80,100),color).save(stream,format='PNG');return stream.getvalue()


@pytest.fixture
def client(monkeypatch,tmp_path):
    monkeypatch.setenv('IDOL_CHARACTERS','1')
    monkeypatch.setenv('IDOL_CHARACTER_STORE',str(tmp_path/'characters'))
    monkeypatch.setenv('IDOL_CHARACTER_RESOURCE',str(tmp_path/'resource.lock'))
    monkeypatch.setattr(server,'OUTPUTS',tmp_path/'legacy')
    monkeypatch.setattr(server,'executor',ThreadPoolExecutor(max_workers=1))
    with TestClient(server.app,base_url="http://127.0.0.1") as client:
        yield client


def submit(client,data=None,identifier=IDENTITY):
    return client.post('/api/characters',data={'request_id':identifier},files={'image':('private-owner-name.png',picture() if data is None else data,'image/png')})


def wait(client,stage='input',identifier=IDENTITY):
    for _ in range(150):
        response=client.get(f'/api/characters/{identifier}');assert response.status_code==200,response.text
        record=response.json()
        if record['stages'][stage]['state']!='running': return record
        time.sleep(.02)
    pytest.fail('Owned CPU stage did not finish')


def reviewed_input(client):
    assert submit(client).status_code==202
    assert wait(client)['stages']['input']['state']=='awaiting_review'
    response=client.post(f'/api/characters/{IDENTITY}/input',json={'confirmed':True})
    assert response.status_code==202,response.text
    assert wait(client)['stages']['input']['state']=='succeeded'


def test_real_upload_review_artifacts_and_privacy(client):
    payload=picture();response=submit(client,payload)
    assert response.status_code==202,response.text
    record=wait(client)
    assert record['id']==IDENTITY and record['stages']['input']['state']=='awaiting_review'
    text=json.dumps(record)
    assert 'private-owner-name' not in text and '/home/' not in text and 'lease.json' not in text
    preview=client.get(f'/api/characters/{IDENTITY}/artifacts/input/prepared.png')
    assert preview.status_code==200 and preview.headers['content-type']=='image/png'
    with Image.open(BytesIO(preview.content)) as image: assert image.size==(80,100)
    original=client.get(f'/api/characters/{IDENTITY}/artifacts/input/original.bin')
    assert original.content==payload
    assert client.get(f'/api/characters/{IDENTITY}/artifacts/input/_execution.json').status_code==404
    assert client.post(f'/api/characters/{IDENTITY}/input',json={'confirmed':True}).status_code==202
    assert wait(client)['stages']['input']['state']=='succeeded'
    assert client.get(f'/api/characters/{IDENTITY}/artifacts/input/original.bin').content==payload


def test_duplicate_upload_reconnects_and_changed_input_conflicts(client):
    assert submit(client).status_code==202
    duplicate=submit(client)
    assert duplicate.status_code==200 and duplicate.json()['id']==IDENTITY
    assert wait(client)['stages']['input']['attempt']==1
    assert submit(client,picture('blue')).status_code==409
    assert client.get('/api/characters').json()['characters'][0]['id']==IDENTITY


@pytest.mark.parametrize('payload',[b'not an image',b''])
def test_disguised_upload_rejected_before_creating_character(client,payload):
    assert submit(client,payload).status_code==422
    assert client.get('/api/characters').json()['characters']==[]


def test_invalid_identity_and_cross_origin_cannot_mutate(client):
    assert submit(client,identifier='../escape').status_code==422
    response=client.post('/api/characters',headers={'Origin':'https://unrelated.invalid'},data={'request_id':IDENTITY},files={'image':('image.png',picture(),'image/png')})
    assert response.status_code==403
    assert client.get('/api/characters').json()['characters']==[]


def test_review_and_manual_anatomy_corrections_preserve_input(client):
    reviewed_input(client)
    before=client.get(f'/api/characters/{IDENTITY}').json()['stages']['input']
    missing=client.post(f'/api/characters/{IDENTITY}/assessment',json={})
    assert missing.status_code==202
    assert wait(client,'assessment')['stages']['assessment']['state']=='awaiting_review'
    fields={'body_plan':'quadruped','species':'dog','front_axis':'+z','scale_m':1.0,'single_subject':True,'full_body':True,'limbs_separable':True,'confirmed':True}
    assert client.post(f'/api/characters/{IDENTITY}/assessment',json=fields).status_code==202
    record=wait(client,'assessment')
    assert record['stages']['assessment']['state']=='succeeded'
    assert record['stages']['input']==before
    report=client.get(f'/api/characters/{IDENTITY}/artifacts/assessment/assessment.json').json()
    assert report['body_plan']=='quadruped' and report['source']=='manual'
    fields['body_plan']='unsupported'
    assert client.post(f'/api/characters/{IDENTITY}/assessment',json=fields).status_code==202
    assert wait(client,'assessment')['stages']['assessment']['state']=='failed'
    assert client.get(f'/api/characters/{IDENTITY}/artifacts/input/original.bin').status_code==200


def test_cache_retry_does_not_create_another_worker(client):
    reviewed_input(client)
    before=client.get(f'/api/characters/{IDENTITY}').json()
    assert client.post(f'/api/characters/{IDENTITY}/stages/input/retry',json={'confirmed':True}).status_code==202
    after=wait(client)
    assert after['stages']['input']['attempt']==before['stages']['input']['attempt']
    assert client.post(f'/api/characters/{IDENTITY}/stages/splat/retry',json={}).status_code==422


def test_disabled_api_does_not_create_private_store(monkeypatch,tmp_path):
    monkeypatch.delenv('IDOL_CHARACTERS',raising=False)
    monkeypatch.setenv('IDOL_CHARACTER_STORE',str(tmp_path/'disabled'))
    monkeypatch.setattr(server,'executor',ThreadPoolExecutor(max_workers=1))
    with TestClient(server.app) as client:
        assert submit(client).status_code==404
    assert not (tmp_path/'disabled').exists()


def test_service_restart_retains_same_upload_identity(tmp_path):
    root=tmp_path/'store';resource=tmp_path/'resource.lock'
    first=CharacterService(root,resource)
    try:
        first.create(IDENTITY,picture())
        for _ in range(100):
            first.poll()
            if first.status(IDENTITY)['stages']['input']['state']!='running': break
            time.sleep(.02)
        assert first.status(IDENTITY)['stages']['input']['state']=='awaiting_review'
    finally: first.close()
    second=CharacterService(root,resource)
    try:
        record,created=second.create(IDENTITY,picture())
        assert not created and record['stages']['input']['attempt']==1
    finally: second.close()


def test_crop_and_exif_metadata_are_normalized_without_rewriting_original(client):
    image=Image.new('RGB',(80,100),'red')
    for x in range(40,80):
        for y in range(100): image.putpixel((x,y),(0,0,255))
    exif=Image.Exif();exif[315]='PRIVATE_AUTHOR_METADATA'
    stream=BytesIO();image.save(stream,format='PNG',exif=exif,icc_profile=b'PRIVATE_COLOR_METADATA');payload=stream.getvalue()
    assert submit(client,payload).status_code==202
    wait(client)
    response=client.post(f'/api/characters/{IDENTITY}/input',json={'confirmed':True,'crop':[40,0,80,100]})
    assert response.status_code==202
    assert wait(client)['stages']['input']['state']=='succeeded'
    with Image.open(BytesIO(client.get(f'/api/characters/{IDENTITY}/artifacts/input/prepared.png').content)) as prepared:
        assert prepared.size==(40,100) and prepared.getpixel((20,50))==(0,0,255,255)
        assert not prepared.getexif()
        assert prepared.info.get('icc_profile') is None
        assert b'PRIVATE_AUTHOR_METADATA' not in prepared.tobytes()
    assert client.get(f'/api/characters/{IDENTITY}/artifacts/input/original.bin').content==payload


def test_oversized_upload_is_bounded_and_leaves_no_character(client):
    from character_input import MAX_UPLOAD
    response=submit(client,b'0'*(MAX_UPLOAD+128*1024))
    assert response.status_code==413,response.text
    assert client.get('/api/characters').json()['characters']==[]


def test_cancel_retains_original_and_retry_runs_a_new_attempt(client,monkeypatch):
    from dataclasses import replace
    import sys
    service=server.app.state.character_service
    original=service.executor.adapters['input']
    waiting=replace(original,versions={'adapter':'owned-waiting-fixture'},command=lambda _: [sys.executable,'-c','import time;time.sleep(600)'])
    monkeypatch.setitem(service.executor.adapters,'input',waiting)
    assert submit(client).status_code==202
    assert client.post(f'/api/characters/{IDENTITY}/cancel').status_code==202
    assert client.get(f'/api/characters/{IDENTITY}').json()['stages']['input']['state']=='cancelled'
    assert client.get(f'/api/characters/{IDENTITY}/artifacts/input/original.bin').content==picture()
    monkeypatch.setitem(service.executor.adapters,'input',original)
    assert client.post(f'/api/characters/{IDENTITY}/stages/input/retry',json={'confirmed':True}).status_code==202
    record=wait(client)
    assert record['stages']['input']['state']=='succeeded' and record['stages']['input']['attempt']==2


def test_corrupt_or_symlinked_artifact_is_never_served(client):
    reviewed_input(client)
    service=server.app.state.character_service
    record=service.store.load(IDENTITY)
    ref=next(item for item in record['stages']['input']['outputs'] if item['path'].endswith('/prepared.png'))
    path=service.store.root/IDENTITY/ref['path']
    path.write_bytes(b'corrupt fixture')
    assert client.get(f'/api/characters/{IDENTITY}/artifacts/input/prepared.png').status_code==409
    path.unlink();path.symlink_to('/etc/hostname')
    response=client.get(f'/api/characters/{IDENTITY}/artifacts/input/prepared.png')
    assert response.status_code==409 and '/etc/' not in response.text
    assert client.get(f'/api/characters/{IDENTITY}/artifacts/input/original.bin').status_code==200


def test_bad_crop_or_untrusted_parameters_cannot_launch_worker(client):
    reviewed_input(client)
    before=client.get(f'/api/characters/{IDENTITY}').json()
    for settings in ({'confirmed':True,'crop':[0,0,900,100]}, {'confirmed':True,'command':['touch','escape']}, {'confirmed':'true'}):
        assert client.post(f'/api/characters/{IDENTITY}/input',json=settings).status_code==422
    after=client.get(f'/api/characters/{IDENTITY}').json()
    assert after['revision']==before['revision']


def test_concurrent_duplicate_submissions_share_one_attempt(client):
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses=list(pool.map(lambda _: submit(client),range(2)))
    assert sorted(response.status_code for response in responses)==[200,202]
    record=wait(client)
    assert record['stages']['input']['attempt']==1
    service=server.app.state.character_service
    assert len(list((service.store.root/IDENTITY/'runs'/'input').iterdir()))==1


def test_oriented_image_dimensions_and_input_correction_invalidation(client):
    image=Image.new('RGB',(80,100),'green');exif=Image.Exif();exif[274]=6
    stream=BytesIO();image.save(stream,format='PNG',exif=exif)
    assert submit(client,stream.getvalue()).status_code==202
    wait(client)
    assert client.post(f'/api/characters/{IDENTITY}/input',json={'confirmed':True}).status_code==202
    assert wait(client)['stages']['input']['state']=='succeeded'
    with Image.open(BytesIO(client.get(f'/api/characters/{IDENTITY}/artifacts/input/prepared.png').content)) as prepared:
        assert prepared.size==(100,80) and not prepared.getexif()
    fields={'body_plan':'biped','species':'person','confirmed':True,'single_subject':True,'full_body':True,'limbs_separable':True}
    assert client.post(f'/api/characters/{IDENTITY}/assessment',json=fields).status_code==202
    assert wait(client,'assessment')['stages']['assessment']['state']=='succeeded'
    assert client.post(f'/api/characters/{IDENTITY}/input',json={'confirmed':True,'crop':[0,0,80,80]}).status_code==202
    record=wait(client)
    assert record['stages']['input']['state']=='succeeded' and record['stages']['assessment']['state']=='pending'


def test_rejects_animation_and_decompression_bomb_before_storage(client):
    import struct,zlib
    stream=BytesIO();Image.new('RGB',(80,100),'red').save(stream,format='GIF')
    assert submit(client,stream.getvalue()).status_code==422
    def chunk(kind,data):
        return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    bomb=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',100000,100000,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(b'\x00\x00\x00\x00'))+chunk(b'IEND',b'')
    assert submit(client,bomb).status_code==422
    assert client.get('/api/characters').json()['characters']==[]


def test_uncertain_upload_pointer_preserves_source_and_blocks_new_work(tmp_path,monkeypatch):
    from character_store import CommitUncertain
    root=tmp_path/'store';resource=tmp_path/'resource.lock'
    first=CharacterService(root,resource)
    original=first.store._atomic
    def uncertain(path,data):
        original(path,data)
        if path.name=='request.json': raise CommitUncertain('Injected post-publication uncertainty')
    try:
        with monkeypatch.context() as patch:
            patch.setattr(first.store,'_atomic',uncertain)
            with pytest.raises(CommitUncertain): first.create(IDENTITY,picture())
        assert not first.ready
        assert first.status(IDENTITY)['stages']['input']['attempt']==0
        assert first.artifact(IDENTITY,'input','original.bin')==picture()
        with pytest.raises(RuntimeError): first.create('b'*32,picture())
    finally: first.close()
    second=CharacterService(root,resource)
    try:
        record,created=second.create(IDENTITY,picture())
        assert not created and record['stages']['input']['attempt']==1
    finally: second.close()


def test_non_loopback_host_is_rejected_and_status_is_not_cached(client):
    assert client.get('/api/characters',headers={'Host':'unrelated.invalid'}).status_code==403
    response=client.get('/api/characters')
    assert response.headers['cache-control']=='no-store'
    assert response.headers['x-content-type-options']=='nosniff'


def test_unsupported_platform_fails_before_creating_store(tmp_path,monkeypatch):
    import character_service
    with monkeypatch.context() as patch:
        patch.setattr(character_service.sys,'platform','darwin')
        with pytest.raises(RuntimeError): CharacterService(tmp_path/'unsupported',tmp_path/'resource.lock')
    assert not (tmp_path/'unsupported').exists()
