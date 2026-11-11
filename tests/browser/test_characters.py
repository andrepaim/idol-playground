"""Real Chromium + isolated local API/PIL. No owner images or model inference."""
from contextlib import contextmanager
from io import BytesIO
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.parse import parse_qs,urlparse

from PIL import Image
from playwright.sync_api import sync_playwright,expect
import pytest

ROOT=Path(__file__).resolve().parents[2]


@contextmanager
def running_site(directory,mode='normal'):
    directory.mkdir(parents=True,exist_ok=True)
    log=directory/'server.log'
    environment={**os.environ,'IDOL_CHARACTERS':'0' if mode=='disabled' else '1',
                 'IDOL_CHARACTER_STORE':str(directory/'characters'),'IDOL_CHARACTER_RESOURCE':str(directory/'resource.lock')}
    code='''import uvicorn
uvicorn.run('app:app',host='127.0.0.1',port=0)
'''
    if mode=='waiting':
        code='''import sys
from dataclasses import replace
import character_service
Original=character_service.CharacterService
class Waiting(Original):
 def __init__(self,*args,**kwargs):
  super().__init__(*args,**kwargs)
  current=self.executor.adapters['input']
  self.executor.adapters['input']=replace(current,versions={'adapter':'owned-browser-wait-v1'},command=lambda _:[sys.executable,'-c','import time;time.sleep(600)'])
character_service.CharacterService=Waiting
'''+code
    with log.open('wb') as output:
        process=subprocess.Popen([sys.executable,'-c',code],cwd=ROOT,env=environment,stdout=output,stderr=output)
    try:
        deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            matches=re.findall(r'Uvicorn running on http://127\.0\.0\.1:(\d+)',log.read_text())
            if matches: break
            assert process.poll() is None,'Disposable API server did not start'
            time.sleep(.05)
        assert matches,'Disposable server readiness timeout'
        yield 'http://127.0.0.1:'+matches[-1]
    finally:
        if process.poll() is None:
            process.terminate();process.wait(timeout=15)


@pytest.fixture(scope='module')
def character_site(tmp_path_factory):
    assert (ROOT/'dist/index.html').exists(),'Run npm run build first'
    with running_site(tmp_path_factory.mktemp('character-browser')) as site: yield site


@pytest.fixture
def character_page(character_site):
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch(args=['--no-sandbox'])
        page=browser.new_page(base_url=character_site,viewport={'width':1280,'height':900})
        errors=[];external=[];uploads=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        def request(request):
            if not request.url.startswith((character_site+'/', 'blob:'+character_site+'/')): external.append(request.url)
            if request.url==character_site+'/api/characters' and request.method=='POST': uploads.append(request.url)
        page.on('request',request)
        page.goto(character_site+'/characters.html')
        yield page,uploads
        assert not errors,errors
        assert not external,external
        browser.close()


def image_file(color='orange'):
    stream=BytesIO();Image.new('RGBA',(80,100),color).save(stream,format='PNG')
    return {'name':'synthetic.png','mimeType':'image/png','buffer':stream.getvalue()}


def upload(page):
    expect(page.locator('#workflow')).to_be_visible()
    page.locator('#character-image').set_input_files(image_file())
    page.locator('#upload-character').click()
    expect(page.locator('#image-state')).to_have_text('Needs review')
    return parse_qs(urlparse(page.url).query)['character'][0]


def review_image(page):
    page.locator('#image-confirmed').check()
    page.locator('#confirm-image').click()
    expect(page.locator('#image-state')).to_have_text('Reviewed')


