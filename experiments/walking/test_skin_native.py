"""Numerical transfer tests in the locked UniRig environment (NumPy/Open3D/SciPy)."""
import os
import sys
import unittest
import numpy as np
from experiments.walking.skin import fit_similarity, transfer_weights


class ContinuousTransfer(unittest.TestCase):
    def test_known_similarity_and_invalid_joint_correspondence(self):
        source=np.array([[0,0,0],[1,0,0],[0,1,0],[0,0,1]],float)
        rotation=np.array([[0,-1,0],[1,0,0],[0,0,1]])
        target=source@rotation*2+[3,4,5]
        scale,r,shift,error=fit_similarity(source,target)
        np.testing.assert_allclose(source@r*scale+shift,target,atol=1e-6)
        self.assertLess(error,1e-6)
        for bad in (target[:2],target*np.array([-1,1,1]),target+np.array([[0,0,0],[0,0,0],[0,0,0],[1,2,3]])):
            with self.assertRaises(ValueError):fit_similarity(source,bad)

    def test_barycentric_field_is_continuous_across_shared_edge(self):
        vertices=np.array([[0,0,0],[1,0,0],[0,1,0],[1,1,0]],float)
        faces=np.array([[0,1,2],[1,3,2]])
        weights=np.array([[1,0],[0,1],[1,0],[0,1]],float)
        points=np.array([[.5,.5-1e-5,.1],[.5,.5+1e-5,.1],[.25,.1,0]])
        result,report=transfer_weights(vertices,faces,weights,points,steps=0)
        np.testing.assert_allclose(result,[[.5,.5],[.5,.5],[.75,.25]],atol=1e-5)
        self.assertLess(abs(report['distance_p95']-.1),1e-5)
        many,_=transfer_weights(vertices,faces,np.full((4,6),1/6),points,steps=0)
        self.assertTrue(np.all((many>0).sum(1)<=4));np.testing.assert_allclose(many.sum(1),1,atol=1e-6)
        smoothed,_=transfer_weights(vertices,faces,weights,points,steps=4)
        self.assertTrue(np.isfinite(smoothed).all())
        np.testing.assert_allclose(smoothed.sum(1),1,atol=1e-6)

    def test_rejects_invalid_geometry_and_unweighted_source(self):
        v=np.array([[0,0,0],[1,0,0],[0,1,0]],float);f=np.array([[0,1,2]]);w=np.ones((3,1))
        for faces,weights,points,steps in [(f,np.zeros_like(w),v,0),(np.array([[0,1,9]]),w,v,0),(f,w,v*float('nan'),0),(f,w,v,-1),(f,w,v,129)]:
            with self.assertRaises(ValueError):transfer_weights(v,faces,weights,points,steps=steps)


if __name__=='__main__':
    result=unittest.main(exit=False).result
    sys.stdout.flush();sys.stderr.flush();os._exit(0 if result.wasSuccessful() else 1)
