"""Real Chromium acceptance against built UI; API and splats are synthetic."""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
import math
import json
import struct
import threading

from PIL import Image, ImageChops
from playwright.sync_api import sync_playwright, expect
import pytest


@pytest.fixture(scope='module')
def site():
    root = Path(__file__).resolve().parents[2] / 'dist'
    assert (root / 'index.html').is_file(), 'Run npm run build first'
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(root), **kwargs)

        def do_GET(self):
            if self.path in ('/fixture.ply', '/fixture.glb', '/rig-fixture.glb', '/colored-fixture.glb'):
                data = colored_bytes() if self.path == '/colored-fixture.glb' else rig_bytes() if self.path == '/rig-fixture.glb' else mesh_bytes() if self.path.endswith('.glb') else splat_bytes()
                self.send_response(200)
                self.send_header('Content-Type', 'application/octet-stream')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            else:
                super().do_GET()

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f'http://127.0.0.1:{server.server_port}'
    server.shutdown()
    server.server_close()
    thread.join()


def splat_bytes():
    names = ['x', 'y', 'z', 'nx', 'ny', 'nz', 'f_dc_0', 'f_dc_1', 'f_dc_2',
             'opacity', 'scale_0', 'scale_1', 'scale_2', 'rot_0', 'rot_1', 'rot_2', 'rot_3']
    header = 'ply\nformat binary_little_endian 1.0\nelement vertex 128\n'
    header += ''.join(f'property float {name}\n' for name in names) + 'end_header\n'
    rows = []
    for i in range(128):
        angle = i * math.pi / 32
        rows.append(struct.pack('<17f', math.sin(angle) * .3, (i % 8) * .04, math.cos(angle) * .3,
                                0, 0, 0, 1, 0, 0, 5, -4, -4, -4, 1, 0, 0, 0))
    return header.encode() + b''.join(rows)


def mesh_bytes():
    image = BytesIO()
    Image.new('RGB', (512, 512), 'coral').save(image, format='PNG')
    binary = struct.pack('<9f', 0, 0, 0, 1, 0, 0, 0, 1, 0) + struct.pack('<6f', 0, 0, 1, 0, 0, 1) + struct.pack('<3H', 0, 1, 2) + b'\0\0' + image.getvalue()
    document = {'asset': {'version': '2.0'}, 'scene': 0, 'scenes': [{'nodes': [0]}], 'nodes': [{'mesh': 0}],
                'buffers': [{'byteLength': len(binary)}],
                'bufferViews': [{'buffer': 0, 'byteOffset': 0, 'byteLength': 36},
                                {'buffer': 0, 'byteOffset': 36, 'byteLength': 24},
                                {'buffer': 0, 'byteOffset': 60, 'byteLength': 6},
                                {'buffer': 0, 'byteOffset': 68, 'byteLength': len(image.getvalue())}],
                'accessors': [{'bufferView': 0, 'componentType': 5126, 'count': 3, 'type': 'VEC3', 'min': [0,0,0], 'max': [1,1,0]},
                              {'bufferView': 1, 'componentType': 5126, 'count': 3, 'type': 'VEC2'},
                              {'bufferView': 2, 'componentType': 5123, 'count': 3, 'type': 'SCALAR'}],
                'meshes': [{'primitives': [{'attributes': {'POSITION': 0, 'TEXCOORD_0': 1}, 'indices': 2, 'material': 0}]}],
                'images': [{'bufferView': 3, 'mimeType': 'image/png'}], 'textures': [{'source': 0}],
                'materials': [{'doubleSided': True, 'pbrMetallicRoughness': {'baseColorTexture': {'index': 0}, 'metallicFactor': 0}}]}
    encoded = json.dumps(document).encode()
    encoded += b' ' * (-len(encoded) % 4)
    binary += bytes(-len(binary) % 4)
    chunks = struct.pack('<I4s', len(encoded), b'JSON') + encoded + struct.pack('<I4s', len(binary), b'BIN\0') + binary
    return struct.pack('<4sII', b'glTF', 2, len(chunks) + 12) + chunks


