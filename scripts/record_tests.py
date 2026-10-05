import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

if __name__=='__main__':
    a=argparse.ArgumentParser(); a.add_argument('--output',required=True); a.add_argument('--pattern',default='test*.py'); args=a.parse_args()
    start=datetime.now(timezone.utc).isoformat()
    p=subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-p',args.pattern,'-v'],capture_output=True,text=True)
    path=Path(args.output); path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps({'started_at_utc':start,'ended_at_utc':datetime.now(timezone.utc).isoformat(),'exit_code':p.returncode,'stdout':p.stdout,'stderr':p.stderr,'python':sys.version},indent=2),encoding='utf-8')
    print(p.stderr); raise SystemExit(p.returncode)