def test_upload_review_anatomy_and_refresh_reconnect(character_page):
    page,uploads=character_page
    identifier=upload(page)
    expect(page.locator('#prepared-image')).to_be_visible()
    expect(page.locator('#confirm-image')).to_be_disabled()
    review_image(page)
    expect(page.locator('#anatomy-form')).to_be_visible()
    page.locator('#body-plan').select_option('quadruped')
    page.locator('#species').select_option('dog')
    for name in ('single-subject','full-body','limbs-separable','anatomy-confirmed'): page.locator('#'+name).check()
    page.locator('#save-anatomy').click()
    expect(page.locator('#anatomy-state')).to_have_text('Reviewed')
    expect(page.locator('#saved-character option:checked')).to_contain_text('Reviewed')
    before=page.request.get('/api/characters/'+identifier).json()
    page.reload()
    expect(page.locator('#anatomy-state')).to_have_text('Reviewed')
    after=page.request.get('/api/characters/'+identifier).json()
    assert after['stages']['input']['attempt']==before['stages']['input']['attempt']
    assert after['stages']['assessment']['attempt']==before['stages']['assessment']['attempt']
    assert len(uploads)==1
    expect(page.locator('#next-steps')).to_contain_text('not enabled')
    original=page.request.get('/api/characters/'+identifier+'/artifacts/input/original.bin')
    assert original.body()==image_file()['buffer']


def test_network_loss_reconnects_without_submitting_again(character_page):
    page,uploads=character_page
    identifier=upload(page);review_image(page)
    before=page.request.get('/api/characters/'+identifier).json()
    pattern='**/api/characters/'+identifier
    page.route(pattern,lambda route:route.abort())
    expect(page.locator('#connection-status')).to_contain_text('Connection lost',timeout=5000)
    page.unroute(pattern)
    expect(page.locator('#connection-status')).to_contain_text('Connected',timeout=5000)
    assert page.request.get('/api/characters/'+identifier).json()['stages']['input']['attempt']==before['stages']['input']['attempt']
    assert len(uploads)==1


def test_invalid_link_mobile_and_blob_disposal(character_page):
    page,_=character_page
    page.goto(page.url+'?character=../../invalid')
    expect(page.locator('#character-message')).to_contain_text('Invalid character link')
    page.set_viewport_size({'width':375,'height':812})
    assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
    page.add_init_script('''window.blobCounts={created:0,revoked:0};
const create=URL.createObjectURL.bind(URL),revoke=URL.revokeObjectURL.bind(URL);
URL.createObjectURL=(value)=>{window.blobCounts.created++;return create(value)};
URL.revokeObjectURL=(value)=>{window.blobCounts.revoked++;return revoke(value)};''')
    page.goto(urlparse(page.url)._replace(query='').geturl())
    expect(page.locator('#workflow')).to_be_visible()
    for index,color in enumerate(('red','green','blue'),1):
        page.locator('#character-image').set_input_files(image_file(color))
        page.wait_for_function('(count)=>window.blobCounts.created===count',arg=index)
    assert page.evaluate('window.blobCounts')=={'created':3,'revoked':2}
    page.evaluate("window.dispatchEvent(new Event('pagehide'))")
    assert page.evaluate('window.blobCounts')=={'created':3,'revoked':3}


def test_disabled_character_workflow(tmp_path):
    with running_site(tmp_path/'disabled','disabled') as site,sync_playwright() as playwright:
        browser=playwright.chromium.launch(args=['--no-sandbox']);page=browser.new_page(base_url=site)
        page.goto(site+'/characters.html')
        expect(page.locator('#disabled-notice')).to_be_visible()
        expect(page.locator('#workflow')).to_be_hidden()
        browser.close()


def test_cancel_and_retry_ui_with_owned_waiting_worker(tmp_path):
    with running_site(tmp_path/'waiting','waiting') as site,sync_playwright() as playwright:
        browser=playwright.chromium.launch(args=['--no-sandbox']);page=browser.new_page(base_url=site)
        page.goto(site+'/characters.html')
        page.locator('#character-image').set_input_files(image_file())
        page.locator('#upload-character').click()
        expect(page.locator('#cancel-stage')).to_be_visible()
        page.locator('#cancel-stage').click()
        expect(page.locator('#image-state')).to_have_text('Stopped')
        page.locator('#retry-input').click()
        expect(page.locator('#cancel-stage')).to_be_visible()
        page.locator('#cancel-stage').click()
        expect(page.locator('#image-state')).to_have_text('Stopped')
        identifier=parse_qs(urlparse(page.url).query)['character'][0]
        assert page.request.get('/api/characters/'+identifier).json()['stages']['input']['attempt']==2
        browser.close()


