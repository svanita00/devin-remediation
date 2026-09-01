"""Central configuration, loaded from environment / .env.

DEVIN_MODE is the key switch:
  - "mock" (default): no Devin API calls, no cost. The full control-plane flow
    (scan -> findings -> remediate -> track -> dashboard) runs offline for $0.
  - "live":  real calls to https://api.devin.ai/v3 using DEVIN_API_KEY + DEVIN_ORG_ID.
"""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Devin API (v3) ---
    devin_mode: str = "mock"                        # "mock" | "live"
    devin_api_key: str = ""                          # cog_... PAT (live only)
    devin_org_id: str = "org-810cadad51d945e3a673b97d53289387"
    devin_api_base: str = "https://api.devin.ai/v3"

    # --- Target + remediation policy ---
    target_repo: str = "svanita00/superset"
    scan_type: str = "security"                      # security | code-quality | ...
    remediate_severities: str = "critical,high"      # which findings to auto-remediate
    max_remediations_per_run: int = 3                # guardrail: cap PRs per scan run
    auto_review: bool = True                          # Devin self-reviews each PR it opens

    # --- Polling ---
    poll_interval_seconds: int = 10
    scan_poll_timeout_seconds: int = 3600

    # Periodic trigger is the native schedule Automation (scripts/setup_devin.py) — not an in-app cron.

    # --- Reporting assumptions (labeled estimates for the ROI view) ---
    hours_saved_per_fix: float = 2.0        # eng-hours a human would spend per fix (estimate)
    manual_baseline_days: int = 14          # typical human time-to-fix, for MTTR comparison
    acu_to_usd: float = 0.0                 # 0 = show ACU only; else show approx $ (rate/ACU)

    # --- Storage ---
    db_path: str = "data/control_plane.db"

    # --- Mock behaviour (ignored when live) ---
    mock_seconds_to_complete: int = 6                # simulated scan + remediation duration
    mock_num_findings: int = 4


settings = Settings()


def remediate_severity_set() -> set[str]:
    return {s.strip().lower() for s in settings.remediate_severities.split(",") if s.strip()}
