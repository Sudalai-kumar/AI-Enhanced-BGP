/**
 * Standalone HTML run-report generator (client-side, no dependencies).
 * Builds a self-contained dark NOC-styled document summarizing the run archive.
 */

export interface ReportRun {
  runId: number;
  scenarioId: string;
  scenarioName: string;
  variantLabel: string | null;
  mttd: number | null;
  mttm: number | null;
  msr: boolean;
  ribVerified: boolean;
  appliedPolicy: string;
  phase: string;
  createdAt: string;
  comparison?: Record<string, { detected: boolean; mttd: number | null; mitigated: boolean }> | null;
}

function esc(v: unknown): string {
  return String(v ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

const PHASE_TONE: Record<string, string> = {
  rolledback: '#34d399',
  mitigated: '#22d3ee',
  detected: '#fbbf24',
  injected: '#94a3b8',
  failed: '#f87171',
};

const DEFENSE_LABELS: [string, string][] = [
  ['standardBgp', 'Standard BGP'],
  ['rpki', 'RPKI ROV'],
  ['heuristic', 'Heuristics'],
  ['aiControl', 'AI Control Plane'],
];

function defenseCell(d?: { detected: boolean; mttd: number | null; mitigated: boolean }): string {
  if (!d) return '<td class="c dim">—</td>';
  if (!d.detected) return '<td class="c bad">blind</td>';
  const tone = d.mitigated ? 'ok' : 'mid';
  return `<td class="c ${tone}">${d.mttd !== null ? `${d.mttd}s` : 'n/a'}</td>`;
}

export function buildRunReportHtml(runs: ReportRun[]): string {
  const now = new Date();
  const total = runs.length;
  const mitigated = runs.filter((r) => r.msr).length;
  const msrPct = total ? Math.round((mitigated / total) * 100) : 0;
  const mttds = runs.filter((r) => r.mttd !== null).map((r) => r.mttd as number);
  const mttms = runs.filter((r) => r.mttm !== null).map((r) => r.mttm as number);
  const avg = (xs: number[]) => (xs.length ? (xs.reduce((a, b) => a + b, 0) / xs.length).toFixed(1) + 's' : '—');
  const ribOk = runs.filter((r) => r.ribVerified).length;
  const ribPct = total ? Math.round((ribOk / total) * 100) : 0;

  // per-scenario aggregation
  const byScenario = new Map<
    string,
    { name: string; runs: number; msr: number; mttds: number[]; mttms: number[]; sample: ReportRun }
  >();
  for (const r of runs) {
    let s = byScenario.get(r.scenarioId);
    if (!s) {
      s = { name: r.scenarioName, runs: 0, msr: 0, mttds: [], mttms: [], sample: r };
      byScenario.set(r.scenarioId, s);
    }
    s.runs += 1;
    if (r.msr) s.msr += 1;
    if (r.mttd !== null) s.mttds.push(r.mttd);
    if (r.mttm !== null) s.mttms.push(r.mttm);
  }

  const kpi = (label: string, value: string, tone: string) => `
    <div class="kpi"><div class="kpi-v" style="color:${tone}">${esc(value)}</div><div class="kpi-l">${esc(label)}</div></div>`;

  const scenarioRows = Array.from(byScenario.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([sid, s]) => {
      const msrP = Math.round((s.msr / s.runs) * 100);
      return `
      <tr>
        <td><b>${esc(sid)}</b> <span class="dim">${esc(s.name.replace(sid + ': ', ''))}</span></td>
        <td class="c">${s.runs}</td>
        <td class="c" style="color:${msrP >= 80 ? '#34d399' : msrP >= 40 ? '#fbbf24' : '#f87171'}">${msrP}%</td>
        <td class="c">${s.mttds.length ? avg(s.mttds) : '—'}</td>
        <td class="c">${s.mttms.length ? avg(s.mttms) : '—'}</td>
      </tr>`;
    })
    .join('');

  const latestByScenario = new Map<string, ReportRun>();
  for (const r of runs) latestByScenario.set(r.scenarioId, r);
  const defenseRows = Array.from(latestByScenario.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([sid, r]) => {
      const cmp = r.comparison ?? {};
      return `
      <tr>
        <td><b>${esc(sid)}</b></td>
        ${DEFENSE_LABELS.map(([key]) => defenseCell(cmp[key])).join('')}
      </tr>`;
    })
    .join('');

  const runRows = runs
    .slice()
    .reverse()
    .map((r) => {
      const tone = PHASE_TONE[r.phase] ?? '#94a3b8';
      return `
      <tr>
        <td>${new Date(r.createdAt).toISOString().replace('T', ' ').slice(0, 19)}</td>
        <td class="c">${r.runId}</td>
        <td><b>${esc(r.scenarioId)}</b></td>
        <td><span class="pill" style="color:${tone};border-color:${tone}55">${esc(r.phase)}</span></td>
        <td class="c">${esc(r.variantLabel ?? 'custom')}</td>
        <td class="c">${r.mttd !== null ? r.mttd + 's' : '—'}</td>
        <td class="c">${r.mttm !== null ? r.mttm + 's' : '—'}</td>
        <td class="c" style="color:${r.ribVerified ? '#34d399' : '#f87171'}">${r.ribVerified ? '✓' : '✗'}</td>
        <td class="c" style="color:${r.msr ? '#34d399' : '#f87171'}">${r.msr ? '✓' : '✗'}</td>
        <td>${esc(r.appliedPolicy || '—')}</td>
      </tr>`;
    })
    .join('');

  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>BGP Simulation Run Report · ${now.toISOString().slice(0, 19)}</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body { margin: 0; background: #020617; color: #e2e8f0; font-family: ui-monospace, 'SF Mono', Menlo, Consolas, monospace; font-size: 12px; }
  .wrap { max-width: 1060px; margin: 0 auto; padding: 32px 20px 60px; }
  header { border: 1px solid #1e293b; border-radius: 10px; padding: 18px 20px; background: linear-gradient(135deg, #0f172a, #020617); margin-bottom: 20px; }
  h1 { margin: 0 0 4px; font-size: 17px; letter-spacing: 0.02em; }
  h1 .accent { color: #34d399; }
  .sub { color: #64748b; font-size: 10.5px; }
  .kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 10px; margin: 20px 0 26px; }
  .kpi { border: 1px solid #1e293b; border-radius: 8px; background: #0f172a; padding: 12px 14px; }
  .kpi-v { font-size: 20px; font-weight: 700; }
  .kpi-l { color: #64748b; font-size: 9.5px; text-transform: uppercase; letter-spacing: 0.08em; margin-top: 3px; }
  h2 { font-size: 12.5px; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.1em; margin: 26px 0 10px; border-bottom: 1px solid #1e293b; padding-bottom: 6px; }
  table { width: 100%; border-collapse: collapse; border: 1px solid #1e293b; border-radius: 8px; overflow: hidden; }
  th { background: #0f172a; color: #64748b; font-size: 9.5px; text-transform: uppercase; letter-spacing: 0.06em; text-align: left; padding: 7px 10px; }
  td { padding: 6px 10px; border-top: 1px solid #0f172a; color: #cbd5e1; }
  tr:hover td { background: #0f172a80; }
  .c { text-align: center; }
  .dim { color: #475569; }
  .ok { color: #34d399; } .mid { color: #fbbf24; } .bad { color: #f87171; }
  .pill { display: inline-block; border: 1px solid; border-radius: 999px; padding: 1px 8px; font-size: 10px; }
  footer { margin-top: 30px; color: #475569; font-size: 9.5px; line-height: 1.7; }
  @media print { body { background: #fff; color: #111; } .kpi, table, header { border-color: #ccc; } }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>AI-Enhanced BGP Autonomous Control Plane · <span class="accent">Run Report</span></h1>
    <div class="sub">Generated ${esc(now.toISOString().replace('T', ' ').slice(0, 19))} UTC · ${total} archived runs · telemetry→features→ML→trust→shadow→policy→RIB→rollback pipeline · LocalPref 100/80/50/0 + no-export · Gao-Rexford · RFC 1997/6811/9234</div>
  </header>

  <div class="kpis">
    ${kpi('total runs', String(total), '#e2e8f0')}
    ${kpi('MSR', msrPct + '%', msrPct >= 80 ? '#34d399' : msrPct >= 40 ? '#fbbf24' : '#f87171')}
    ${kpi('avg MTTD', avg(mttds), '#fbbf24')}
    ${kpi('avg MTTM', avg(mttms), '#fb923c')}
    ${kpi('RIB verified', ribPct + '%', '#22d3ee')}
  </div>

  <h2>Per-Scenario Aggregates</h2>
  <table>
    <thead><tr><th>Scenario</th><th class="c">Runs</th><th class="c">MSR</th><th class="c">Avg MTTD</th><th class="c">Avg MTTM</th></tr></thead>
    <tbody>${scenarioRows || '<tr><td colspan="5" class="c dim">no runs</td></tr>'}</tbody>
  </table>

  <h2>Defense Comparison (latest run per scenario)</h2>
  <table>
    <thead><tr><th>Scenario</th>${DEFENSE_LABELS.map(([, l]) => `<th class="c">${esc(l)}</th>`).join('')}</tr></thead>
    <tbody>${defenseRows || '<tr><td colspan="5" class="c dim">no runs</td></tr>'}</tbody>
  </table>

  <h2>Full Run Log (${total} records, newest first)</h2>
  <table>
    <thead><tr><th>Timestamp</th><th class="c">#</th><th class="c">Scenario</th><th class="c">Phase</th><th class="c">Variant</th><th class="c">MTTD</th><th class="c">MTTM</th><th class="c">RIB</th><th class="c">MSR</th><th>Policy</th></tr></thead>
    <tbody>${runRows || '<tr><td colspan="10" class="c dim">archive empty</td></tr>'}</tbody>
  </table>

  <footer>
    Generated by the BGP simulation web app (AI-Enhanced-BGP replica) · Standard BGP is origin-blind ·
    RPKI ROV validates origin only (blind to sub-prefix hijacks of unregistered space) ·
    Heuristics use fixed rules · AI Control Plane = ML + 6-factor trust + shadow validation + tiered policy + RIB verification + autonomous rollback.
  </footer>
</div>
</body>
</html>`;
}

export function downloadHtmlReport(runs: ReportRun[]): string {
  const html = buildRunReportHtml(runs);
  const blob = new Blob([html], { type: 'text/html;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-');
  a.download = `bgp-run-report-${stamp}.html`;
  a.click();
  URL.revokeObjectURL(url);
  return stamp;
}

/* ================================================================== */
/* Per-run forensic report — single run / single prefix deep evidence  */
/* ================================================================== */

export interface ForensicTrustPoint {
  t: number;
  trust: number;
}

export interface ForensicEvent {
  t: number;
  level: string;
  source: string;
  message: string;
}

export interface ForensicRibEntry {
  t: number;
  lp: number;
  community: string | null;
  attempts: number;
  outcome: string;
  action: string;
}

export interface ForensicInput {
  prefix: string;
  /** most relevant run (newest touching this prefix), null if none */
  run: ReportRun & {
    injectedAt?: number;
    detectedAt?: number | null;
    mitigatedAt?: number | null;
    rolledBackAt?: number | null;
    groundTruth?: number | string;
    comparison?: Record<string, { detected: boolean; mttd: number | null; mitigated: boolean }> | null;
  } | null;
  routeStatus: string;
  trustScore: number | null;
  trustHistory: ForensicTrustPoint[];
  events: ForensicEvent[];
  ribEntries: ForensicRibEntry[];
  featureVector: number[] | null;
  featureNames: string[];
  simTime: number;
}

const F_TIER_LINES: [number, string][] = [
  [0.85, '#34d399'],
  [0.55, '#fbbf24'],
  [0.25, '#fb923c'],
];

function forensicTrustSvg(hist: ForensicTrustPoint[]): string {
  if (hist.length < 2) return '<p class="dim">not enough trust samples recorded</p>';
  const W = 720;
  const H = 170;
  const PAD = { l: 34, r: 10, t: 10, b: 20 };
  const ts = hist.map((p) => p.t);
  const tMin = Math.min(...ts);
  const tMax = Math.max(...ts);
  const span = Math.max(1, tMax - tMin);
  const x = (t: number) => PAD.l + ((t - tMin) / span) * (W - PAD.l - PAD.r);
  const y = (v: number) => PAD.t + (1 - Math.max(0, Math.min(1, v))) * (H - PAD.t - PAD.b);
  const pts = hist.map((p) => `${x(p.t).toFixed(1)},${y(p.trust).toFixed(1)}`).join(' ');
  let minI = 0;
  hist.forEach((p, i) => {
    if (p.trust < hist[minI].trust) minI = i;
  });
  const area = `${PAD.l},${y(0)} ${pts} ${x(tMax).toFixed(1)},${y(0)}`;
  const grid = [0, 0.25, 0.55, 0.85, 1]
    .map((v) => `<text x="${PAD.l - 6}" y="${(y(v) + 3).toFixed(1)}" text-anchor="end" font-size="8" fill="#475569">${v.toFixed(2)}</text>`)
    .join('');
  const tiers = F_TIER_LINES.map(
    ([v, c]) =>
      `<line x1="${PAD.l}" y1="${y(v)}" x2="${W - PAD.r}" y2="${y(v)}" stroke="${c}" stroke-opacity="0.35" stroke-dasharray="4 4"/><text x="${W - PAD.r}" y="${y(v) - 3}" text-anchor="end" font-size="8" fill="${c}" fill-opacity="0.7">${v}</text>`
  ).join('');
  const last = hist[hist.length - 1];
  const lastTone = last.trust >= 0.85 ? '#34d399' : last.trust >= 0.55 ? '#fbbf24' : last.trust >= 0.25 ? '#fb923c' : '#f87171';
  return `
  <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="trust trajectory" style="width:100%;height:auto;border:1px solid #1e293b;border-radius:8px;background:#0f172a">
    ${grid}
    ${tiers}
    <polygon points="${area}" fill="url(#tgrad)" fill-opacity="0.25"/>
    <polyline points="${pts}" fill="none" stroke="#38bdf8" stroke-width="1.5"/>
    <circle cx="${x(hist[minI].t)}" cy="${y(hist[minI].trust)}" r="3" fill="#f87171"/>
    <text x="${Math.min(W - PAD.r - 60, x(hist[minI].t) + 6)}" y="${y(hist[minI].trust) - 6}" font-size="8" fill="#f87171">min ${hist[minI].trust.toFixed(2)}</text>
    <circle cx="${x(last.t)}" cy="${y(last.trust)}" r="3.5" fill="${lastTone}"/>
    <text x="${Math.min(W - PAD.r - 60, x(last.t) + 6)}" y="${y(last.trust) - 6}" font-size="8" fill="${lastTone}">τ ${last.trust.toFixed(2)}</text>
    <text x="${PAD.l}" y="${H - 6}" font-size="8" fill="#475569">t=${tMin}s</text>
    <text x="${W - PAD.r}" y="${H - 6}" text-anchor="end" font-size="8" fill="#475569">t=${tMax}s</text>
    <defs><linearGradient id="tgrad" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#38bdf8"/><stop offset="100%" stop-color="#38bdf8" stop-opacity="0"/></linearGradient></defs>
  </svg>`;
}

function forensicLifecycleBar(
  run: NonNullable<ForensicInput['run']>
): string {
  const marks: { t: number | null; label: string; color: string }[] = [
    { t: run.injectedAt ?? null, label: 'injected', color: '#fbbf24' },
    { t: run.detectedAt ?? null, label: 'detected', color: '#fb923c' },
    { t: run.mitigatedAt ?? null, label: 'mitigated', color: '#ef4444' },
    { t: run.rolledBackAt ?? null, label: 'rolled back', color: '#34d399' },
  ].filter((m) => m.t !== null && m.t !== undefined) as { t: number; label: string; color: string }[];
  if (marks.length < 2) return '<p class="dim">run did not progress past injection</p>';
  const t0 = marks[0].t;
  const tN = marks[marks.length - 1].t;
  const span = Math.max(1, tN - t0);
  const W = 720;
  const H = 58;
  const PAD = 70;
  const x = (t: number) => PAD + ((t - t0) / span) * (W - 2 * PAD);
  // phase bands between consecutive marks
  const bands: string[] = [];
  for (let i = 0; i < marks.length - 1; i++) {
    const a = marks[i];
    const b = marks[i + 1];
    bands.push(
      `<rect x="${x(a.t)}" y="18" width="${Math.max(2, x(b.t) - x(a.t))}" height="14" rx="3" fill="${a.color}" fill-opacity="0.55"/>`
    );
  }
  const markers = marks
    .map(
      (m) =>
        `<line x1="${x(m.t)}" y1="14" x2="${x(m.t)}" y2="36" stroke="${m.color}"/><circle cx="${x(m.t)}" cy="14" r="3" fill="${m.color}"/><text x="${Math.max(4, Math.min(W - 54, x(m.t) - 20))}" y="10" font-size="8" fill="${m.color}">${m.label} ${m.t - t0}s</text>`
    )
    .join('');
  return `
  <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="run lifecycle timeline" style="width:100%;height:auto;border:1px solid #1e293b;border-radius:8px;background:#0f172a">
    <line x1="${PAD}" y1="25" x2="${W - PAD}" y2="25" stroke="#334155" stroke-width="1"/>
    ${bands.join('')}
    ${markers}
    <text x="${PAD - 8}" y="${H - 8}" text-anchor="end" font-size="8" fill="#475569">t=${t0}s</text>
    <text x="${W - PAD + 8}" y="${H - 8}" font-size="8" fill="#475569">t=${tN}s</text>
  </svg>`;
}

export function buildForensicReportHtml(input: ForensicInput): string {
  const now = new Date();
  const { run, prefix } = input;
  const tone = run ? (PHASE_TONE[run.phase] ?? '#94a3b8') : '#94a3b8';
  const kpi = (label: string, value: string, tone: string) => `
    <div class="kpi"><div class="kpi-v" style="color:${tone}">${esc(value)}</div><div class="kpi-l">${esc(label)}</div></div>`;

  const defenseRows = run?.comparison
    ? DEFENSE_LABELS.map(([key, label]) => defenseCell(run.comparison?.[key])).join('')
    : DEFENSE_LABELS.map(() => '<td class="c dim">—</td>').join('');

  const eventRows = input.events
    .slice()
    .reverse()
    .slice(0, 60)
    .map(
      (e) => `
      <tr>
        <td class="c">${esc(e.t)}s</td>
        <td class="c" style="color:${e.level === 'danger' ? '#f87171' : e.level === 'warn' ? '#fbbf24' : e.level === 'success' ? '#34d399' : '#38bdf8'}">${esc(e.level)}</td>
        <td class="c">${esc(e.source)}</td>
        <td>${esc(e.message)}</td>
      </tr>`
    )
    .join('');

  const ribRows = input.ribEntries
    .slice()
    .reverse()
    .map(
      (e) => `
      <tr>
        <td class="c">${esc(e.t)}s</td>
        <td class="c">${esc(e.lp)}</td>
        <td class="c">${esc(e.community ?? '—')}</td>
        <td class="c">${esc(e.attempts)}×</td>
        <td class="c" style="color:${e.outcome === 'verified' ? '#34d399' : '#f87171'}">${esc(e.outcome)}</td>
        <td>${esc(e.action)}</td>
      </tr>`
    )
    .join('');

  const featureRows =
    input.featureVector && input.featureNames
      ? input.featureNames
          .map(
            (name, i) =>
              `<tr><td>${esc(name)}</td><td class="c">${esc(input.featureVector?.[i] ?? '—')}</td></tr>`
          )
          .join('')
      : '';

  const dwell =
    run?.mitigatedAt != null && run?.injectedAt != null ? `${run.mitigatedAt - run.injectedAt}s` : run?.phase === 'failed' ? '>150s' : '—';

  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>BGP Forensic Report · ${esc(prefix)} · run #${esc(run?.runId ?? '—')}</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body { margin: 0; background: #020617; color: #e2e8f0; font-family: ui-monospace, 'SF Mono', Menlo, Consolas, monospace; font-size: 12px; }
  .wrap { max-width: 980px; margin: 0 auto; padding: 32px 20px 60px; }
  header { border: 1px solid #1e293b; border-radius: 10px; padding: 18px 20px; background: linear-gradient(135deg, #0f172a, #020617); margin-bottom: 20px; }
  h1 { margin: 0 0 4px; font-size: 17px; letter-spacing: 0.02em; }
  h1 .accent { color: #34d399; }
  .sub { color: #64748b; font-size: 10.5px; }
  .kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 10px; margin: 20px 0 26px; }
  .kpi { border: 1px solid #1e293b; border-radius: 8px; background: #0f172a; padding: 12px 14px; }
  .kpi-v { font-size: 19px; font-weight: 700; }
  .kpi-l { color: #64748b; font-size: 9.5px; text-transform: uppercase; letter-spacing: 0.08em; margin-top: 3px; }
  h2 { font-size: 12.5px; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.1em; margin: 26px 0 10px; border-bottom: 1px solid #1e293b; padding-bottom: 6px; }
  table { width: 100%; border-collapse: collapse; border: 1px solid #1e293b; border-radius: 8px; overflow: hidden; }
  th { background: #0f172a; color: #64748b; font-size: 9.5px; text-transform: uppercase; letter-spacing: 0.06em; text-align: left; padding: 7px 10px; }
  td { padding: 6px 10px; border-top: 1px solid #0f172a; color: #cbd5e1; }
  tr:hover td { background: #0f172a80; }
  .c { text-align: center; }
  .dim { color: #475569; }
  .ok { color: #34d399; } .mid { color: #fbbf24; } .bad { color: #f87171; }
  .pill { display: inline-block; border: 1px solid; border-radius: 999px; padding: 1px 8px; font-size: 10px; }
  footer { margin-top: 30px; color: #475569; font-size: 9.5px; line-height: 1.7; }
  @media print { body { background: #fff; color: #111; } .kpi, table, header { border-color: #ccc; } }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>BGP Forensic Report · <span class="accent">${esc(prefix)}</span></h1>
    <div class="sub">
      ${run ? `run #${esc(run.runId)} · ${esc(run.scenarioId)} ${esc(run.scenarioName.replace(/^[SCX][0-9]*: /, ''))} · ` : 'no run linked · '}
      <span class="pill" style="color:${tone};border-color:${tone}55">${esc(run?.phase ?? input.routeStatus)}</span>
      · exported ${esc(now.toISOString().replace('T', ' ').slice(0, 19))} UTC · sim clock t=${esc(input.simTime)}s
    </div>
  </header>

  <div class="kpis">
    ${kpi('MTTD', run?.mttd != null ? run.mttd + 's' : 'never', run?.mttd != null ? '#fbbf24' : '#f87171')}
    ${kpi('MTTM', run?.mttm != null ? run.mttm + 's' : '—', '#fb923c')}
    ${kpi('dwell (inject→mitigate)', dwell, '#e879f9')}
    ${kpi('MSR', run ? (run.msr ? '✓ mitigated' : '✗') : '—', run?.msr ? '#34d399' : '#f87171')}
    ${kpi('RIB verified', run ? (run.ribVerified ? '✓' : '✗') : '—', run?.ribVerified ? '#22d3ee' : '#f87171')}
    ${kpi('trust τ (final)', input.trustScore != null ? input.trustScore.toFixed(3) : '—', input.trustScore != null && input.trustScore >= 0.85 ? '#34d399' : input.trustScore != null && input.trustScore >= 0.25 ? '#fbbf24' : '#f87171')}
    ${kpi('policy applied', run?.appliedPolicy || 'none', '#94a3b8')}
    ${kpi('samples', `${input.trustHistory.length} τ · ${input.events.length} events · ${input.ribEntries.length} commits`, '#94a3b8')}
  </div>

  <h2>Defense Comparison (this run)</h2>
  <table>
    <thead><tr><th>${esc(prefix)}</th>${DEFENSE_LABELS.map(([, l]) => `<th class="c">${esc(l)}</th>`).join('')}</tr></thead>
    <tbody><tr><td><b>${esc(run?.scenarioId ?? '—')}</b> · ground truth class ${esc(String(run?.groundTruth ?? '—'))}</td>${defenseRows}</tbody>
  </table>

  <h2>Trust Trajectory (τ over time, policy tiers marked)</h2>
  ${forensicTrustSvg(input.trustHistory)}

  ${run ? `<h2>Run Lifecycle</h2>${forensicLifecycleBar(run)}` : ''}

  <h2>Feature Vector (final observation)</h2>
  ${
    featureRows
      ? `<table><thead><tr><th>Behavioral Feature</th><th class="c">Value</th></tr></thead><tbody>${featureRows}</tbody></table>`
      : '<p class="dim">route no longer in the RIB — feature vector unavailable for this export</p>'
  }

  <h2>Event Timeline (${input.events.length} prefix events, newest first, max 60)</h2>
  <table>
    <thead><tr><th class="c">t</th><th class="c">level</th><th class="c">source</th><th>message</th></tr></thead>
    <tbody>${eventRows || '<tr><td colspan="4" class="c dim">no prefix events retained</td></tr>'}</tbody>
  </table>

  <h2>RIB Commit Audit (${input.ribEntries.length} entries)</h2>
  <table>
    <thead><tr><th class="c">t</th><th class="c">LP</th><th class="c">community</th><th class="c">attempts</th><th class="c">outcome</th><th>action</th></tr></thead>
    <tbody>${ribRows || '<tr><td colspan="6" class="c dim">no RIB commits recorded for this prefix</td></tr>'}</tbody>
  </table>

  <footer>
    Generated by the BGP simulation web app (AI-Enhanced-BGP replica) · per-prefix forensic export from the drill-down
    console · trust tiers: τ ≥ 0.85 normal · 0.55-0.85 suspicious (LP 80) · 0.25-0.55 leak (LP 50) · &lt; 0.25 hijack
    (LP 0 + no-export) · MTTD = injection → detection · MTTM = detection → verified mitigation · dwell = injection → mitigation.
  </footer>
</div>
</body>
</html>`;
}

export function downloadForensicReport(input: ForensicInput): string {
  const html = buildForensicReportHtml(input);
  const blob = new Blob([html], { type: 'text/html;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-');
  a.download = `bgp-forensic-${input.prefix.replace(/[/.]/g, '-')}-${stamp}.html`;
  a.click();
  URL.revokeObjectURL(url);
  return stamp;
}
