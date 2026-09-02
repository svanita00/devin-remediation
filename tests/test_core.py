"""Lightweight unit tests for the control plane's core logic (no network).

Run:  pip install pytest && pytest
"""
from app.config import remediate_severity_set, settings
from app.devin.client import Session
from app import sync, scans
from app.observability import _fmt_duration


def test_severity_set_parses():
    settings.remediate_severities = "critical,high"
    assert remediate_severity_set() == {"critical", "high"}


def test_issue_number_from_tag_title_and_keyword():
    assert sync._issue_number(Session("s", "running", tags=["issue-5"])) == 5
    assert sync._issue_number(Session("s", "running", title="Fix #4: XSS")) == 4
    assert sync._issue_number(Session("s", "running", title="Bump jaraco.context >=6.1.0")) == 2


def test_is_remediation_excludes_code_scan_internals():
    assert sync._is_remediation(Session("s", "running", title="Code scan: investigate batch 3")) is False
    assert sync._is_remediation(Session("s", "running", tags=["takehome"])) is True
    assert sync._is_remediation(Session("s", "running", origin="automation")) is True


def test_status_treats_pr_as_success():
    assert sync._status(Session("s", "suspended", pull_requests=["http://pr/1"])) == "success"
    assert sync._status(Session("s", "error")) == "failed"
    assert sync._status(Session("s", "suspended")) == "needs_attention"
    assert scans._normalize("suspended", "http://pr/1") == "success"
    assert scans._normalize("running", None) == "running"


def test_fmt_duration():
    assert _fmt_duration(0) == "—"
    assert _fmt_duration(30) == "30 s"
    assert _fmt_duration(600) == "10 min"
