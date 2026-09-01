#!/usr/bin/env python3
"""Provision the Devin resources this system depends on — idempotently.

Creates (if absent):
  1. a remediation Playbook (reusable SOP),
  2. a repo-context Knowledge note,
  3. an EVENT Automation  (GitHub `devin-fix` label -> remediation session -> PR),
  4. a SCHEDULE Automation (weekly security sweep).

This makes the whole setup reproducible: a new user runs
    DEVIN_API_KEY=... DEVIN_ORG_ID=org-... TARGET_REPO=you/superset python scripts/setup_devin.py
and their org is configured the same way ours is — no manual clicking.

Uses only the stdlib so it runs anywhere. Safe to re-run.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request

API = os.environ.get("DEVIN_API_BASE", "https://api.devin.ai/v3")
KEY = os.environ.get("DEVIN_API_KEY", "")
ORG = os.environ.get("DEVIN_ORG_ID", "")
REPO = os.environ.get("TARGET_REPO", "svanita00/superset")
LABEL = os.environ.get("TRIGGER_LABEL", "devin-fix")


def _call(method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    req = urllib.request.Request(
        f"{API}/organizations/{ORG}/{path}",
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
    )
    try:
        r = urllib.request.urlopen(req, timeout=40)
        return r.status, json.loads(r.read() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, {"error": e.read(300).decode(errors="replace")}


def _existing_names(path: str, name_key: str) -> set[str]:
    _, d = _call("GET", path)
    return {i.get(name_key, "") for i in (d.get("items") or [])}


PLAYBOOK_TITLE = "Security & Code-Quality Remediation"
PLAYBOOK_BODY = (
    "Reusable procedure to remediate a single security or code-quality issue.\n"
    "1. Check out the repo and create branch devin/issue-<N>.\n"
    "2. Implement the smallest change that resolves the issue; follow neighboring conventions.\n"
    "3. Treat the issue's Acceptance Criteria as the definition of done.\n"
    "4. Verify with the repo's own tooling (ruff + relevant tests); iterate until green; "
    "never open a PR with failing checks.\n"
    "5. Open a PR from devin/issue-<N> referencing the issue, describing problem/fix/verification.\n"
    "6. Report structured output {status, pr_url, summary, verification}."
)


def provision_playbook() -> str | None:
    if PLAYBOOK_TITLE in _existing_names("playbooks", "title"):
        print("• Playbook exists — skipping")
        return None
    code, d = _call("POST", "playbooks", {"title": PLAYBOOK_TITLE, "body": PLAYBOOK_BODY})
    pid = d.get("playbook_id")
    print(f"• Playbook created: {pid}" if pid else f"• Playbook create failed: {code} {d}")
    return pid


def provision_knowledge() -> None:
    name = "Superset repo context"
    if name in _existing_names("knowledge/notes", "name"):
        print("• Knowledge note exists — skipping")
        return
    body = ("Apache Superset needs Python 3.11+. Python deps are compiled with uv: edit "
            "requirements/*.in or pyproject.toml then run uv pip compile; do not hand-edit only "
            "the pinned .txt. Frontend is superset-frontend (npm). Lint with ruff. Keep changes "
            "minimal and scoped to one issue.")
    code, d = _call("POST", "knowledge/notes",
                    {"name": name, "trigger": f"When working in {REPO}", "body": body})
    print(f"• Knowledge note created: {d.get('note_id')}" if code < 300
          else f"• Knowledge create skipped ({code})")


def provision_event_automation(playbook_id: str | None) -> None:
    name = f"Auto-remediate {LABEL} issues ({REPO})"
    if name in _existing_names("automations", "name"):
        print("• Event automation exists — skipping")
        return
    pb = f" Follow @playbook:{playbook_id}." if playbook_id else ""
    body = {
        "name": name,
        "triggers": [{"event_type": "github:issues", "replies": [{"type": "post_response"}],
                      "conditions": {"any": [{"all": [
                          {"field": "repository.full_name", "operator": "eq", "value": REPO},
                          {"field": "action", "operator": "eq", "value": "labeled"},
                          {"field": "label.name", "operator": "eq", "value": LABEL}]}]}}],
        "actions": [{"type": "start_session",
                     "prompt": (f"A GitHub issue in @{REPO} was labeled `{LABEL}`. Investigate it, "
                                f"implement the fix, and open a pull request that resolves it.{pb} "
                                "The triggering issue payload is included automatically."),
                     "session": {"tags": ["auto-remediation", "event-trigger"]}}],
        "run_as": {"type": "creator"}, "enabled": True,
        "limits": {"max_acu_limit": 10}, "notifications": {"email": {"when": "dispatch_failed"}},
    }
    code, d = _call("POST", "automations", body)
    print(f"• Event automation created: {d.get('automation_id')}" if code < 300
          else f"• Event automation failed: {code} {d}")


def provision_schedule_automation(playbook_id: str | None) -> None:
    name = f"Weekly security sweep ({REPO})"
    if name in _existing_names("automations", "name"):
        print("• Schedule automation exists — skipping")
        return
    pb = f" Follow @playbook:{playbook_id}." if playbook_id else ""
    body = {
        "name": name,
        "triggers": [{"event_type": "schedule:recurring",
                      "conditions": {"any": [{"all": [
                          {"field": "rrule", "operator": "matches",
                           "value": "FREQ=WEEKLY;BYDAY=MO;BYHOUR=9;BYMINUTE=0"}]}]}}],
        "actions": [{"type": "start_session",
                     "prompt": (f"Weekly security sweep of @{REPO}. Check for known dependency "
                                "vulnerabilities (pip-audit on requirements, npm audit in "
                                "superset-frontend) and open a PR for each HIGH/CRITICAL finding."
                                f"{pb} Keep each PR minimal and scoped."),
                     "session": {"tags": ["scheduled-sweep", "security"]}}],
        "run_as": {"type": "creator"}, "enabled": True,
        "limits": {"max_acu_limit": 30}, "notifications": {"email": {"when": "dispatch_failed"}},
    }
    code, d = _call("POST", "automations", body)
    print(f"• Schedule automation created: {d.get('automation_id')}" if code < 300
          else f"• Schedule automation failed: {code} {d}")


def main() -> int:
    if not KEY or not ORG:
        print("ERROR: set DEVIN_API_KEY and DEVIN_ORG_ID", file=sys.stderr)
        return 1
    print(f"Provisioning Devin resources for org {ORG}, repo {REPO}\n")
    pid = provision_playbook()
    provision_knowledge()
    provision_event_automation(pid)
    provision_schedule_automation(pid)
    print("\nDone. Label an issue `devin-fix` (event) or POST /scan (code-scan) to remediate.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
