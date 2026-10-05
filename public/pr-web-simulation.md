# Pull Request: feat(simulation) — Interactive Web Simulation (Next.js Control Room + Real-Time Socket.IO Engine)

## 📋 Summary

Adds `simulation/` — a self-contained, **interactive operator NOC for the AI-Enhanced BGP control plane**. The full research pipeline (telemetry → 10-feature extractor → ML classifier → hybrid trust engine → policy actor → shadow validation → autonomous rollback) is re-implemented as a live, tick-driven simulation where **every subsystem can be toggled on/off and every parameter is editable at runtime** — no Docker/FRR required.

**Why:** makes the paper's claims (S1–S6 attack lifecycle, A0–A4 ablation matrix, MTTD/MTTM/MSR metrics) directly explorable in ~2 minutes, lowering the barrier for reviewers, students, and operators to understand the system's dynamics.

| Control Room | Analytics |
| --- | --- |
| ![Control Room](simulation/docs/img/control-room.png) | ![Analytics](simulation/docs/img/analytics.png) |

## 🧩 What's included

- **`simulation/engine/`** (Bun + Socket.IO, port 3010): 10-AS topology with valley-free semantics, 10-feature behavioral extractor, RF/LogReg 4-class classifier, 6-criteria weighted trust engine, policy tiers (LP 100/80/50/0 + `no-export`), streak/dwell shadow validation, N-tick autonomous rollback, S1–S6 scenarios + custom attacks, A0–A4 ablation variants
- **`simulation/webapp/`** (Next.js 16, port 3000): control room (topology graph, live RIB, attack panel), analytics dashboards, A/B auto-benchmark, ablation lab, chaos drills with config fuzz, per-prefix watchlist alerting, forensic report export (print→PDF), time-travel replay, AI copilot, run archive (Prisma + SQLite)
- **README**: new "Interactive Web Simulation" section + repository tree entry; `simulation/README.md` with quickstart, architecture, and research-concept → feature mapping

## 🚀 Reviewer quickstart

```bash
cd simulation/engine && bun install && bun run dev     # terminal 1 — engine :3010
cd simulation/webapp && bun install && cp .env.example .env && bunx prisma db push && bun run dev   # terminal 2 — app :3000
```

Open http://localhost:3000 → **LINK goes green** → inject S1 (direct /24 hijack) from the attack panel and watch: detect → quarantine (LP 0 + no-export) → mitigate → rollback, with MTTD/MTTM/MSR in the KPI header.

## ✅ Test plan

- [ ] Engine boots on :3010, webapp LINK indicator connects (socket path `/`)
- [ ] S1–S6 each: detection fires, trust drops, LP tier applied, rollback restores LP100
- [ ] A0 (standard BGP) shows no detection vs A4 (full) full mitigation — ablation lab matrix
- [ ] Config editor: toggle any subsystem off (e.g. shadow validation) and observe behavior/metrics change; weights editor enforces Σ=1.0
- [ ] Run archive persists to SQLite (runs list survives restart)

## 🔍 Notes for maintainers

- Purely additive — **zero changes** to existing Python/Docker code paths; only the README gains a section + repo-tree line
- Web app dark control-room theme, mobile-responsive to 390px, keyboard shortcuts (`?`)
- AI copilot degrades gracefully without credentials (returns JSON error, UI shows notice)
- MIT license, same as parent repo

Closes: —
