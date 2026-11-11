"""Container/locked browser consistency regressions; no Docker or network calls."""
import unittest
from browser_image import check_image


class ImageTests(unittest.TestCase):
    def test_digest_pinned_image_matches_locked_package(self):
        image = 'mcr.microsoft.com/playwright/python:v1.65.0-noble@sha256:' + 'a' * 64
        lock = {'package': [{'name':'playwright', 'version':'1.65.0'}]}
        self.assertEqual(check_image('container:\n  image: '+image+'\n', lock), '1.65.0')

    def test_mutable_wrong_registry_and_mismatched_images_fail(self):
        lock = {'package': [{'name':'playwright', 'version':'1.65.0'}]}
        for image in ['mcr.microsoft.com/playwright/python:v1.65.0-noble',
                      'mcr.microsoft.com/playwright/python:latest',
                      'other.example/playwright/python:v1.65.0-noble@sha256:'+'a'*64,
                      'mcr.microsoft.com/playwright/python:v1.64.0-noble@sha256:'+'a'*64]:
            with self.subTest(image=image), self.assertRaises(ValueError):
                check_image('image: '+image+'\n', lock)

    def test_missing_or_ambiguous_locked_versions_fail(self):
        workflow = 'image: mcr.microsoft.com/playwright/python:v1.65.0-noble@sha256:'+'a'*64+'\n'
        for lock in [{}, {'package':[]}, {'package':[{'name':'playwright','version':'1.64.0'}, {'name':'playwright','version':'1.65.0'}]}]:
            with self.assertRaises(ValueError):
                check_image(workflow, lock)
        with self.assertRaises(ValueError):
            check_image('no browser container', {'package':[{'name':'playwright','version':'1.65.0'}]})


if __name__ == '__main__':
    unittest.main()
