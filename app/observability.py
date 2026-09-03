"""Observability: JSON metrics + an engineering-leader control plane.

Answers the five questions an eng leader actually asks:
  - Is it worth it?      -> engineer-hours reclaimed + cost per fix
  - Is it landing?       -> funnel: findings -> dispatched -> PRs opened -> merged
  - Is it fast?          -> mean time-to-PR vs. a manual baseline
  - Can I trust it?      -> autonomy rate (autonomous vs. needs-a-human)
  - Are we safer?        -> severity of what's been remediated

Built by composing our per-finding records with Devin's NATIVE Metrics +
Consumption APIs (we read them, we don't reinvent collection).
"""
from __future__ import annotations

import html
import time
from datetime import datetime, timezone

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse

from app.config import settings
from app.devin.client import get_devin_client
from app import store

router = APIRouter()


async def _native() -> dict:
    client = get_devin_client()
    now = int(time.time()); after = now - 90 * 86400
    out: dict = {}
    try:
        out["metrics_sessions"] = await client.metrics_sessions(after, now)
        out["metrics_prs"] = await client.metrics_prs(after, now)
        out["consumption"] = await client.consumption_daily()
    except Exception as e:
        out["error"] = str(e)
    finally:
        await client.aclose()
    return out


def _fmt_duration(seconds: float) -> str:
    if seconds <= 0:
        return "—"
    if seconds < 90:
        return f"{seconds:.0f} s"
    m = seconds / 60
    if m < 60:
        return f"{m:.0f} min"
    h = m / 60
    return f"{h:.1f} h" if h < 24 else f"{h/24:.1f} d"


def _aggregate(native: dict) -> dict:
    runs = store.list_scan_runs()
    rems = store.list_remediations()
    by_status: dict[str, int] = {}
    for r in rems:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1

    dispatched = len(rems)
    prs_opened = sum(1 for r in rems if r["pr_url"])
    _prs = native.get("metrics_prs", {}) or {}
    merged = int(_prs.get("prs_merged_count", 0) or 0)
    prs_created = int(_prs.get("prs_created_count", 0) or 0) or prs_opened
    findings_total = sum((r["findings_total"] or 0) for r in runs)
    success = by_status.get("success", 0)
    needs_attention = by_status.get("needs_attention", 0)
    failed = by_status.get("failed", 0)
    active = by_status.get("pending", 0) + by_status.get("running", 0)
    completed = success + needs_attention + failed
    reviewed = sum(1 for r in rems if r.get("reviewed"))
    total_acu = round(sum((r["acus_consumed"] or 0) for r in rems), 2)

    # time-to-PR (detection -> PR opened), from our timestamps
    durs = [r["updated_at"] - r["created_at"] for r in rems
            if r["pr_url"] and r["updated_at"] and r["created_at"] and r["updated_at"] > r["created_at"]]
    mttr = sum(durs) / len(durs) if durs else 0

    # remediated severity mix
    sev_mix: dict[str, int] = {}
    for r in rems:
        if r["pr_url"]:
            sev_mix[(r["severity"] or "?").lower()] = sev_mix.get((r["severity"] or "?").lower(), 0) + 1

    hours_saved = round(prs_opened * settings.hours_saved_per_fix, 1)
    cost_per_fix = round(total_acu / prs_opened, 2) if prs_opened else 0
    usd = round(total_acu * settings.acu_to_usd, 2) if settings.acu_to_usd else None

    return {
        "mode": settings.devin_mode.upper(),
        "scan_runs": len(runs),
        "findings_total": findings_total,
        "dispatched": dispatched,
        "prs_opened": prs_opened,
        "prs_merged": merged,
        "active": active,
        "success": success,
        "needs_attention": needs_attention,
        "failed": failed,
        "reviewed": reviewed,
        "prs_created": prs_created,
        "autonomy_rate": round(success / completed, 3) if completed else None,
        "merge_rate": round(merged / prs_created, 3) if prs_created else None,
        "mttr_seconds": round(mttr, 1),
        "mttr_human": _fmt_duration(mttr),
        "manual_baseline_days": settings.manual_baseline_days,
        "hours_saved": hours_saved,
        "total_acu": total_acu,
        "cost_per_fix_acu": cost_per_fix,
        "usd_cost": usd,
        "severity_mix": sev_mix,
    }


