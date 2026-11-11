"""Verify the official CI browser image pin matches the locked Python package."""
import argparse
from importlib.metadata import version
from pathlib import Path
import re
import tomllib

IMAGE = re.compile(r'mcr\.microsoft\.com/playwright/python:v(\d+\.\d+\.\d+)-noble@sha256:[0-9a-f]{64}')


def check_image(workflow, lock):
    versions = {item.get('version') for item in lock.get('package', []) if item.get('name') == 'playwright'}
    if len(versions) != 1 or not all(isinstance(value, str) for value in versions):
        raise ValueError('Exactly one locked Playwright version is required.')
    expected = versions.pop()
    images = [value.strip('\'"') for value in re.findall(r'^\s*image:\s*(\S+)', workflow, re.MULTILINE) if 'playwright' in value]
    if not images:
        raise ValueError('Missing official digest-pinned Playwright browser image.')
    for image in images:
        match = IMAGE.fullmatch(image)
        if not match or match.group(1) != expected:
            raise ValueError('Pin the official Playwright Python image by digest and match the uv.lock Playwright version.')
    return expected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', action='store_true', help='Also verify the installed package and bundled Chromium executable')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    expected = check_image((root/'.github/workflows/ci.yml').read_text(), tomllib.loads((root/'uv.lock').read_text()))
    if args.runtime:
        if version('playwright') != expected:
            raise SystemExit('Installed Playwright differs from the pinned browser image.')
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            executable = Path(playwright.chromium.executable_path)
            if not executable.is_relative_to('/ms-playwright') or not executable.is_file():
                raise SystemExit('Bundled Chromium executable is missing from the browser image.')
    print(f'Official browser image matches locked Playwright {expected}; full browser tests remain required.')


if __name__ == '__main__':
    main()
