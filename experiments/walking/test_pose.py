import math
import pytest
from experiments.walking.pose import validate_mapping, sagittal_rotation, summarize_stretch


def test_mapping_rejects_partial_unknown_and_repeated_assignments():
    entry={'target':'leg','source':'knee'}
    assert validate_mapping([entry],{'leg'},{'knee'})==[entry]
    for rows in ([entry,entry],[{'target':'missing','source':'knee'}],[{'target':'leg','source':'missing'}],[]):
        with pytest.raises(ValueError):validate_mapping(rows,{'leg'},{'knee'})
    with pytest.raises(ValueError):validate_mapping([{**entry,'degrees':float('nan')}],{'leg'},{'knee'})


def test_rotation_respects_x_forward_z_up_and_rejects_unusable_vectors():
    assert sagittal_rotation((1,0,0),(0,0,-1))==pytest.approx(math.pi/2)
    assert sagittal_rotation((1,0,1),(1,0,0))==pytest.approx(math.pi/4)
    for vector in ((0,1,0),(float('nan'),0,1)):
        with pytest.raises(ValueError):sagittal_rotation(vector,(1,0,0))


def test_deformation_summary_distinguishes_rigid_motion_from_stretch():
    report=summarize_stretch([1,1,1,1]);assert report['over_2_fraction']==0 and report['p95']==1
    report=summarize_stretch([1,1,2,4]);assert report['over_2_fraction']==.25 and report['p95']>3
    for values in ([],[float('inf')],[-1]):
        with pytest.raises(ValueError):summarize_stretch(values)
