# Loom Script — Devin Remediation Control Plane (~8–9 min)

Conversational bullets to read or riff from. `[SHOW]` = screen cue. Examples are
ordered capability → verification → judgment so the section ends on the trust boundary,
which flows into the dashboard.

---

## 0:00 — The problem
- "Hi, I'm Vanita. The problem I wanted to explore is simple: every engineering team has a queue of work that's *important but expensive to context-switch into* — security findings, dependency upgrades, on-call cleanup, tech debt."
- "The hard part usually isn't knowing *what* to fix. It's that each one pulls an engineer away from what they're doing to understand the code, make the change, test it, and open a PR."
- "So I built a workflow where **Devin becomes a first-pass engineer for that queue** — the engineer still decides what's a good candidate and reviews the result, but Devin does the investigation and implementation."

## 0:45 — Two ways work enters
- "Work comes in two ways. **Reactive:** an engineer already has a ticket — maybe from on-call — decides it's a good fit, and just adds a `devin-fix` label."
- "**Proactive:** Devin's Code Scan continuously looks for security issues, and the engineer picks which findings to hand off."
- "Either way it converges on one flow: **finding → Devin investigates → fix → PR → human review.** The goal isn't to replace the queue — it's to make it easy to delegate."

## 1:30 — LIVE: the handoff (issue #18)
- `[SHOW: GitHub issue #18]`
- "Let me do this live. I'm on call, and this issue just came in — a small correctness issue in the OAuth path. Not worth stopping my day for, but it should get cleaned up."
- "Instead of assigning it to another engineer, I hand it to Devin." `[ADD devin-fix LABEL]`
- "That's the entire handoff. The label fires the automation, and now there's a Devin session running against the issue." `[SHOW: session spinning up]`
- "Notice I didn't copy the ticket into Devin or write a prompt. **The GitHub issue is the interface. The label is the handoff.**"

## 2:30 — Devin working: a trained engineer, not a blank agent
- `[SHOW: session investigating; then the Playbook + Knowledge note in the Devin UI]`
- "While that runs — here's something I think is the real point. The session **isn't starting from a blank prompt.** It's operating under a **Playbook** I set up: our remediation SOP — branch, make the smallest change, treat the issue's acceptance criteria as done, verify with the repo's own lint and tests, then open the PR."
- "And a **Knowledge note** with repo-specific context — like the fact that this repo compiles its Python deps with `uv`, so Devin edits the source constraint and recompiles instead of hand-editing a pin."
- "So I'm not re-explaining the codebase or our conventions on every ticket. **It behaves less like a generic agent I have to brief each time, and more like a trained engineer who already knows how we work here.**"
- "And it compounds — every Playbook and Knowledge note I add is context the whole team's handoffs inherit from then on. The system gets more capable over time without anyone re-teaching it."
- *(Optional: hover the Knowledge note's trigger `When working in svanita00/superset` — visually proves it auto-applies, no prompting.)*

## 3:15 — Proactive: the security scan (feat. #20, the authorization fix)
- `[SHOW: Devin Code Scan findings]`
- "The other side is proactive. I configured Devin's Code Scan with a threat model for this repo, so instead of waiting for someone to find issues, it surfaces them continuously."
- "This scan produced 14 findings. And the key point: finding something doesn't mean blindly fixing everything — **I prioritize, and assign the ones worth Devin's time.**"
- "Here's one I assigned — a real **authorization bug**: a query tab wasn't enforcing ownership on the query it pointed to (`TabState.latest_query_id`), so a user could reference someone else's query." `[SHOW: PR #20]`
- "And this is the part that genuinely impressed me — watch how it *verified* the fix." `[SHOW: the testing video]`
- "It didn't just make the change and open a PR. It wrote and ran **access-control tests that prove the authorization actually holds** — the kind of adversarial verification you'd want a security-minded engineer to do before you trust the fix."
- "So the engineer stays in control of *what* gets done; Devin takes on the *doing* — and here, the *proving*."

## 4:00 — Two more, for range and judgment

**Example 1 (optional, for breadth) — #14, deck.gl** `[SHOW: PR #14 + browser recording of charts]`
- "To show this isn't just Python security work — here's a *breaking* frontend dependency upgrade, the hard case. Devin didn't take the naive upgrade path; it looked at the dependency tree and found the safer route."
- "And it **opened the app in a browser and confirmed the charts still rendered** before opening the PR — verifying its own work the way an engineer would."

**Example 2 — #10, Slack error handling (human judgment — the closer)** `[SHOW: PR #10 → review finding → your comment → follow-up]`
- "Third, and my favorite. Devin narrowed an overly broad error handler. Then its own review flagged an edge case — one cache backend could throw an error outside the new list."
- "Instead of telling it to bolt on a hack, I asked it to find a clean, backend-agnostic fix. **There wasn't one** — so it documented the tradeoff and added test coverage instead of forcing bad coupling."
- "That's the boundary that matters to me: **autonomy doesn't mean auto-merging everything.** Devin does the investigation, implementation, and iteration — the engineer still makes the architectural call. And on these nuanced ones, review caught real gaps."
- "What I took away: Devin is strongest when work is **bounded, well-contextualized, and test-verifiable** — and wide-blast-radius or subtle correctness changes still want a human."

## 5:45 — The dashboard
- `[SHOW: /dashboard]`
- "Once work enters from multiple directions, the question is: *is this creating value for the team?* That's the control plane."
- "I wanted a leader to answer a few things at a glance: **how much work is completing, how much is autonomous, are PRs actually merging, what severity are we clearing, and how fast does a finding become a PR.**"
- "It's built by reading Devin's **native Metrics and Consumption APIs** — I'm not recreating Devin's telemetry. And I'm deliberate about **measured vs. estimated**: the engineer-hours number is a labeled assumption, not something I pretend I measured."

## 6:45 — Next steps
- "If I took this further, the most interesting direction is that **the agent gets better the more we invest in its context.** Every recurring review comment, every 'actually, we do it this way here' — that becomes a Playbook or Knowledge note, and the next handoff already knows it. Over time you're effectively **onboarding and leveling up a teammate**, not re-prompting a tool."
- "I'd make it part of the team's *existing* workflow rather than a special system — `devin-fix` becomes a standard backlog and on-call label, and you auto-identify certain ticket classes as good Devin candidates."
- "And I'd extend the same pipeline beyond security — dependency upgrades, CI failures, recurring maintenance."
- "The abstraction stays the same: **work enters the queue → a context-rich Devin investigates and remediates → a human reviews.** The point isn't automating engineering *judgment* — it's automating the repetitive, expensive-to-context-switch-into work, with an agent that keeps getting sharper as we teach it, so engineers spend their time on the decisions that actually need them."

---

## Notes / timing
- ~8–9 min at a natural pace. Tightest version is three shown PRs: **#18 (live/reactive) → #20 (proactive security, testing video) → #10 (judgment closer)**. #14 is the optional breadth example — cut it first if you're long.
- **#20 honesty:** if it hasn't merged by recording, that's fine — show it as in-progress and let the *testing rigor* be the point; the pending human review reinforces the human-in-the-loop gate. If it has merged, even better.
- Two verification beats are intentional but distinct: #20 = automated access-control tests; #14 = manual browser render check. Lead #14 with *breadth* (frontend, not security) so it doesn't feel like a repeat.
- Concrete "learns over time" seed you can gesture to: the timezone self-correction (#13) is exactly the kind of review insight that *should* become a Knowledge note so it never recurs.