@pytest.fixture
def browser_page(site):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(args=['--no-sandbox', '--enable-unsafe-swiftshader'])
        page = browser.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        state = {'phase': 'sampling', 'ready': True, 'mesh_ready': True, 'stereo_ready': True, 'mesh_backend': 'idol', 'conversions': 0, 'saved': [], 'rig_ready': True, 'submissions': 0, 'output_type': 'splat'}

        def api(route):
            path = route.request.url.split('/api/')[1]
            if path == 'status':
                route.fulfill(json={'ready': state['ready'], 'weights_downloaded': True, 'mesh': {'ready': state['mesh_ready'], 'weights_downloaded': True}, 'rig': {'ready': state['rig_ready'], 'weights_downloaded': True}, 'splat_mesh': {'ready': state['stereo_ready'], 'weights_downloaded': True, 'upload_ready': state['ready']}})
            elif path == 'jobs':
                route.fulfill(json={'jobs':state['saved']})
            elif path.endswith('/mesh'):
                state.update(output_type='mesh',mesh_backend='idol',phase='capture')
                state['conversions']+=1
                route.fulfill(status=202,json={'id':'converted'})
            elif path == 'generate':
                state['output_type'] = 'mesh' if b'name="output_type"\r\n\r\nmesh' in route.request.post_data_buffer else 'splat'
                state['mesh_backend'] = 'idol' if b'name="mesh_backend"\r\n\r\nidol' in route.request.post_data_buffer else 'triposr'
                state['submissions'] += 1
                route.fulfill(status=202, json={'id': 'fixture'})
            elif path.endswith('/rig'):
                state['output_type'] = 'rig'
                state['phase'] = 'skeleton'
                route.fulfill(status=202,json={'id':'rig-fixture'})
            elif path.endswith('/cancel'):
                state['phase'] = 'cancelled'
                route.fulfill(status=202, json={'state': 'cancelling'})
            else:
                phase = state['phase']
                job = {'stage': phase, 'state': 'running', 'message': 'Generating synthetic fixture',
                       'step': 4, 'total_steps': 10, 'elapsed_seconds': 12,
                       'eta_seconds': 45, 'eta_basis': 'measured'}
                if phase == 'cancelled':
                    job.update(state='cancelled', message='Generation cancelled')
                if phase == 'error':
                    job.update(state='error', message='Synthetic GPU failure')
                if phase == 'complete':
                    job.update(state='complete', seconds=20, settings={'num_gaussians': 128, 'seed': 42},
                               files={'object.ply': '/fixture.ply'})
                    if state['output_type'] == 'mesh':
                        job.update(output_type='mesh', mesh_backend=state['mesh_backend'], mesh={'triangles': 1, 'texture_resolution': 512}, files={'object.glb': '/fixture.glb'})
                        if state['mesh_backend']=='idol':
                            job.update(mesh={'triangles':1,'appearance':'vertex_colors','warnings':['Dense mesh; inspect surface holes before rigging.']},files={'object.glb':'/colored-fixture.glb','source.ply':'/fixture.ply'})
                if phase == 'complete' and state['output_type'] == 'rig':
                    job.update(output_type='rig',source_job='fixture',rig={'bones':2,'triangles':1},files={'rigged.glb':'/rig-fixture.glb','rigged.fbx':'/rigged.fbx','character.blend':'/character.blend'})
                route.fulfill(json=job)

        page.route('**/api/**', api)
        page.goto(site)
        yield page, state
        assert not errors, errors
        browser.close()


def upload(page):
    image = BytesIO()
    Image.new('RGB', (32, 32), 'orange').save(image, format='PNG')
    page.locator('#image').set_input_files({'name': 'synthetic.png', 'mimeType': 'image/png', 'buffer': image.getvalue()})


def test_progress_download_and_repeated_viewer(browser_page):
    page, state = browser_page
    expect(page.locator('#generate')).to_be_disabled()
    upload(page)
    page.locator('#generate').click()
    expect(page.locator('#step-detail')).to_have_text('Sampling step 4 of 10')
    expect(page.locator('#eta')).to_contain_text('remaining')
    expect(page.locator('#generation-bar')).to_have_attribute('value', '4')
    expect(page.locator('[data-stage=sampling]')).to_have_attribute('aria-current', 'step')
    state['phase'] = 'complete'
    expect(page.locator('#busy')).to_be_hidden(timeout=20000)
    expect(page.locator('#viewer canvas')).to_have_count(1)
    expect(page.locator('#message')).to_be_hidden()
    with page.expect_download() as info:
        page.locator('#download').click()
    assert Path(info.value.path()).read_bytes().startswith(b'ply\n')
    page.locator('#generate').click()
    expect(page.locator('#busy')).to_be_hidden(timeout=20000)
    expect(page.locator('#viewer canvas')).to_have_count(1)
    assert state['submissions'] == 2
    page.set_viewport_size({'width': 390, 'height': 844})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


