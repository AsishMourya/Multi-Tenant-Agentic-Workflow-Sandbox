#!/usr/bin/env bash
set -euo pipefail

if ! grep -qi microsoft /proc/sys/kernel/osrelease 2>/dev/null; then
  echo "This demo is supported from WSL only. Open Ubuntu and run ./start-demo.sh there." >&2
  exit 1
fi

cd "$(dirname "$(readlink -f "$0")")"

offline=false
with_judge=false
for option in "$@"; do
  case "$option" in
    --offline) offline=true ;;
    --with-judge) with_judge=true ;;
    *) echo "Unknown option: $option (use --offline or --with-judge)" >&2; exit 2 ;;
  esac
done

if ! command -v node >/dev/null || ! command -v npm >/dev/null; then
  echo "Node.js and npm are required in WSL to build the dashboard." >&2
  exit 1
fi
if ! command -v python3 >/dev/null || ! command -v sudo >/dev/null; then
  echo "Python 3 and sudo are required in WSL." >&2
  exit 1
fi

if [[ ! -x .venv-linux/bin/python ]]; then
  python3 -m venv .venv-linux
fi
if $offline; then
  .venv-linux/bin/python -m pip check
else
  .venv-linux/bin/python -m pip install --disable-pip-version-check -r requirements-lock.txt
fi

if [[ ! -x web/node_modules/.bin/vite || ! -x web/node_modules/esbuild-linux-64/bin/esbuild ]]; then
  if $offline; then
    echo "Offline dependencies are missing. Run bash start-demo.sh once while online." >&2
    exit 1
  fi
  npm ci --prefix web
fi
npm --prefix web run build

if [[ ! -s config/tenants.local.json ]]; then
  .venv-linux/bin/python -c 'import json,secrets; from pathlib import Path; path=Path("config/tenants.local.json"); path.write_text(json.dumps({tenant:secrets.token_urlsafe(32) for tenant in ("tenant-a","tenant-b")}, indent=2) + "\n")'
  chmod 600 config/tenants.local.json
fi

echo
echo "Dashboard: http://127.0.0.1:8080/"
echo "Demo tokens: config/tenants.local.json (open it in VS Code or run: cat config/tenants.local.json)"
echo "The token file is local-only and ignored by Git."
echo
echo "Checking WSL/KVM readiness. The dashboard can still open if KVM is unavailable;"
echo "real learner-code execution requires working KVM and /root/dat-backend artifacts."
sudo -H env PYTHONNOUSERSITE=1 .venv-linux/bin/python scripts/feasibility.py \
  --backend-root /root/dat-backend --output /tmp/dat-sandbox-preflight.json || true
echo
echo "Starting the local API. Keep this terminal open; press Ctrl+C to stop."
judge_args=()
if $with_judge; then
  if ! command -v ollama >/dev/null || ! ollama show "${DAT_JUDGE_MODEL:-qwen2.5:0.5b}" >/dev/null 2>&1; then
    echo "Local Ollama judge is unavailable. Start Ollama and install ${DAT_JUDGE_MODEL:-qwen2.5:0.5b}." >&2
    exit 1
  fi
  DAT_JUDGE_MODEL="${DAT_JUDGE_MODEL:-qwen2.5:0.5b}"
fi
if [[ -n "${DAT_JUDGE_MODEL:-}" ]]; then
  echo "Local judge enabled: $DAT_JUDGE_MODEL (uncalibrated scores remain pending human review)."
  judge_args=(--judge-model "$DAT_JUDGE_MODEL")
fi
exec sudo -H env PYTHONNOUSERSITE=1 .venv-linux/bin/python scripts/serve.py \
  --credentials config/tenants.local.json \
  --state-root work/demo-state-v2 \
  --backend-root /root/dat-backend \
  --host 127.0.0.1 --port 8080 "${judge_args[@]}"
