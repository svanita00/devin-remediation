# Devin Remediation Control Plane

A **production-style, event-driven automation** built on the Devin API that turns
security & code-quality findings in a repo into **reviewed-ready pull requests** —
autonomously — and reports effectiveness to an engineering leader.

Target for this demo: a fork of [Apache Superset](https://github.com/apache/superset).

Everything here runs from **one command** (`docker compose up`) and reproduces in
**mock mode for $0, no credentials** — flip one env var for live Devin.

---

## Why it exists

Scanners tell you *what* to fix; the bottleneck is the human hours to *fix* each
finding and open a reviewable PR. Devin already ships the remediation loop natively
(Code Scans, Automations, Playbooks, Metrics). This project is the thin layer a real
team still needs: it **orchestrates Devin's primitives** into a governed program and
gives leadership a **single control plane** — findings → PRs → success rate → cost.
It composes Devin; it does not reinvent it.

## Architecture

```
  TRIGGERS (all reproducible)                CONTROL PLANE (this repo, FastAPI + Docker)
  ┌───────────────────────────┐             ┌───────────────────────────────────────────┐
  │ 1. GitHub `devin-fix` label│──event────► │ native Devin Automation (provisioned by     │
  │    (event Automation)      │             │ scripts/setup_devin.py) → session → PR      │
  ├───────────────────────────┤             ├───────────────────────────────────────────┤
  │ 2. Weekly schedule         │──periodic─► │ native schedule Automation → security sweep │
  ├───────────────────────────┤             ├───────────────────────────────────────────┤
  │ 3. POST /scan (on-demand)  │──API──────► │ Code Scan → findings → remediate → PR       │
  └───────────────────────────┘             │      │            (Devin sessions)          │
                                             │      ▼                                       │
                                             │ auto-trigger Devin Review on each PR         │
                                             │      │                                       │
                                             │      ▼   reconcile ALL sessions from Devin API│
                                             │ SQLite + native Metrics/Consumption          │
                                             │      │                                       │
                                             │ GET /dashboard   GET /metrics                │──► what a VP sees
                                             └───────────────────────────────────────────┘
```

**Three triggers, matching the brief:** event (`devin-fix` label), periodic (weekly
schedule), and on-demand (`POST /scan`). All drive native Devin sessions; the control
plane **reconciles every session (any origin) from the Devin API** so the dashboard
reflects reality — not just what this process launched.

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

## Observability — "how would a leader know it's working?"

`/dashboard` (auto-refresh) shows, composed from our records + Devin's **native**
Metrics/Consumption APIs:
- **ROI**: engineer-hours reclaimed · cost per fix
- **Autonomy rate** (autonomous vs. needs-a-human) · **mean time-to-fix** vs. a manual baseline
- **Remediation funnel**: findings → dispatched → PRs opened → **merged**
- Risk-by-severity, a per-remediation table (severity → Devin session → PR → ACU), live activity log

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
```

## Devin platform surface used

Sessions · **Code Scans** · **Automations** (event + schedule) · **Playbooks** ·
**Knowledge** · **Devin Review** · **Metrics** · **Consumption**. (Dynamic Workflows &
MCP integrations noted as next steps.)

## Why Devin (not a dependency bot)

A version bot files a PR and stops. Devin reads the code, implements the fix, **writes a
regression test, runs the repo's lint/tests, iterates**, and opens the PR — then reviews
it. It even reads the repo's `AGENTS.md`/Playbook (e.g. it fixed a dependency by editing
the `uv` *source constraint* and recompiling, not hand-editing the pin). The boundary:
bounded, test-verifiable fixes land autonomously; wide-blast-radius/visual changes (the
deck.gl upgrade) still want a human — and the dashboard shows exactly which is which.

## Next steps (real engagement)

Human-in-the-loop approval gate before merge · multi-repo fleet view · route reports to
Slack/Jira/Notion via **MCP** · express the audit→fix→verify pipeline as a native
**Dynamic Workflow** · richer analytics (MTTR & cost per severity) from the Metrics API.