def assert_video(download):
    assert download.suggested_filename in ('idol-turntable.mp4', 'idol-turntable.webm')
    data = Path(download.path()).read_bytes()
    if download.suggested_filename.endswith('.mp4'):
        assert data[4:8] == b'ftyp'
    else:
        assert data.startswith(bytes.fromhex('1a45dfa3'))
    assert len(data) > 1000


def test_turntable_video_download_restores_view(browser_page):
    page, state = browser_page
    expect(page.locator('#video-download')).to_be_hidden()
    upload(page)
    state['phase'] = 'complete'
    page.locator('#generate').click()
    expect(page.locator('#busy')).to_be_hidden(timeout=20000)
    expect(page.locator('#video-download')).to_be_visible()
    page.wait_for_timeout(2000)
    before = page.locator('#viewer canvas').screenshot()
    with page.expect_download(timeout=30000) as info:
        page.locator('#video-download').click()
        expect(page.locator('#video-download')).to_be_disabled()
        expect(page.locator('#video-download')).to_contain_text('Recording')
    assert_video(info.value)
    expect(page.locator('#video-download')).to_be_enabled()
    expect(page.locator('#video-download')).to_have_text('Download video ↓')
    page.wait_for_timeout(2000)
    after = page.locator('#viewer canvas').screenshot()
    # The orbit returns the camera to its start; only splat sort order may change a few pixels slightly.
    changed = ImageChops.difference(Image.open(BytesIO(before)).convert('L'), Image.open(BytesIO(after)).convert('L'))
    assert sum(changed.histogram()[24:]) == 0
    page.locator('#output_type').select_option('mesh')
    page.locator('#mesh_backend').select_option('triposr')
    page.locator('#generate').click()
    expect(page.locator('#mesh-toolbar')).to_be_visible(timeout=20000)
    with page.expect_download(timeout=30000) as info:
        page.locator('#video-download').click()
    assert_video(info.value)


def test_failure_releases_controls_for_retry(browser_page):
    page, state = browser_page
    state['phase'] = 'error'
    upload(page)
    page.locator('#generate').click()
    expect(page.locator('#message')).to_contain_text('Synthetic GPU failure')
    expect(page.locator('#generate')).to_be_enabled()
    expect(page.locator('#download')).to_be_hidden()
    state['phase'] = 'complete'
    page.locator('#generate').click()
    expect(page.locator('#busy')).to_be_hidden(timeout=20000)
    expect(page.locator('#download')).to_be_visible()


def test_missing_model_setup_and_invalid_upload(browser_page):
    page, state = browser_page
    state['ready'] = False
    page.reload()
    expect(page.locator('#setup')).to_be_visible()
    upload(page)
    expect(page.locator('#generate')).to_be_disabled()
    page.locator('#image').set_input_files({'name': 'bad.gif', 'mimeType': 'image/gif', 'buffer': b'bad'})
    expect(page.locator('#message')).to_contain_text('PNG, JPEG, or WebP')


def test_mesh_controls_download_and_switch_back_to_splat(browser_page):
    page, state = browser_page
    page.locator('#output_type').select_option('mesh')
    page.locator('#mesh_backend').select_option('triposr')
    upload(page)
    expect(page.locator('#mode')).to_be_disabled()
    expect(page.locator('#target_faces')).to_be_enabled()
    state['phase'] = 'extract'
    page.locator('#generate').click()
    expect(page.locator('#step-detail')).to_contain_text('Surface samples')
    state['phase'] = 'complete'
    expect(page.locator('#busy')).to_be_hidden(timeout=20000)
    expect(page.locator('#mesh-toolbar')).to_be_visible()
    expect(page.locator('#result-info')).to_contain_text('512px texture')
    page.locator('#wireframe').check()
    page.locator('#reset-view').click()
    with page.expect_download() as info:
        page.locator('#download').click()
    assert Path(info.value.path()).read_bytes().startswith(b'glTF')
    page.locator('#output_type').select_option('splat')
    expect(page.locator('#target_faces')).to_be_disabled()
    page.locator('#generate').click()
    expect(page.locator('#busy')).to_be_hidden(timeout=20000)
    expect(page.locator('#viewer canvas')).to_have_count(1)
    expect(page.locator('#mesh-toolbar')).to_be_hidden()
    expect(page.locator('#download')).to_contain_text('.ply')


