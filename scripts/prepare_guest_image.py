"""Install locked Linux CPython 3.12 wheels into a copy of the guest image."""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sandbox.vm_snapshot import sha256


def main(args):
    root = Path(args.root).resolve()
    repo = Path(__file__).resolve().parents[1]
    source = root / 'ubuntu.ext4'
    output = root / args.image
    if output.exists():
        raise FileExistsError(output)
    wheels = repo / 'work/backend/wheels'
    if not wheels.is_dir():
        raise FileNotFoundError(wheels)
    mount = root / 'prepare-guest-mount'
    mount.mkdir(exist_ok=False)
    subprocess.run(['cp', '--reflink=auto', '--sparse=always', str(source), str(output)], check=True)
    try:
        subprocess.run(['mount', '-o', 'loop', str(output), str(mount)], check=True)
        try:
            target = mount / 'usr/local/lib/python3.12/dist-packages'
            target.mkdir(parents=True, exist_ok=True)
            subprocess.run([
                'pip3', 'install', '--no-index', '--find-links', str(wheels),
                '--target', str(target), '--no-compile', '--ignore-installed',
                '--no-deps', '--ignore-requires-python',
                '--only-binary=:all:', '--platform', 'manylinux2014_x86_64',
                '--python-version', '3.12', '--implementation', 'cp', '--abi', 'cp312',
                '-r', str(repo / 'requirements-lock.txt'),
            ], check=True)
            check = subprocess.run([
                'chroot', str(mount), '/usr/bin/python3', '-c',
                'import importlib.metadata as m; import langgraph; '
                'print(m.version("langgraph"))',
            ], capture_output=True, text=True, check=True)
            version = check.stdout.strip()
            subprocess.run(['sync'], check=True)
        finally:
            subprocess.run(['umount', str(mount)], check=True)
    finally:
        mount.rmdir()
    result = {'at_utc': datetime.now(timezone.utc).isoformat(),
              'source_sha256': sha256(source), 'image': str(output),
              'image_sha256': sha256(output), 'image_bytes': output.stat().st_size,
              'python': '3.12', 'langgraph': version,
              'requirements_lock_sha256': sha256(repo / 'requirements-lock.txt'),
              'scope': 'offline guest image build; no VM boot or isolation validation'}
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', default='/root/dat-backend')
    parser.add_argument('--image', default='ubuntu-langgraph-2026-10-16-v2.ext4')
    parser.add_argument('--output', required=True)
    main(parser.parse_args())