def test_review_waits_for_saved_crop_details_and_preserves_consent(character_page):
    page,_=character_page
    pending=[]
    pattern=re.compile(r'/artifacts/input/input\.json\?')
    page.route(pattern,lambda route:pending.append(route))
    with page.expect_request(pattern): upload(page)
    expect(page.locator('#image-confirmed')).to_be_disabled()
    held_route(page,pending).continue_()
    page.unroute(pattern)
    expect(page.locator('#image-confirmed')).to_be_enabled()
    page.locator('#image-confirmed').check()
    expect(page.locator('#confirm-image')).to_be_enabled()
    with page.expect_response(re.compile(r'/api/characters/[0-9a-f]{32}$')):
        pass  # one normal status refresh must preserve explicit consent
    expect(page.locator('#image-confirmed')).to_be_checked()
    expect(page.locator('#source-image')).to_be_visible()
    assert page.locator('#source-image').evaluate('(image)=>image.complete && image.naturalWidth===80')


def test_delayed_status_cannot_replace_a_newer_review(character_page):
    page,_=character_page
    identifier=upload(page)
    expect(page.locator('#image-confirmed')).to_be_enabled()
    pending=[]
    pattern=re.compile('/api/characters/'+identifier+'$')
    captured=[False]
    def delayed(route):
        if captured[0]: route.continue_()
        else:
            captured[0]=True;pending.append(route)
    page.route(pattern,delayed)
    with page.expect_request(pattern): pass
    held=held_route(page,pending)
    old=held.fetch()  # capture actual earlier durable state, delay only delivery
    review_image(page)
    page.evaluate("""window.observedImageStates=[];
new MutationObserver(()=>window.observedImageStates.push(document.getElementById('image-state').textContent))
.observe(document.getElementById('image-state'),{childList:true,subtree:true,characterData:true});""")
    held.fulfill(response=old)
    page.unroute(pattern)
    with page.expect_response(pattern): pass
    assert 'Needs review' not in page.evaluate('window.observedImageStates')


def held_route(page,pending):
    deadline=time.monotonic()+5
    while not pending and time.monotonic()<deadline:
        page.wait_for_timeout(10)
    assert pending,'Expected route handler did not receive the request'
    return pending.pop(0)


def test_crop_and_saved_character_selection_keep_originals(character_page):
    page,uploads=character_page
    first=upload(page)
    expect(page.locator('#image-confirmed')).to_be_enabled()
    page.get_by_text('Adjust the crop',exact=True).click()
    page.locator('#whole-image').uncheck()
    page.locator('#crop-left').fill('16')
    review_image(page)
    page.wait_for_function("document.getElementById('prepared-image').naturalWidth===64")
    page.locator('#character-image').set_input_files(image_file('blue'))
    page.locator('#upload-character').click()
    expect(page.locator('#image-state')).to_have_text('Needs review')
    second=parse_qs(urlparse(page.url).query)['character'][0]
    assert first!=second and len(uploads)==2
    page.locator('#saved-character').select_option(first)
    expect(page.locator('#image-state')).to_have_text('Reviewed')
    page.wait_for_function("document.getElementById('prepared-image').naturalWidth===64")
    assert parse_qs(urlparse(page.url).query)['character'][0]==first and len(uploads)==2
    assert page.request.get('/api/characters/'+first+'/artifacts/input/original.bin').body()==image_file()['buffer']