def test_mesh_cancel_and_missing_backend(browser_page):
    page, state = browser_page
    page.locator('#output_type').select_option('mesh')
    page.locator('#mesh_backend').select_option('triposr')
    upload(page)
    state['phase'] = 'extract'
    page.locator('#generate').click()
    expect(page.locator('#cancel')).to_be_enabled()
    page.locator('#cancel').click()
    expect(page.locator('#busy')).to_be_hidden()
    expect(page.locator('#result-info')).to_have_text('Generation cancelled.')
    expect(page.locator('#generate')).to_be_enabled()
    expect(page.locator('#cancel')).to_be_hidden()
    state['mesh_ready'] = False
    page.reload()
    page.locator('#output_type').select_option('mesh')
    page.locator('#mesh_backend').select_option('triposr')
    upload(page)
    expect(page.locator('#setup')).to_contain_text('make setup-mesh mesh-models')
    expect(page.locator('#generate')).to_be_disabled()


def rig_bytes():
    data=mesh_bytes();length=struct.unpack_from('<I',data,12)[0]
    doc=json.loads(data[20:20+length]);blob=bytearray(data[28+length:])
    def add(rows,code,kind,width):
        while len(blob)%4:blob.append(0)
        begin=len(blob)
        for row in rows:blob.extend(struct.pack('<'+code*width,*row))
        view=len(doc['bufferViews']);doc['bufferViews'].append({'buffer':0,'byteOffset':begin,'byteLength':len(blob)-begin})
        index=len(doc['accessors']);doc['accessors'].append({'bufferView':view,'componentType':5126 if code=='f' else 5123,'type':kind,'count':len(rows)})
        return index
    joints=add([(0,1,0,0)]*3,'H','VEC4',4)
    weights=add([(1,0,0,0),(.5,.5,0,0),(0,1,0,0)],'f','VEC4',4)
    bind=add([(1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1),(1,0,0,0,0,1,0,0,0,0,1,0,0,-.5,0,1)],'f','MAT4',16)
    times=add([(0,),(.625,),(1.25,)],'f','SCALAR',1)
    doc['accessors'][times].update(min=[0],max=[1.25])
    rotations=add([(0,0,0,1),(math.sin(.125),0,0,math.cos(.125)),(0,0,0,1)],'f','VEC4',4)
    doc['nodes']=[{'mesh':0,'skin':0},{'name':'root','children':[2]},{'name':'bend','translation':[0,.5,0]}]
    doc['scenes']=[{'nodes':[0,1]}]
    doc['skins']=[{'joints':[1,2],'inverseBindMatrices':bind}]
    doc['meshes'][0]['primitives'][0]['attributes'].update(JOINTS_0=joints,WEIGHTS_0=weights)
    doc['animations']=[{'name':'Diagnostic bend','samplers':[{'input':times,'output':rotations,'interpolation':'LINEAR'}],
                        'channels':[{'sampler':0,'target':{'node':2,'path':'rotation'}}]}]
    doc['buffers'][0]['byteLength']=len(blob)
    encoded=json.dumps(doc).encode();encoded+=b' '*(-len(encoded)%4);blob+=bytes(-len(blob)%4)
    chunks=struct.pack('<I4s',len(encoded),b'JSON')+encoded+struct.pack('<I4s',len(blob),b'BIN\0')+blob
    return struct.pack('<4sII',b'glTF',2,len(chunks)+12)+chunks


def test_experimental_rig_controls_progress_animation_and_exports(browser_page):
    page,state=browser_page
    page.locator('#output_type').select_option('mesh')
    upload(page);page.locator('#generate').click()
    state['phase']='complete'
    expect(page.locator('#auto-rig')).to_be_enabled(timeout=20000)
    page.locator('#auto-rig').click()
    expect(page.locator('#progress')).to_contain_text('Generating synthetic fixture')
    expect(page.locator('[data-stage="skeleton"]')).to_have_attribute('aria-current','step')
    expect(page.locator('#cancel')).to_be_enabled()
    state['phase']='complete'
    expect(page.locator('#busy')).to_be_hidden(timeout=20000)
    expect(page.locator('#result-info')).to_contain_text('2 bones')
    expect(page.locator('#skeleton-control')).to_be_visible()
    expect(page.locator('#bend-control')).to_be_visible()
    page.locator('#skeleton').check();page.locator('#bend').check()
    page.wait_for_timeout(500)
    page.locator('#bend').uncheck();page.locator('#reset-view').click()
    expect(page.locator('#fbx-download')).to_have_attribute('href','/rigged.fbx')
    expect(page.locator('#blend-download')).to_have_attribute('href','/character.blend')
    expect(page.locator('#static-download')).to_have_attribute('href','/outputs/fixture/object.glb')
    expect(page.locator('#viewer canvas')).to_have_count(1)
    page.locator('#output_type').select_option('splat');page.locator('#generate').click()
    expect(page.locator('#busy')).to_be_hidden(timeout=20000)
    expect(page.locator('#rig-exports')).to_be_hidden()
    expect(page.locator('#rig-actions')).to_be_hidden()
    expect(page.locator('#viewer canvas')).to_have_count(1)


