"""One bounded mesh phase; Chromium descendants are explicitly cleaned on cancellation."""
from argparse import ArgumentParser,Namespace
import hashlib
import json
import os
from pathlib import Path
import signal
import sys
import traceback

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
children=[]


def emit(stage,message,**values):
    print('IDOL_EVENT '+json.dumps({'event':'progress','stage':stage,'message':message,**values}),flush=True)


def cancelled(signum,frame):
    import psutil
    children.extend(psutil.Process().children(recursive=True))
    raise SystemExit('Splat-mesh phase cancelled')


def cleanup():
    import psutil
    processes={item.pid:item for item in [*children,*psutil.Process().children(recursive=True)]}
    for item in processes.values():
        try:item.terminate()
        except psutil.NoSuchProcess:pass
    _,alive=psutil.wait_procs(list(processes.values()),timeout=2)
    for item in alive:
        try:item.kill()
        except psutil.NoSuchProcess:pass
    psutil.wait_procs(alive,timeout=2)


def main():
    parser=ArgumentParser(description=__doc__)
    parser.add_argument('--phase',choices=['capture','stereo','surface','export'],required=True)
    parser.add_argument('--job',type=Path,required=True);parser.add_argument('--models',type=Path,required=True)
    args=parser.parse_args();folder=args.job.resolve();models=args.models.resolve()
    settings=json.loads((folder/'mesh-settings.json').read_text())
    if args.phase=='capture':
        from experiments.splat_mesh.render_views import capture_views
        capture_views(Namespace(splat=folder/'source.ply',output=folder/'views',base_url='http://splat-mesh.local/',withheld=False),
                      lambda step,total:emit('capture',f'Rendering image {step} of {total}…',step=step,total_steps=total))
    elif args.phase=='stereo':
        from splat_mesh_setup import CHECKPOINT_SHA256
        checkpoint=models/'DLNR_Middlebury.pth'
        if hashlib.sha256(checkpoint.read_bytes()).hexdigest()!=CHECKPOINT_SHA256:raise RuntimeError('Stereo model checksum mismatch; rerun setup.')
        from experiments.splat_mesh.reconstruct import reconstruct
        reconstruct(Namespace(views=folder/'views',output=folder/'depth',method='dlnr',source=models/'source',
                              checkpoint=checkpoint,limit=0,iters=10,voxel=.004,status_url=''),
                    lambda step,total:emit('stereo',f'Recovering depth {step} of {total}…',step=step,total_steps=total))
    elif args.phase=='surface':
        from experiments.splat_mesh.refine import refine
        refine(Namespace(views=folder/'views',depths=folder/'depth',output=folder/'surface-result',
                         voxel=.002 if settings['surface_quality']=='fine' else .004,
                         minimum_component=1,largest_component=settings['component_mode']=='largest'))
    else:
        import shutil
        from mesh_runtime import validate_glb
        result=folder/'surface-result'
        details=validate_glb((result/'mesh.glb').read_bytes())
        shutil.copy2(result/'mesh.glb',folder/'object.glb')
        shutil.copy2(result/'raw.ply',folder/'raw-mesh.ply')
        surface=json.loads((result/'report.json').read_text());depth=json.loads((folder/'depth/report.json').read_text())
        warnings=['Dense reconstructed mesh; inspect surface holes, anatomy and topology before game use.']
        if settings['component_mode']=='largest':warnings.append('Only the largest connected subject was retained; detached parts may be omitted.')
        report={**details,'backend':'idol-splat','rigged':False,'up_axis':'Y','watertight':surface['watertight'],
                'voxel':surface['voxel'],'removed_triangles':surface['removed_small_fragment_triangles'],
                'gpu':depth['gpu'],'peak_allocated_mib':depth['peak_allocated_mib'],'warnings':warnings}
        (folder/'mesh.json').write_text(json.dumps(report,indent=2))


if __name__=='__main__':
    signal.signal(signal.SIGTERM,cancelled)
    print('IDOL_EVENT '+json.dumps({'event':'started','pid':os.getpid()}),flush=True)
    try:main()
    except BaseException as error:
        traceback.print_exc(file=sys.stderr)
        message='GPU ran out of memory during stereo recovery.' if 'out of memory' in str(error).lower() else str(error)
        print('IDOL_EVENT '+json.dumps({'event':'error','message':message[:1000]}),flush=True)
        code=1
    else:code=0
    finally:cleanup()
    raise SystemExit(code)