async def _sync():
    try:
        from app.sync import sync_live_sessions
        await sync_live_sessions()
    except Exception as e:
        # A control plane shouldn't silently eat reconcile failures — surface it
        # on the activity feed so a stale dashboard is explainable, not mysterious.
        store.log(f"⚠️ live sync failed: {type(e).__name__}: {e}")


@router.get("/metrics")
async def metrics() -> JSONResponse:
    await _sync()
    native = await _native()
    agg = _aggregate(native)
    agg["native"] = native
    return JSONResponse(agg)


# ---------- presentation ----------
_SEV = {"critical": "#7f1d1d", "high": "#dc2626", "medium": "#d97706", "low": "#64748b", "?": "#94a3b8"}
_BADGE = {"pending": "#64748b", "running": "#2563eb", "success": "#16a34a",
          "needs_attention": "#d97706", "failed": "#dc2626"}


def _card(inner: str, extra: str = "") -> str:
    return f'<div class="card" style="{extra}">{inner}</div>'


def _bar(pct: float, color: str) -> str:
    return (f'<div class="track"><div class="fill" style="width:{max(2,pct):.0f}%;'
            f'background:{color}"></div></div>')


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard() -> str:
    await _sync()
    native = await _native()
    m = _aggregate(native)
    rems = store.list_remediations()
    events = store.list_events(14)

    autonomy = m["autonomy_rate"]
    autonomy_pct = f'{autonomy*100:.0f}%' if autonomy is not None else "—"
    merge_pct = f'{m["merge_rate"]*100:.0f}%' if m["merge_rate"] is not None else "—"
    usd = f' · ≈${m["usd_cost"]}' if m["usd_cost"] is not None else ""

    # ---- hero ----
    hero = f"""
    <div class="hero">
      <div class="hero-eyebrow">AUTONOMOUS REMEDIATION · {html.escape(settings.target_repo)}</div>
      <div class="hero-big">{m['prs_created']} PRs opened · {m['prs_merged']} merged</div>
      <div class="hero-sub">{m['dispatched']} findings remediated · {autonomy_pct} autonomous · <span class="chip">{m['mode']}</span></div>
    </div>"""

    # ---- KPI cards (measured only) ----
    kpis = "".join([
        _card(f'<div class="k-l">Autonomy rate</div><div class="k-v">{autonomy_pct}</div>'
              f'{_bar((autonomy or 0)*100, "#16a34a")}'
              f'<div class="k-s">{m["success"]} autonomous · {m["needs_attention"]} need a human · {m["failed"]} failed</div>'),
        _card(f'<div class="k-l">Merge rate</div><div class="k-v">{merge_pct}</div>'
              f'{_bar((m["merge_rate"] or 0)*100, "#2563eb")}'
              f'<div class="k-s">{m["prs_merged"]} of {m["prs_created"]} PRs merged</div>'),
        _card(f'<div class="k-l">PRs opened</div><div class="k-v">{m["prs_created"]}</div>'
              f'<div class="k-s">across {m["scan_runs"]} runs / triggers</div>'),
        _card(f'<div class="k-l">Estimated engineer-hours reclaimed</div>'
              f'<div class="k-v" style="color:#94a3b8">~{m["hours_saved"]:.0f}<span class="unit"> h</span></div>'
              f'<div class="k-s">{m["prs_created"]} PRs × ~{settings.hours_saved_per_fix:.0f}h/fix · <em>illustrative assumption, not measured</em></div>'),
    ])

    # ---- funnel ----
    stages = [("Findings detected", m["findings_total"], "#7c3aed"),
              ("Remediations dispatched", m["dispatched"], "#2563eb"),
              ("PRs opened", m["prs_created"], "#0891b2"),
              ("PRs merged", m["prs_merged"], "#16a34a")]
    top = max((s[1] for s in stages), default=0) or 1
    funnel_rows = ""
    prev = None
    for label, val, color in stages:
        conv = f' · {val/prev*100:.0f}% of prev' if prev not in (None, 0) else ""
        funnel_rows += (f'<div class="fn-row"><div class="fn-label">{label}</div>'
                        f'<div class="fn-bar"><div class="fn-fill" style="width:{max(3,val/top*100):.0f}%;'
                        f'background:{color}">{val}</div></div>'
                        f'<div class="fn-conv">{conv}</div></div>')
        prev = val
    funnel = _card(f'<div class="c-title">Remediation funnel</div>{funnel_rows}')

    # ---- severity mix ----
    sev_chips = "".join(
        f'<span class="sev-chip" style="background:{_SEV.get(k,"#94a3b8")}">{v} {k}</span>'
        for k, v in sorted(m["severity_mix"].items(), key=lambda x: x[0]))
    risk = _card(f'<div class="c-title">Risk remediated (by severity)</div>'
                 f'<div class="sev-wrap">{sev_chips or "<span class=muted>none yet</span>"}</div>')

    # ---- table ----
    trows = ""
    for r in rems:
        sev = (r["severity"] or "?").lower()
        pr = f'<a href="{html.escape(r["pr_url"])}" target="_blank">PR ↗</a>' if r["pr_url"] else "—"
        sess = (f'<a href="{html.escape(r["session_url"])}" target="_blank">session ↗</a>'
                if r["session_url"] else "—")
        acu = f'{r["acus_consumed"]:.2f}' if r["acus_consumed"] is not None else "—"
        trows += (f'<tr><td><span class="pill" style="background:{_SEV.get(sev,"#94a3b8")}">{sev}</span></td>'
                  f'<td class="ttl">{html.escape(r["title"] or "")}</td>'
                  f'<td class="mono">{html.escape(r["file_path"] or "")}</td>'
                  f'<td><span class="pill" style="background:{_BADGE.get(r["status"],"#64748b")}">{r["status"].replace("_"," ")}</span></td>'
                  f'<td>{sess}</td><td>{pr}</td><td class="num">{acu}</td></tr>')
    table = _card(f'<div class="c-title">Remediations</div><table>'
                  f'<tr><th>Severity</th><th>Finding</th><th>File</th><th>Status</th><th>Devin</th><th>PR</th><th>ACU</th></tr>'
                  f'{trows or "<tr><td colspan=7 class=muted>No remediations yet — POST /scan or run scripts/simulate.py.</td></tr>"}'
                  f'</table>')

    ev = "".join(f'<li><span class="ev-t">{datetime.fromtimestamp(e["ts"]).strftime("%H:%M:%S")}</span> '
                 f'{html.escape(e["message"])}</li>' for e in events)
    activity = _card(f'<div class="c-title">Activity</div><ul class="timeline">{ev or "<li class=muted>—</li>"}</ul>')

    origins = (native.get("metrics_sessions", {}) or {}).get("sessions_created_by_origin", {})
    origin_txt = " · ".join(f"{k} {v}" for k, v in origins.items() if v) or "—"
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>Devin Remediation — Control Plane</title><meta http-equiv="refresh" content="5">
<style>
 :root{{--bg:#f4f5f8;--card:#fff;--ink:#0f172a;--sub:#64748b;--line:#eef1f5;}}
 *{{box-sizing:border-box}}
 body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;margin:0;background:var(--bg);color:var(--ink)}}
 .top{{padding:22px 32px 8px}} .top h1{{margin:0;font-size:16px;letter-spacing:.2px}}
 .top .meta{{color:var(--sub);font-size:12px;margin-top:3px}}
 .wrap{{padding:8px 32px 40px;max-width:1200px}}
 .hero{{background:linear-gradient(135deg,#111827,#1e293b);color:#fff;border-radius:18px;padding:26px 30px;margin:12px 0 18px;box-shadow:0 8px 30px rgba(15,23,42,.15)}}
 .hero-eyebrow{{font-size:11px;letter-spacing:1.5px;color:#93a4bd;font-weight:600}}
 .hero-big{{font-size:34px;font-weight:750;margin:6px 0 6px;letter-spacing:-.5px}}
 .hero-sub{{color:#cbd5e1;font-size:14px}}
 .chip{{background:#334155;color:#e2e8f0;padding:2px 9px;border-radius:9999px;font-size:11px;font-weight:600;margin-left:4px}}
 .grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:16px}}
 .card{{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:16px 18px;box-shadow:0 1px 2px rgba(15,23,42,.04)}}
 .k-l{{font-size:12px;color:var(--sub);font-weight:600}} .k-v{{font-size:28px;font-weight:750;margin:4px 0 2px}}
 .unit{{font-size:14px;color:var(--sub);font-weight:600}} .k-s{{font-size:11.5px;color:var(--sub);margin-top:6px}}
 .track{{height:7px;background:#eef2f7;border-radius:9999px;overflow:hidden;margin-top:8px}}
 .fill{{height:100%;border-radius:9999px}}
 .cols{{display:grid;grid-template-columns:1.4fr 1fr;gap:14px;margin-bottom:16px}}
 .c-title{{font-size:12px;color:var(--sub);font-weight:700;text-transform:uppercase;letter-spacing:.4px;margin-bottom:12px}}
 .fn-row{{display:flex;align-items:center;gap:12px;margin:9px 0}}
 .fn-label{{width:180px;font-size:13px;color:#334155}}
 .fn-bar{{flex:1;background:#f1f5f9;border-radius:8px;overflow:hidden}}
 .fn-fill{{color:#fff;font-size:12px;font-weight:700;padding:6px 10px;border-radius:8px;text-align:right;min-width:26px}}
 .fn-conv{{width:120px;font-size:11px;color:var(--sub)}}
 .sev-wrap{{display:flex;gap:8px;flex-wrap:wrap}}
 .sev-chip,.pill{{color:#fff;padding:3px 10px;border-radius:9999px;font-size:11px;font-weight:600}}
 .pill{{text-transform:capitalize}}
 table{{width:100%;border-collapse:collapse}} th,td{{text-align:left;padding:9px 10px;font-size:13px;border-bottom:1px solid var(--line)}}
 th{{color:var(--sub);font-size:11px;text-transform:uppercase;letter-spacing:.4px}}
 .ttl{{max-width:320px}} .mono{{font-family:ui-monospace,Menlo,monospace;font-size:11.5px;color:var(--sub)}}
 .num{{text-align:right;font-variant-numeric:tabular-nums}}
 .timeline{{list-style:none;margin:0;padding:0;font-size:12.5px;color:#475569;line-height:1.9}}
 .ev-t{{color:#94a3b8;font-variant-numeric:tabular-nums;margin-right:6px}}
 .muted{{color:#94a3b8}} a{{color:#2563eb;text-decoration:none;font-weight:600}}
 .footnote{{color:#94a3b8;font-size:11px;margin-top:14px}}
</style></head><body>
 <div class="top"><h1>Devin Remediation — Control Plane</h1>
   <div class="meta">native session origins: {origin_txt} · reads Devin Metrics + Consumption APIs · {now} · auto-refresh 5s</div></div>
 <div class="wrap">
   {hero}
   <div class="grid">{kpis}</div>
   <div class="cols">{funnel}{risk}</div>
   {table}
   <div style="height:14px"></div>
   {activity}
   <div class="footnote">Measured (from Devin's Metrics API): PRs created/merged, autonomy rate, merge rate, funnel. Estimated (a labeled assumption, not measured): engineer-hours saved = PRs × ~{settings.hours_saved_per_fix:.0f}h/fix. ACU cost is available via Devin's Consumption API on Teams/Enterprise plans; on this Free account the API returns 0, so it's omitted rather than shown as $0.</div>
 </div>
</body></html>"""
