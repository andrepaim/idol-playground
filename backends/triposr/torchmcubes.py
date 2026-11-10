"""CPU marching-cubes compatibility for the pinned TripoSR isosurface helper.

The neural field is evaluated on CUDA. PyMCubes extracts its zero surface on
CPU, then TripoSR moves the resulting geometry back to its original device.
No torchmcubes CUDA extension or system CUDA compiler is required.
"""
import mcubes
import numpy as np
import torch

HAS_CUDA = False


def marching_cubes(volume, threshold):
    data = volume.detach().float().cpu().numpy()
    if not np.isfinite(data).all() or not data.min() < threshold < data.max():
        raise ValueError('No usable surface was found in the predicted density field.')
    vertices, faces = mcubes.marching_cubes(data, threshold)
    if not len(faces):
        raise ValueError('No usable surface was found in the predicted density field.')
    # Native torchmcubes reports Z/Y/X; the pinned upstream helper reverses it.
    return torch.from_numpy(vertices[:, [2, 1, 0]].copy()).float(), torch.from_numpy(faces.astype(np.int64))
