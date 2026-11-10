import math
import pytest


def test_stereo_depth_known_parallel_camera_plane_and_invalid_observations():
    from experiments.splat_mesh.geometry import stereo_depth
    assert stereo_depth(32,32,100,640,.1,min_depth=.5,max_depth=3)==pytest.approx(2)
    assert stereo_depth(32,12,100,640,.1,min_depth=.5,max_depth=3) == 0
    assert stereo_depth(32,32,10,640,.1,min_depth=.5,max_depth=3) == 0
    for value in [0,-2,float('nan'),float('inf')]:
        assert stereo_depth(value,32,100,640,.1,min_depth=.5,max_depth=3)==0


def test_three_camera_to_cv_world_projection_and_baseline():
    from experiments.splat_mesh.geometry import cv_extrinsic,project
    matrix=[1,0,0,0,0,1,0,0,0,0,1,0,0,0,1.5,1]
    left=cv_extrinsic(matrix)
    assert project([0,0,0],left,600,256,256)==pytest.approx((256,256,1.5))
    right_matrix=matrix.copy();right_matrix[12]=.08
    right=cv_extrinsic(right_matrix)
    assert project([0,0,0],right,600,256,256)==pytest.approx((224,256,1.5))
    assert project([0,.1,0],left,600,256,256)[1] <256
    assert math.isclose(project([0,0,0],left,600,256,256)[0]-project([0,0,0],right,600,256,256)[0],600*.08/1.5)


def test_calibration_preserves_the_apps_negative_y_up_convention():
    from experiments.splat_mesh.geometry import cv_extrinsic,project
    matrix=[-1,0,0,0,0,-1,0,0,0,0,1,0,0,0,1.5,1]
    extrinsic=cv_extrinsic(matrix)
    assert project([.1,0,0],extrinsic,600,256,256)[0]==pytest.approx(216)
    assert project([0,.1,0],extrinsic,600,256,256)[1]==pytest.approx(296)
    with pytest.raises(ValueError):cv_extrinsic([0]*15)
    with pytest.raises(ValueError):project([0,0,2],extrinsic,600,256,256)
