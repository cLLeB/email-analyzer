#!/usr/bin/env python3
"""Central tool to run common tasks with one command.

Usage: python tool.py <command> [args]

Commands:
  setup         Create venv, install deps, rebuild cache, run sample analysis
  run <file>    Run analyzer on a header file (uses project venv if present)
  update        Update all feeds and rebuild cache
  update-feed   Update a single feed: --name <feedname> [--feeds-file <path>]
  list-feeds    Print feed mapping and resolved local paths
  stats         Print per-feed CIDR counts
  test          Run pytest
  help          Show help
"""
import argparse
import subprocess
import sys
from pathlib import Path
import os
import urllib.request
import tarfile
import tempfile
import shutil

ROOT = Path(__file__).resolve().parent


def run(cmd, check=True):
    print('>', ' '.join(cmd))
    return subprocess.run(cmd, check=check)


def ensure_venv_python(venv_dir='venv'):
    venv = ROOT / venv_dir
    if venv.exists():
        py = venv / ('Scripts' if sys.platform == 'win32' else 'bin') / 'python'
        return str(py)
    return sys.executable


def cmd_setup(args):
    parser = argparse.ArgumentParser()
    parser.add_argument('--download-feeds', action='store_true', help='Download blacklist feeds and rebuild cache')
    parser.add_argument('--geoip-url', help='Direct URL to GeoLite2 mmdb or tar.gz to download')
    parser.add_argument('--geoip-dest', default=str(ROOT / 'data' / 'GeoLite2-City.mmdb'),
                        help='Destination path for GeoIP DB')
    parser.add_argument('--maxmind-license',
                        help='MaxMind license key to download GeoLite2-City (will download tar.gz and extract)')
    parsed = parser.parse_args(args)

    # Run bootstrap using venv python if available
    py = ensure_venv_python()
    ret = run([py, str(ROOT / 'bootstrap.py')])
    if ret.returncode != 0:
        return ret

    # Optionally download feeds and rebuild cache
    if parsed.download_feeds:
        print('Downloading blacklist feeds and rebuilding cache...')
        rc = cmd_update([])
        if rc and hasattr(rc, 'returncode'):
            if rc.returncode != 0:
                print('Feed update failed')
                return rc

    # Optionally download GeoIP DB. Support reading license from env var MAXMIND_LICENSE_KEY
    # If user didn't pass flags but an env var is present and the DB is missing, try to fetch it.
    env_license = os.environ.get('MAXMIND_LICENSE_KEY')
    if not parsed.geoip_url and not parsed.maxmind_license and env_license:
        parsed.maxmind_license = env_license
        print('Using MaxMind license from environment variable MAXMIND_LICENSE_KEY')

    dest = Path(parsed.geoip_dest)
    if (parsed.geoip_url or parsed.maxmind_license) or (not dest.exists() and os.environ.get('MAXMIND_LICENSE_KEY')):
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            if parsed.geoip_url:
                print(f'Downloading GeoIP DB from {parsed.geoip_url} to {dest}')
                _download_and_save(parsed.geoip_url, dest)
            else:
                # Build MaxMind download URL for GeoLite2-City tar.gz
                lm = parsed.maxmind_license or os.environ.get('MAXMIND_LICENSE_KEY')
                if not lm:
                    raise RuntimeError('No MaxMind license key available')
                url = f'https://download.maxmind.com/app/geoip_download?edition_id=GeoLite2-City&license_key={lm}&suffix=tar.gz'
                print(f'Downloading GeoIP DB from MaxMind using license key to {dest}')
                _download_and_save(url, dest, extract_mmdb=True)
        except Exception as e:
            print('Failed to download GeoIP DB:', e)
            return 1

    return ret


def _download_and_save(url, dest_path: Path, extract_mmdb: bool = False):
    """Download a file from url and save to dest_path. If extract_mmdb is True and
    the download is a tar.gz, extract the .mmdb file inside and save it to dest_path."""
    tmpfd, tmpname = tempfile.mkstemp()
    os.close(tmpfd)
    try:
        print('Fetching', url)
        urllib.request.urlretrieve(url, tmpname)
        # If we should extract an mmdb from tar.gz
        if extract_mmdb or tarfile.is_tarfile(tmpname):
            with tarfile.open(tmpname, 'r:gz') as tf:
                mmdb_members = [m for m in tf.getmembers() if m.name.endswith('.mmdb')]
                if not mmdb_members:
                    raise RuntimeError('No .mmdb file found in archive')
                # extract the first mmdb member to dest_path
                with tf.extractfile(mmdb_members[0]) as mmdb_file:
                    with open(dest_path, 'wb') as out_f:
                        shutil.copyfileobj(mmdb_file, out_f)
        else:
            # Not an archive: move to dest
            shutil.move(tmpname, str(dest_path))
            tmpname = None
        print('Saved GeoIP DB to', dest_path)
    finally:
        if tmpname and os.path.exists(tmpname):
            os.remove(tmpname)


def cmd_run(args):
    if not args:
        print('Usage: tool.py run <header_file>')
        return 2
    py = ensure_venv_python()
    return run([py, str(ROOT / 'main.py')] + args)


def cmd_update(args):
    py = ensure_venv_python()
    return run([py, str(ROOT / 'update_blacklists.py'), '--rebuild-cache'] + args)


def cmd_update_feed(args):
    parser = argparse.ArgumentParser()
    parser.add_argument('--name', required=True)
    parser.add_argument('--feeds-file')
    parsed = parser.parse_args(args)
    cmd = [sys.executable, str(ROOT / 'update_blacklists.py')]
    if parsed.feeds_file:
        cmd += ['--feeds-file', parsed.feeds_file]
    cmd += ['--feed', parsed.name]
    return run(cmd)


def cmd_list_feeds(args):
    cmd = [sys.executable, str(ROOT / 'update_blacklists.py'), '--list-feeds']
    if args:
        cmd += args
    return run(cmd)


def cmd_stats(args):
    cmd = [sys.executable, str(ROOT / 'update_blacklists.py'), '--stats']
    if args:
        cmd += args
    return run(cmd)


def cmd_test(args):
    # ensure deps installed then run pytest
    run([sys.executable, '-m', 'pip', 'install', '-r', str(ROOT / 'requirements.txt')])
    return run([sys.executable, '-m', 'pytest', '-q'])


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    cmd = sys.argv[1]
    args = sys.argv[2:]
    if cmd == 'setup':
        sys.exit(cmd_setup(args).returncode)
    if cmd == 'run':
        sys.exit(cmd_run(args).returncode)
    if cmd == 'update':
        sys.exit(cmd_update(args).returncode)
    if cmd == 'gui':
        # Launch the minimal GUI (keeps CLI as primary entrypoint)
        try:
            # Import here to avoid requiring Tkinter for pure-CLI runs
            from gui import main as gui_main
            gui_main()
            sys.exit(0)
        except Exception as e:
            print('Failed to launch GUI:', e)
            sys.exit(1)
    if cmd == 'update-feed':
        sys.exit(cmd_update_feed(args).returncode)
    if cmd == 'list-feeds':
        sys.exit(cmd_list_feeds(args).returncode)
    if cmd == 'stats':
        sys.exit(cmd_stats(args).returncode)
    if cmd == 'test':
        sys.exit(cmd_test(args).returncode)
    print('Unknown command', cmd)
    print(__doc__)
    sys.exit(2)


if __name__ == '__main__':
    main()
