"""Offline check of disposable guest-disk staging; does not boot a VM."""
import argparse
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sandbox.firecracker_backend import FirecrackerBackend


def main(args):
    backend = FirecrackerBackend(args.root)
    source = 'import json,sys\nprint(json.dumps(json.load(sys.stdin)))\n'
    with tempfile.TemporaryDirectory(prefix='stage-probe-', dir=backend.root) as directory:
        run = Path(directory)
        disk = run / 'disk.ext4'
        subprocess.run(['cp', '--reflink=auto', '--sparse=always',
                        str(backend.base_disk), str(disk)], check=True)
        backend._stage(disk, run, source, {'value': 42}, 'stage-probe-nonce')
        mount = run / 'verify-mount'
        mount.mkdir()
        subprocess.run(['mount', '-o', 'loop,ro', str(disk), str(mount)], check=True)
        try:
            result = {
                'source_matches': (mount / 'tmp/dat_submission.py').read_text() == source,
                'input_matches': json.loads((mount / 'root/dat_input.json').read_text()) == {'value': 42},
                'runner_present': (mount / 'root/dat_runner.py').is_file(),
                'config_nonce_matches': json.loads((mount / 'root/dat_config.json').read_text())['nonce'] == 'stage-probe-nonce',
            }
        finally:
            subprocess.run(['umount', str(mount)], check=True)
    evidence = {'at_utc': datetime.now(timezone.utc).isoformat(),
                'scope': 'offline disk staging only; no KVM or guest execution',
                'checks': result, 'all_pass': all(result.values())}
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(evidence, indent=2), encoding='utf-8')
    print(json.dumps(evidence, indent=2))
    return 0 if evidence['all_pass'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', default='/root/dat-backend')
    parser.add_argument('--output', required=True)
    raise SystemExit(main(parser.parse_args()))
