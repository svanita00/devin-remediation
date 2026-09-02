# Devin Remediation Control Plane

An **event-driven remediation control plane** built on the Devin API that turns
security and code-quality findings into **review-ready pull requests**.

The system automates the expensive engineering loop — investigation, implementation,
testing, and review — while preserving a **human approval gate** for higher-risk changes.

Target for this demo: a fork of [Apache Superset](https://github.com/apache/superset).

Everything here runs from **one command** (`docker compose up`) and reproduces in
**mock mode for $0, no credentials** — flip one env var for live Devin.

---

## Overview

Scanners identify *what* to fix; the bottleneck is the engineering time to fix each
finding, test it, and open a reviewable PR. Devin ships the remediation primitives
natively (Code Scans, Automations, Playbooks, Metrics). This project is the thin layer
that composes them into a governed program: each fix is implemented by a Devin session,
independently reviewed (Devin Review + a human) before merge, and tracked on a control
plane. Where review surfaces a correctness issue, the change is sent back to Devin to
iterate rather than merged as-is (e.g. PRs #10 and #13). The emphasis is on preserving
existing behavior; the goal is not to maximize autonomous merges, but to maximize the
engineering work that can be safely automated behind a human approval gate.

## Architecture

![Remediation flow](docs/architecture.png)

**A fix starts one of two ways:**
1. **An engineer labels an issue** `devin-fix` → Devin fixes that specific issue.
2. **A security scan finds issues** → Devin fixes the high-severity ones. The scan runs
   **on-demand** (`POST /scan`) or **weekly** (scheduled); lower-confidence findings are
   surfaced for human triage rather than auto-fixed.

From there it's one flow: a **Devin session** investigates, fixes, tests, and opens a
**PR** → **Devin Review** analyzes it → a **human approves and merges**, or holds it. If
review finds an issue, it loops back to Devin to self-correct.

A **FastAPI control plane** (this repo) runs it all: it triggers the scan pipeline and,
via a **continuous background loop**, **reconciles every session (any origin) from the
Devin API** and **auto-triggers Devin Review on each new PR** — so review is part of the
automation (not a manual `/devin review`), and the **dashboard** reflects reality, not
just what this process launched. (Devin's native Automations provision the event/schedule
triggers via `scripts/setup_devin.py`; Devin's native auto-review can also be toggled on
in Settings → Review as a complement.)

## Results

- **7 curated findings → 7 remediation PRs**, 7/7 merged after review.
- **Devin Review caught a correctness bug** in the timezone remediation and drove a second iteration (Devin self-corrected).
- The **Slack remediation surfaced a backend-compatibility tradeoff** that required human judgment (left open with the tradeoff documented + tests added).
- **Devin Code Scan independently discovered** additional findings and opened a fix (semantic-layer secret masking).
- The **scheduled automation was exercised end-to-end** (trigger fired).
- Devin fixed dependencies the *correct* way (edited the `uv` source constraint and recompiled) and verified the deck.gl upgrade by **running the app in a browser**.

## Quickstart — mock mode ($0, no key, how a grader runs it)

```bash
cp .env.example .env          # defaults = mock mode
docker compose up --build
# in another terminal:
curl -X POST localhost:8000/scan          # or: python scripts/simulate.py
```
Open the control plane: **http://localhost:8000/dashboard** (JSON: `/metrics`).

Mock mode simulates the full Devin lifecycle (scan → findings → remediation sessions →
PRs → review → ACU cost) so the entire system runs and demos offline.

## Go live (real scans, PRs, reviews)

1. Create a Devin PAT: **app.devin.ai → Settings → Devin API → PATs** (`cog_…`).
2. Install the **Devin.ai GitHub App** on your fork with write on Code/PRs/Issues/Checks
   (set it to **all repositories** so public-repo automation events are delivered).
3. In `.env`: `DEVIN_MODE=live`, `DEVIN_API_KEY=cog_…`, `DEVIN_ORG_ID=org-…`, `TARGET_REPO=you/superset`.
4. **Provision the Devin resources** (Playbook, Knowledge, both Automations), idempotent:
   ```bash
   DEVIN_API_KEY=$DEVIN_API_KEY DEVIN_ORG_ID=$DEVIN_ORG_ID TARGET_REPO=you/superset \
     python scripts/setup_devin.py
   ```
5. *(optional)* recreate the curated issue set on your fork:
   ```bash
   REPO=you/superset bash seed_issues/seed_issues.sh
   ```
6. `docker compose up`, then trigger any of:
   - **event:** add the `devin-fix` label to an issue
   - **on-demand:** `curl -X POST localhost:8000/scan`
   - **periodic:** the weekly schedule fires on its own

## The seeded issues (scanner-found on real Superset mainline)

| # | Type | Finding |
|---|------|---------|
| 1 | dependency CVE | `python-multipart` → ≥0.0.30 (HIGH ReDoS) |
| 2 | dependency CVE | `jaraco.context` → ≥6.1.0 (HIGH path traversal) |
| 3 | dependency CVE | frontend `brace-expansion` HIGH (npm) |
| 4 | code + tests | eliminate the unsafe-`Markup` XSS class + regression test |
| 5 | code quality | timezone-naive datetime in `daos/key_value.py` |
| 6 | code quality | narrow blind `except` in `utils/slack.py` |
| 7 | dependency (breaking) | deck.gl/loaders.gl major upgrade (HIGH npm) — the hard case |

Plus issues **Devin's Code Scan discovers on its own** via `POST /scan`.

## Observability

`/dashboard` (auto-refreshing) is composed from the local store and Devin's native
**Metrics API**:
- **Remediation funnel**: findings → dispatched → PRs opened → **merged**
- **Autonomy rate** (autonomous vs. needs-a-human) and **merge rate**
- **Estimated** engineer-hours saved — a labeled assumption (PRs × a per-fix estimate),
  not a measured value
- Risk-by-severity and a per-remediation table (severity → Devin session → PR), live log

ACU/cost is available via Devin's **Consumption API** on Teams/Enterprise plans; on a
Free account that API returns 0, so cost is omitted rather than shown as `$0`.

## Project layout

```
app/
  main.py         FastAPI app; POST /scan, dashboard, health, DB init
  config.py       env settings (DEVIN_MODE is the big switch)
  scans.py        orchestrator: scan → findings → remediate → auto-review → track
  sync.py         reconcile ALL Devin sessions (any origin) into the store
  store.py        SQLite: scan_runs, remediations, events
  observability.py  /metrics + /dashboard (local + native metrics)
  devin/          Devin v3 client: interface + live + mock
scripts/
  setup_devin.py  idempotently provision Playbook + Knowledge + both Automations
  simulate.py     one-command trigger for graders/demo
seed_issues/
  *.md            the 7 curated issue bodies (the use case)
  seed_issues.sh  file them onto a fork + create the devin-fix label
tests/            unit tests for the core logic (pip install pytest && pytest)
```

## Devin platform surface used

Sessions · **Code Scans** · **Automations** (event + schedule) · **Playbooks** ·
**Knowledge** · **Devin Review** · **Metrics** · **Consumption**. (Dynamic Workflows &
MCP integrations noted as next steps.)

## Design rationale

Dependency bots automate deterministic changes; this system targets the reasoning-heavy
part of remediation. A Devin session reads the code, implements the fix, writes a
regression test, runs the repo's lint/tests, iterates, and opens the PR — then Devin
Review analyzes it. Sessions honor the repo's own `AGENTS.md` and the provisioned
Playbook (e.g. dependency fixes edit the `uv` source constraint and recompile rather than
hand-editing the pin). The intended boundary: bounded, test-verifiable fixes land
autonomously; wide-blast-radius or visual changes (e.g. the deck.gl upgrade) route to a
human — and the dashboard makes that split visible.

## Next steps (real engagement)

Human-in-the-loop approval gate before merge · multi-repo fleet view · route reports to
Slack/Jira/Notion via **MCP** · express the audit→fix→verify pipeline as a native
**Dynamic Workflow** · richer analytics (MTTR & cost per severity) from the Metrics API.
