"""Cancellable one-job Idol generation for a combined image-to-mesh job."""
import argparse
import json
import os
from pathlib import Path
import sys
import traceback

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True);parser.add_argument('--job',type=Path,required=True)
    args=parser.parse_args()
    from model_setup import ensure_models,models_ready
    from progress import GenerationProgress,instrument_pipeline
    import torch
    from idol import IdolPipeline
    if not models_ready():raise RuntimeError('Download the Idol assets with make models before mesh generation.')
    if not torch.cuda.is_available():raise RuntimeError('CUDA is unavailable in the Idol environment.')
    settings=json.loads((args.job/'mesh-settings.json').read_text())
    options={key:settings[key] for key in ('mode','steps','seed','num_gaussians','cfg_strength','rescale_t')}
    def emit(**event):
        print('IDOL_EVENT '+json.dumps({'event':'progress',**event}),flush=True)
    progress=GenerationProgress(options,emit,args.job/'.idol-timings.json',cold=True,optimize=False)
    progress.start('load')
    weights,encoders=ensure_models()
    model=IdolPipeline.from_pretrained(weights,device='cuda',image_encoders=encoders,optimize=os.environ.get('IDOL_OPTIMIZE','0')=='1')
    torch.cuda.reset_peak_memory_stats()
    with instrument_pipeline(model,progress,torch.cuda.synchronize):result=model(str(args.input),**options)
    progress.start('save')
    result.gaussian.save_ply(str(args.job/'source.ply'))
    result.preprocessed_image.save(args.job/'prepared.png')
    (args.job/'camera.json').write_text(json.dumps(result.camera,indent=2))
    (args.job/'idol.json').write_text(json.dumps({'gpu':torch.cuda.get_device_name(0),'torch':torch.__version__,
                              'peak_allocated_mib':round(torch.cuda.max_memory_allocated()/2**20),**progress.finish()},indent=2))


if __name__=='__main__':
    try:main()
    except Exception as error:
        traceback.print_exc(file=sys.stderr)
        message='GPU ran out of memory. Lower the Gaussian count and retry.' if 'out of memory' in str(error).lower() else str(error)
        print('IDOL_EVENT '+json.dumps({'event':'error','message':message[:1000]}),flush=True)
        raise SystemExit(1)
