#!/usr/bin/env python3
"""Bootstrap the project: create venv, install deps, update feeds and rebuild cache.

Usage: python bootstrap.py [--no-dev] [--no-update] [--venv-dir venv]
"""
import argparse
import subprocess
import sys
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def run(cmd, **kwargs):
    print('>', ' '.join(cmd))
    subprocess.check_call(cmd, **kwargs)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--no-dev', action='store_true', help='Skip installing dev dependencies')
    parser.add_argument('--no-update', action='store_true', help='Skip updating feeds and rebuilding cache')
    parser.add_argument('--venv-dir', default='venv')
    args = parser.parse_args()

    venv_dir = ROOT / args.venv_dir
    python_cmd = sys.executable

    # Create venv if missing
    if not venv_dir.exists():
        run([python_cmd, '-m', 'venv', str(venv_dir)])

    # Activation varies by platform; call pip via venv's python directly
    venv_python = str(venv_dir / ('Scripts' if os.name == 'nt' else 'bin') / 'python')

    run([venv_python, '-m', 'pip', 'install', '--upgrade', 'pip'])
    run([venv_python, '-m', 'pip', 'install', '-r', str(ROOT / 'requirements.txt')])
    # Ensure optional convenience packages like keyring are present (best-effort)
    try:
        run([venv_python, '-m', 'pip', 'install', 'keyring'])
    except Exception:
        print('Warning: failed to install keyring in venv; GUI keyring support may be unavailable.')
    # Install dev requirements if requested and the file exists. If there is no
    # requirements-dev.txt (we consolidated dev deps into requirements.txt), skip
    # gracefully. CI sets --no-dev by default.
    dev_reqs = ROOT / 'requirements-dev.txt'
    if not args.no_dev:
        if dev_reqs.exists():
            run([venv_python, '-m', 'pip', 'install', '-r', str(dev_reqs)])
        else:
            print('No requirements-dev.txt found; skipping dev dependencies installation.')

    if not args.no_update:
        run([venv_python, str(ROOT / 'update_blacklists.py'), '--rebuild-cache', '--no-download'])

    # Run a sample analysis
    run([venv_python, str(ROOT / 'main.py'), 'sample_headers/phishing_sample.txt', '--no-update'])

    print('\nBootstrap complete. To re-run analyzer:')
    print(f'  {venv_python} main.py sample_headers/phishing_sample.txt --no-update')


if __name__ == '__main__':
    main()