def colored_bytes():
    data=mesh_bytes();length=struct.unpack_from('<I',data,12)[0]
    doc=json.loads(data[20:20+length]);blob=bytearray(data[28+length:])
    while len(blob)%4:blob.append(0)
    begin=len(blob);blob.extend(struct.pack('<12f',*([.3,.15,.05,1]*3)))
    view=len(doc['bufferViews']);doc['bufferViews'].append({'buffer':0,'byteOffset':begin,'byteLength':48})
    accessor=len(doc['accessors']);doc['accessors'].append({'bufferView':view,'componentType':5126,'type':'VEC4','count':3})
    attrs=doc['meshes'][0]['primitives'][0]['attributes'];attrs.pop('TEXCOORD_0');attrs['COLOR_0']=accessor
    doc.pop('images');doc.pop('textures')
    doc['materials']=[{'doubleSided':True,'extensions':{'KHR_materials_unlit':{}},'pbrMetallicRoughness':{}}]
    doc['extensionsUsed']=['KHR_materials_unlit'];doc['buffers'][0]['byteLength']=len(blob)
    encoded=json.dumps(doc).encode();encoded+=b' '*(-len(encoded)%4)
    chunks=struct.pack('<I4s',len(encoded),b'JSON')+encoded+struct.pack('<I4s',len(blob),b'BIN\0')+blob
    return struct.pack('<4sII',b'glTF',2,len(chunks)+12)+chunks


def test_default_mesh_uses_idol_and_reports_real_view_and_depth_counts(browser_page):
    page,state=browser_page
    page.locator('#output_type').select_option('mesh')
    expect(page.locator('#mesh_backend')).to_have_value('idol')
    expect(page.locator('#mode')).to_be_enabled()
    expect(page.locator('#target_faces')).to_be_disabled()
    expect(page.locator('#surface_quality')).to_be_enabled()
    upload(page);state['phase']='capture';page.locator('#generate').click()
    expect(page.locator('#step-detail')).to_contain_text('Rendered image')
    expect(page.locator('#saved-result')).to_be_disabled()
    state['phase']='stereo'
    expect(page.locator('#step-detail')).to_contain_text('Depth pair')
    state['phase']='complete'
    expect(page.locator('#busy')).to_be_hidden(timeout=20000)
    expect(page.locator('#result-badge')).to_have_text('SPLAT-DERIVED MESH')
    expect(page.locator('#result-info')).to_contain_text('vertex colors')
    expect(page.locator('#mesh-warnings')).to_contain_text('surface holes')
    expect(page.locator('#source-download')).to_be_visible()
    expect(page.locator('#viewer canvas')).to_have_count(1)


def test_saved_splat_converts_without_new_image_or_regeneration(browser_page):
    page,state=browser_page
    state['saved']=[{'id':'fixture','output_type':'splat','started_at':1}]
    state['phase']='complete';page.reload()
    page.locator('#saved-result').select_option('fixture')
    expect(page.locator('#convert-mesh')).to_be_enabled(timeout=20000)
    assert state['submissions']==0
    page.locator('#convert-mesh').click()
    expect(page.locator('#step-detail')).to_contain_text('Rendered image')
    expect(page.locator('#cancel')).to_be_enabled()
    state['phase']='complete'
    expect(page.locator('#busy')).to_be_hidden(timeout=20000)
    expect(page.locator('#result-info')).to_contain_text('vertex colors')
    assert state['conversions']==1 and state['submissions']==0


def test_default_mesh_missing_setup_is_independent_from_legacy_mesh(browser_page):
    page,state=browser_page
    state['stereo_ready']=False;page.reload()
    page.locator('#output_type').select_option('mesh');upload(page)
    expect(page.locator('#generate')).to_be_disabled()
    expect(page.locator('#setup')).to_contain_text('make setup-splat-mesh splat-mesh-models')
    page.locator('#mesh_backend').select_option('triposr')
    expect(page.locator('#generate')).to_be_enabled()
