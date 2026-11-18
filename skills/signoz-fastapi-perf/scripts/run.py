#!/usr/bin/env python3
"""Orchestrate read-only SigNoz collection and Codex-ready diagnostics."""
from __future__ import annotations
import argparse
import os
from pathlib import Path
import subprocess
import sys


def main() -> int:
    p = argparse.ArgumentParser(description="Read-only SigNoz → AI agent performance evidence pipeline")
    p.add_argument("--url",default=os.getenv("SIGNOZ_URL", ""))
    p.add_argument("--service",default=os.getenv("SIGNOZ_SERVICE", ""))
    p.add_argument("--hours",type=float,default=24)
    p.add_argument("--threshold-ms",type=float,default=5000)
    p.add_argument("--limit",type=int,default=100)
    p.add_argument("--max-spans",type=int,default=2000)
    p.add_argument("--trace-id",default="")
    p.add_argument("--report-dir",default=".perf-reports/latest")
    p.add_argument("--from-existing",action="store_true", help="Do not call SigNoz; convert already collected analysis.json")
    args = p.parse_args()
    here = Path(__file__).resolve().parent
    report_dir = Path(args.report_dir).expanduser().resolve()
    if not args.from_existing:
        if not args.url:
            p.error("Set --url or SIGNOZ_URL for your own SigNoz instance")
        if not args.trace_id and not args.service:
            p.error("Set --service or SIGNOZ_SERVICE when searching slow HTTP requests")
        cmd = [sys.executable,str(here/"collect_signoz.py"),"--url",args.url,
               "--service",args.service,"--hours",str(args.hours),
               "--threshold-ms",str(args.threshold_ms),"--limit",str(args.limit),
               "--max-spans",str(args.max_spans),"--out",str(report_dir)]
        if args.trace_id:
            cmd.extend(["--trace-id",args.trace_id])
        ret = subprocess.run(cmd, check=False).returncode
        if ret:
            return ret
    return subprocess.run([sys.executable,str(here/"build_diagnosis.py"),"--report-dir",str(report_dir)],check=False).returncode

if __name__ == "__main__":
    raise SystemExit(main())
