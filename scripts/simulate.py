#!/usr/bin/env python3
"""Trigger a scan+remediate run against the control plane — so anyone (a grader,
the demo) can exercise the full pipeline with one command.

Usage:
    python scripts/simulate.py                 # manual trigger
    python scripts/simulate.py --trigger scheduled
    python scripts/simulate.py --url http://localhost:8000
"""
from __future__ import annotations

import argparse
import json
import urllib.request


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--trigger", default="manual", choices=["manual", "scheduled"])
    args = ap.parse_args()

    req = urllib.request.Request(
        f"{args.url}/scan?trigger={args.trigger}", data=b"", method="POST"
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        print(f"HTTP {r.status}: {json.load(r)}")
    print("Scan started. Watch it at", f"{args.url}/dashboard")


if __name__ == "__main__":
    main()
