import unittest
from gpu_smoke import validate_ply

class PlyTests(unittest.TestCase):
    def test_valid_records_and_truncation(self):
        header = b"ply\nformat binary_little_endian 1.0\nelement vertex 2\nproperty float x\nend_header\n"
        self.assertEqual(2, validate_ply(header + bytes(8), expected_count=2))
        with self.assertRaises(ValueError):
            validate_ply(header + bytes(4), expected_count=2)
        with self.assertRaises(ValueError):
            validate_ply(header + bytes(8), expected_count=3)
