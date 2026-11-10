"""Camera conventions and physical stereo checks, independent of GPU dependencies."""
import math


def stereo_depth(disparity, reverse, x, focal, baseline, *, min_depth, max_depth, tolerance=1.5):
    if not all(math.isfinite(v) for v in (disparity, reverse, focal, baseline)) or disparity <= 0 or reverse <= 0:
        return 0
    if x - disparity < 0 or abs(disparity - reverse) > tolerance:
        return 0
    depth = focal * baseline / disparity
    return depth if min_depth <= depth <= max_depth else 0


def cv_extrinsic(matrix):
    """Three.js column-major camera-to-world -> OpenCV world-to-camera (right/down/forward)."""
    if len(matrix) != 16 or not all(math.isfinite(value) for value in matrix):
        raise ValueError('Invalid camera matrix')
    position = matrix[12:15]
    rotation = [[matrix[column * 4 + row] * (1 if column == 0 else -1)
                 for row in range(3)] for column in range(3)]
    return [row + [-sum(row[i] * position[i] for i in range(3))] for row in rotation] + [[0,0,0,1]]


def project(point, extrinsic, focal, cx, cy):
    x,y,z = [sum(row[i]*point[i] for i in range(3))+row[3] for row in extrinsic[:3]]
    if z <= 0:raise ValueError('Point is behind the camera')
    return focal*x/z+cx, focal*y/z+cy, z
