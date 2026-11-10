"""Download pinned public model files, including their license/provenance notes."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from huggingface_hub import snapshot_download

MODEL_ROOT = Path(__file__).resolve().parent / "models"
SOURCES = {
    "idol": {
        "repo": "speridlabs/idol",
        "revision": "2731c2291fc65a797c5cb627a5e5526fc1490902",
        "files": ["config.json", "denoiser.safetensors", "decoder.safetensors",
                  "decoder_gs.safetensors", "birefnet.safetensors", "README.md", "LICENSE*"],
        "required": ["config.json", "denoiser.safetensors", "decoder.safetensors",
                     "decoder_gs.safetensors", "birefnet.safetensors"],
    },
    "dinov3": {
        "repo": "LibreYOLO/LibreDINOv3vith16plus",
        "revision": "e849a3492905c6dabc89758042bf1402770fb4e6",
        "files": ["config.json", "model.safetensors", "preprocessor_config.json", "README.md", "LICENSE", "NOTICE"],
        "required": ["config.json", "model.safetensors", "LICENSE", "NOTICE"],
    },
    "flux2-vae": {
        "repo": "black-forest-labs/FLUX.2-klein-4B",
        "revision": "e7b7dc27f91deacad38e78976d1f2b499d76a294",
        "files": ["vae/*", "README.md", "LICENSE*"],
        "required": ["vae/config.json", "vae/diffusion_pytorch_model.safetensors"],
    },
}


def models_ready():
    return all(
        (MODEL_ROOT / name / ".download-complete").is_file()
        and (MODEL_ROOT / name / ".download-complete").read_text() == source["revision"]
        and all((MODEL_ROOT / name / file).is_file() for file in source["required"])
        for name, source in SOURCES.items()
    )


def download_model(name):
    source = SOURCES[name]
    directory = MODEL_ROOT / name
    marker = directory / ".download-complete"
    if marker.is_file() and marker.read_text() == source["revision"] and all(
        (directory / file).is_file() for file in source["required"]
    ):
        return
    print(f'Downloading {source["repo"]} → {directory}', flush=True)
    snapshot_download(
        source["repo"], revision=source["revision"],
        allow_patterns=source["files"], local_dir=directory, max_workers=3,
    )
    marker.write_text(source["revision"])
    print(f'{name}: ready', flush=True)


def ensure_models():
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(download_model, SOURCES))
    return str(MODEL_ROOT / "idol"), {
        "dinov3": str(MODEL_ROOT / "dinov3"),
        "flux2_vae": str(MODEL_ROOT / "flux2-vae"),
    }


if __name__ == "__main__":
    ensure_models()
    print("All model files are ready. No Hugging Face login is required.")
