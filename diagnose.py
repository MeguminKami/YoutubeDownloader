"""
Simple diagnostic entrypoint for source-mode troubleshooting.
"""
from __future__ import annotations

import json

from main import run_self_check


def main() -> int:
    report = run_self_check()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
