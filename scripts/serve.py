"""Run the local authenticated sandbox dashboard and JSON API.

Use a copied, private credential file rather than committing bearer tokens.
Run under Linux root with working KVM to execute learner code.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sandbox.api import SandboxService, serve
from sandbox.firecracker_backend import FirecrackerBackend
from sandbox.local_judge import OllamaJudge
from sandbox.platform import Platform
from sandbox.tenant_gateway import TenantGateway


def credentials(path):
    try:
        value = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise SystemExit(f'cannot read credentials: {exc}') from exc
    if not isinstance(value, dict):
        raise SystemExit('credentials must be a JSON object of tenant names to bearer tokens')
    return value


def main(args):
    backend = FirecrackerBackend(args.backend_root)
    platform = Platform(args.state_root, backend=backend,
                        worker_capacity=args.workers,
                        tenant_worker_capacity=args.tenant_workers,
                        queue_limit=args.queue_limit)
    gateway = TenantGateway(platform, credentials(args.credentials))
    print(f'Sandbox dashboard: http://{args.host}:{args.port}/')
    print('Use a configured tenant bearer token in the dashboard.')
    judge_provider = None
    if args.judge_model:
        judge = OllamaJudge(args.judge_model)
        judge_provider = lambda evidence: judge.judge(evidence['exercise'], evidence)
    try:
        serve(SandboxService(gateway, judge_provider=judge_provider), host=args.host, port=args.port)
    except KeyboardInterrupt:
        pass
    finally:
        platform.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--credentials', required=True,
                        help='private JSON mapping of tenant names to bearer tokens')
    parser.add_argument('--state-root', default='work/platform-api')
    parser.add_argument('--backend-root', default='/root/dat-backend')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8080)
    parser.add_argument('--workers', type=int, default=2)
    parser.add_argument('--tenant-workers', type=int, default=1)
    parser.add_argument('--queue-limit', type=int, default=10)
    parser.add_argument('--judge-model',
                        help='optional local Ollama model, e.g. qwen2.5:0.5b')
    main(parser.parse_args())
