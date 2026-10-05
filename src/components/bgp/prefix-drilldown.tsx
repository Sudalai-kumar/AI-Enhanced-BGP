'use client';

import React, { useMemo, useState } from 'react';
import {
  ATTACK_SCENARIOS,
  CLASS_NAMES,
  FEATURE_NAMES,
  RouteSnapshot,
  RunResult,
  SimState,
  TrustPoint,
} from '@/lib/bgp-sim/types';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Badge } from '@/components/ui/badge';
import {
  Crosshair,
  Activity,
  ShieldAlert,
  ShieldCheck,
  Clock,
  GitBranch,
  ListOrdered,
  Scale,
  Radar,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  FileDown,
  Printer,
  Link2,
} from 'lucide-react';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip as RTooltip,
  ReferenceLine,
  Area,
  CartesianGrid,
} from 'recharts';
import { buildForensicReportHtml, downloadForensicReport } from '@/lib/bgp-sim/report';

const STATUS_STYLE: Record<string, { badge: string; dot: string; label: string }> = {
  normal: { badge: 'border-emerald-800 bg-emerald-950/60 text-emerald-300', dot: 'bg-emerald-400', label: 'NORMAL' },
  suspicious: { badge: 'border-amber-800 bg-amber-950/60 text-amber-300', dot: 'bg-amber-400', label: 'SUSPICIOUS' },
  leak: { badge: 'border-orange-800 bg-orange-950/60 text-orange-300', dot: 'bg-orange-400', label: 'ROUTE LEAK' },
  hijack: { badge: 'border-red-800 bg-red-950/60 text-red-300', dot: 'bg-red-500', label: 'HIJACK' },
  recovering: { badge: 'border-cyan-800 bg-cyan-950/60 text-cyan-300', dot: 'bg-cyan-400', label: 'RECOVERING' },
  withdrawn: { badge: 'border-slate-700 bg-slate-900 text-slate-400', dot: 'bg-slate-600', label: 'WITHDRAWN' },
};

const LEVEL_STYLE: Record<string, string> = {
  info: 'text-sky-300',
  warn: 'text-amber-300',
  danger: 'text-red-400',
  success: 'text-emerald-300',
};

const PHASE_TONE: Record<string, { bg: string; text: string }> = {
  injected: { bg: 'bg-amber-500/70', text: 'text-amber-200' },
  detected: { bg: 'bg-orange-500/70', text: 'text-orange-200' },
  mitigated: { bg: 'bg-red-600/70', text: 'text-red-200' },
  rolledback: { bg: 'bg-emerald-600/70', text: 'text-emerald-200' },
  failed: { bg: 'bg-red-900/70', text: 'text-red-300' },
};

function trustText(t: number): string {
  if (t >= 0.85) return 'text-emerald-300';
  if (t >= 0.55) return 'text-amber-300';
  if (t >= 0.25) return 'text-orange-300';
  return 'text-red-400';
}

function trustStroke(t: number): string {
  if (t >= 0.85) return '#34d399';
  if (t >= 0.55) return '#fbbf24';
  if (t >= 0.25) return '#fb923c';
  return '#f87171';
}

/**
 * Full-history prefix drill-down: everything the engine knows about ONE prefix
 * in a single NOC-styled modal — trust decomposition, live trajectory chart,
 * run lifecycle timeline, per-prefix event stream and RIB audit.
 */
export function PrefixDrilldown({
  state,
  prefix,
  onClose,
}: {
  state: SimState;
  prefix: string | null;
  onClose: () => void;
}) {
  const r: RouteSnapshot | undefined = prefix ? state.routes[prefix] : undefined;
  const trustHistory: TrustPoint[] = useMemo(
    () => (prefix ? state.trustHistory.filter((p) => p.prefix === prefix) : []),
    [state.trustHistory, prefix],
  );
  const events = useMemo(
    () => (prefix ? state.events.filter((e) => e.message.includes(prefix)).slice(-40).reverse() : []),
    [state.events, prefix],
  );
  const ribEntries = useMemo(
    () => (prefix ? state.ribLog.filter((e) => e.prefix === prefix) : []),
    [state.ribLog, prefix],
  );

  // runs touching this prefix — scenario prefix match, or custom (CX) runs linked
  // via the injection event's timestamp (event t === run.injectedAt, since the
  // engine emits the attack event on the same tick the run starts)
  const runs: RunResult[] = useMemo(() => {
    if (!prefix) return [];
    const scenarioIds = new Set(ATTACK_SCENARIOS.filter((s) => s.prefix === prefix).map((s) => s.id));
    const all = state.activeRun ? [state.activeRun, ...state.history] : state.history;
    const matched = all.filter((run) => scenarioIds.has(run.scenarioId));
    const injectTs = new Set(
      state.events.filter((e) => e.source === 'attack' && e.message.includes(prefix)).map((e) => e.t),
    );
    const custom = all.filter((run) => run.scenarioId === 'CX' && injectTs.has(run.injectedAt));
    return [...matched, ...custom];
  }, [state.activeRun, state.history, state.events, prefix]);

  const st = STATUS_STYLE[r?.status ?? 'withdrawn'] ?? STATUS_STYLE.withdrawn;
  const trust = r?.trust;
  const weights = state.config.trust.weights;

  // trust composition: indicator × weight → contribution
  const contributions =
    trust && state.config.trust.enabled
      ? Object.entries(trust.indicators).map(([k, v]) => ({
          key: k,
          value: v as number,
          weight: (weights as Record<string, number>)[k] ?? 0,
          contribution: (v as number) * ((weights as Record<string, number>)[k] ?? 0),
        }))
      : [];

  const chartData = trustHistory.map((p) => ({ t: p.t, trust: p.trust }));

  /** newest run touching this prefix — drives the forensic export */
  const newestRun = runs.length > 0 ? runs.reduce((a, b) => (a.injectedAt >= b.injectedAt ? a : b)) : null;

  /** shared forensic-report input (used by both the HTML download and print/PDF) */
  const forensicInput = () => {
    if (!prefix) return null;
    return {
      prefix,
      run: newestRun
        ? {
            runId: newestRun.runId,
            scenarioId: newestRun.scenarioId,
            scenarioName: newestRun.scenarioName,
            variantLabel: null,
            mttd: newestRun.mttd,
            mttm: newestRun.mttm,
            msr: newestRun.msr,
            ribVerified: newestRun.ribVerified,
            appliedPolicy: newestRun.appliedPolicy,
            phase: newestRun.phase,
            createdAt: new Date().toISOString(),
            comparison: newestRun.comparison,
            injectedAt: newestRun.injectedAt,
            detectedAt: newestRun.detectedAt,
            mitigatedAt: newestRun.mitigatedAt,
            rolledBackAt: newestRun.rolledBackAt,
            groundTruth: newestRun.groundTruth,
          }
        : null,
      routeStatus: r?.status ?? 'withdrawn',
      trustScore: trust?.score ?? null,
      trustHistory: trustHistory.map((p) => ({ t: p.t, trust: p.trust })),
      events: events.slice().reverse().map((e) => ({ t: e.t, level: e.level, source: e.source, message: e.message })),
      ribEntries: ribEntries.map((e) => ({
        t: e.t,
        lp: e.lp,
        community: e.community,
        attempts: e.attempts,
        outcome: e.outcome,
        action: e.action,
      })),
      featureVector: r?.features ?? null,
      featureNames: FEATURE_NAMES,
      simTime: state.simTime,
    } as Parameters<typeof downloadForensicReport>[0];
  };

  const exportForensic = () => {
    const input = forensicInput();
    if (!input) return;
    const stamp = downloadForensicReport(input);
    return stamp;
  };

  /** open the report in a print window — browser print dialog supports "Save as PDF" */
  const printForensic = () => {
    const input = forensicInput();
    if (!input) return;
    try {
      const html = buildForensicReportHtml(input);
      const blob = new Blob([html], { type: 'text/html' });
      const url = URL.createObjectURL(blob);
      const w = window.open(url, '_blank', 'width=900,height=1000');
      if (w) {
        // give the new document a beat to layout, then bring up the print dialog
        w.addEventListener('load', () => {
          window.setTimeout(() => {
            w.focus();
            w.print();
          }, 250);
        });
        // release the blob URL after the window has it
        window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
      } else {
        // popup blocked — degrade to a download
        downloadForensicReport(input);
      }
    } catch {
      downloadForensicReport(input);
    }
  };

  /** copy the deep link (?tab=control&prefix=…) so operators can share/bookmark this forensic view */
  const [copied, setCopied] = useState(false);
  const copyDeepLink = async () => {
    if (!prefix) return;
    const url = `${window.location.origin}${window.location.pathname}?tab=control&prefix=${encodeURIComponent(prefix)}`;
    try {
      await navigator.clipboard.writeText(url);
    } catch {
      // clipboard API unavailable (insecure context) — fall back to a legacy path
      const ta = document.createElement('textarea');
      ta.value = url;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      try {
        document.execCommand('copy');
      } catch {
        /* give up silently */
      }
      document.body.removeChild(ta);
    }
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  };

  return (
    <Dialog open={prefix !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-4xl max-h-[88vh] overflow-y-auto bg-slate-950 border-slate-800 text-slate-200 p-0">
        {prefix && (
          <>
            {/* ---------- header ---------- */}
            <DialogHeader className="px-5 pt-5 pb-3 border-b border-slate-800 bg-gradient-to-b from-slate-900/60 to-transparent sticky top-0 z-10 backdrop-blur supports-[backdrop-filter]:bg-slate-950/85">
              <div className="flex items-center gap-2.5 flex-wrap pr-8">
                <Crosshair className="h-4 w-4 text-emerald-400 shrink-0" />
                <DialogTitle className="font-mono text-base font-bold text-slate-50 tracking-tight">
                  {prefix}
                </DialogTitle>
                <Badge variant="outline" className={`text-[9px] h-5 px-1.5 ${st.badge}`}>
                  <span className={`inline-block w-1.5 h-1.5 rounded-full mr-1 ${st.dot} ${r && r.status !== 'normal' ? 'animate-pulse' : ''}`} />
                  {st.label}
                </Badge>
                {trust && (
                  <span className={`font-mono text-sm font-semibold tabular-nums ${trustText(trust.score)}`}>
                    τ {trust.score.toFixed(3)}
                  </span>
                )}
                {r && (
                  <span className="text-[10px] font-mono text-slate-500">
                    LP <span className="text-slate-200 font-semibold">{r.route.locPref}</span>
                    {r.route.community ? ` · ${r.route.community}` : ''}
                  </span>
                )}
                <span className="ml-auto text-[10px] font-mono text-slate-600">
                  {runs.length > 0 ? `${runs.length} run(s) · ` : ''}
                  {events.length} events · {ribEntries.length} RIB commits · {trustHistory.length} τ samples
                </span>
                <button
                  onClick={() => {
                    exportForensic();
                  }}
                  disabled={events.length === 0 && trustHistory.length === 0}
                  title="download a standalone forensic HTML report for this prefix (run KPIs, defense comparison, trust trajectory, event timeline, RIB audit, feature vector)"
                  aria-label="export forensic report for this prefix"
                  className="inline-flex items-center gap-1 px-2 py-1 rounded border border-emerald-800 bg-emerald-950/50 text-[9px] font-mono text-emerald-300 hover:bg-emerald-900/50 transition-colors disabled:opacity-40 focus-visible:ring-1 focus-visible:ring-emerald-500"
                >
                  <FileDown className="h-3 w-3" /> export report
                </button>
                <button
                  onClick={printForensic}
                  disabled={events.length === 0 && trustHistory.length === 0}
                  title="print the forensic report — choose “Save as PDF” in the print dialog for a PDF copy"
                  aria-label="print or save as PDF the forensic report for this prefix"
                  className="inline-flex items-center gap-1 px-2 py-1 rounded border border-sky-800 bg-sky-950/50 text-[9px] font-mono text-sky-300 hover:bg-sky-900/50 transition-colors disabled:opacity-40 focus-visible:ring-1 focus-visible:ring-sky-500"
                >
                  <Printer className="h-3 w-3" /> print / pdf
                </button>
                <button
                  onClick={copyDeepLink}
                  title="copy a deep link to this prefix forensics view (?prefix=… survives reload, shareable)"
                  aria-label={`copy deep link for ${prefix}`}
                  className={`inline-flex items-center gap-1 px-2 py-1 rounded border text-[9px] font-mono transition-colors focus-visible:ring-1 focus-visible:ring-emerald-500 ${
                    copied
                      ? 'border-emerald-600 bg-emerald-900/60 text-emerald-200'
                      : 'border-slate-700 bg-slate-900/60 text-slate-300 hover:border-slate-500 hover:text-slate-100'
                  }`}
                >
                  {copied ? <CheckCircle2 className="h-3 w-3" /> : <Link2 className="h-3 w-3" />}
                  {copied ? ' copied' : ' copy link'}
                </button>
              </div>
              <DialogDescription className="text-[11px] font-mono text-slate-500">
                full per-prefix forensics — trust decomposition, trajectory, run lifecycle, event stream & RIB audit
              </DialogDescription>
            </DialogHeader>

            <div className="p-5 space-y-5">
              {!r && (
                <div className="rounded-lg border border-slate-800 bg-slate-900/40 px-4 py-3 flex items-center gap-2.5">
                  <AlertTriangle className="h-4 w-4 text-amber-400 shrink-0" />
                  <p className="text-[11px] font-mono text-slate-400">
                    route no longer in the RIB (withdrawn / reset) — showing historical evidence below.
                  </p>
                </div>
              )}

              {/* ---------- KPI strip ---------- */}
              {r && (
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                  {[
                    { icon: GitBranch, label: 'AS path', value: r.route.asPath, tone: 'text-sky-300' },
                    { icon: Scale, label: 'origin AS', value: String(r.route.originAs), tone: 'text-violet-300' },
                    { icon: Clock, label: 'route age', value: `${Math.round(state.simTime - r.route.lastUpdateEpoch)}s`, tone: 'text-cyan-300' },
                    {
                      icon: r.status === 'normal' ? ShieldCheck : ShieldAlert,
                      label: 'ML verdict',
                      value: r.ml ? `${r.ml.className} · ${Math.round(r.ml.confidence * 100)}%` : 'detector off',
                      tone: 'text-fuchsia-300',
                    },
                  ].map((k) => (
                    <div key={k.label} className="rounded-lg border border-slate-800 bg-slate-900/40 p-2.5">
                      <div className="flex items-center gap-1.5 text-[9px] font-mono uppercase tracking-wider text-slate-500">
                        <k.icon className="h-3 w-3" /> {k.label}
                      </div>
                      <div className={`mt-1 text-[12px] font-mono font-semibold break-all ${k.tone}`}>{k.value}</div>
                    </div>
                  ))}
                </div>
              )}

              {/* ---------- trust decomposition ---------- */}
              {contributions.length > 0 && (
                <section>
                  <h3 className="flex items-center gap-1.5 mb-2 text-[10px] font-semibold tracking-wider text-slate-400 uppercase">
                    <Scale className="h-3 w-3 text-teal-400" /> Trust composition · τ = Σ wᵢ·tᵢ
                  </h3>
                  <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-3 space-y-1.5">
                    {contributions.map((c) => (
                      <div key={c.key} className="grid grid-cols-[72px_1fr_44px_56px] items-center gap-2 group/c">
                        <span className="text-[10px] font-mono text-slate-500 uppercase">{c.key}</span>
                        <div className="h-2 rounded bg-slate-800 overflow-hidden relative">
                          <div
                            className={`h-full rounded transition-all duration-500 ${
                              c.value >= 0.85 ? 'bg-emerald-500' : c.value >= 0.55 ? 'bg-amber-500' : c.value >= 0.25 ? 'bg-orange-500' : 'bg-red-500'
                            }`}
                            style={{ width: `${Math.max(2, c.value * 100)}%` }}
                            title={`indicator ${c.value.toFixed(3)} × weight ${c.weight.toFixed(2)}`}
                          />
                          {/* weight marker */}
                          <div
                            className="absolute top-[-2px] bottom-[-2px] w-[2px] bg-violet-400/70"
                            style={{ left: `${c.weight * 100}%` }}
                            title={`weight ${c.weight.toFixed(2)}`}
                          />
                        </div>
                        <span className="text-right text-[10px] font-mono text-slate-400 tabular-nums">×{c.weight.toFixed(2)}</span>
                        <span
                          className={`text-right text-[11px] font-mono font-semibold tabular-nums ${
                            c.contribution >= 0.17 ? 'text-emerald-300' : c.contribution >= 0.1 ? 'text-amber-300' : 'text-red-400'
                          }`}
                        >
                          {c.contribution.toFixed(3)}
                        </span>
                      </div>
                    ))}
                    <div className="pt-1.5 mt-1.5 border-t border-slate-800 flex items-center justify-between text-[10px] font-mono">
                      <span className="text-slate-500">composite trust score</span>
                      <span className={`text-sm font-bold tabular-nums ${trustText(trust!.score)}`}>
                        {trust!.score.toFixed(3)}
                      </span>
                    </div>
                  </div>
                </section>
              )}

              {/* ---------- trust trajectory (full width chart) ---------- */}
              {chartData.length > 1 && (
                <section>
                  <div className="flex items-center gap-1.5 mb-2">
                    <Activity className="h-3 w-3 text-cyan-400" />
                    <h3 className="text-[10px] font-semibold tracking-wider text-slate-400 uppercase">
                      Trust trajectory · full history
                    </h3>
                    <span className="ml-auto text-[9px] font-mono text-slate-600">
                      {chartData.length} samples · min{' '}
                      <span className="text-slate-400 tabular-nums">{Math.min(...chartData.map((d) => d.trust)).toFixed(3)}</span> · now{' '}
                      <span className={trustText(chartData[chartData.length - 1].trust)}>
                        {chartData[chartData.length - 1].trust.toFixed(3)}
                      </span>
                    </span>
                  </div>
                  <div className="rounded-lg border border-slate-800 bg-slate-900/40 px-2 pt-2 pb-1 h-[190px]">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={chartData} margin={{ top: 4, right: 8, bottom: 0, left: -22 }}>
                        <defs>
                          <linearGradient id="drillTrustFill" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor={trustStroke(chartData[chartData.length - 1].trust)} stopOpacity={0.28} />
                            <stop offset="100%" stopColor={trustStroke(chartData[chartData.length - 1].trust)} stopOpacity={0.02} />
                          </linearGradient>
                        </defs>
                        <CartesianGrid stroke="#1e293b" strokeDasharray="2 4" vertical={false} />
                        <XAxis
                          dataKey="t"
                          type="number"
                          domain={['dataMin', 'dataMax']}
                          tick={{ fill: '#475569', fontSize: 9, fontFamily: 'monospace' }}
                          tickFormatter={(v: number) => `${Math.round(v / 60)}m`}
                          minTickGap={42}
                          axisLine={{ stroke: '#1e293b' }}
                          tickLine={false}
                        />
                        <YAxis
                          domain={[0, 1]}
                          tick={{ fill: '#475569', fontSize: 9, fontFamily: 'monospace' }}
                          tickFormatter={(v: number) => v.toFixed(2)}
                          axisLine={false}
                          tickLine={false}
                        />
                        <RTooltip
                          contentStyle={{
                            background: '#020617',
                            border: '1px solid #1e293b',
                            borderRadius: 6,
                            fontSize: 10,
                            fontFamily: 'monospace',
                          }}
                          labelFormatter={(v: number) => `t = ${v}s`}
                          formatter={(v: number) => [v.toFixed(3), 'trust τ']}
                        />
                        <ReferenceLine y={state.config.policy.thresholds.normal} stroke="#34d399" strokeDasharray="4 3" strokeOpacity={0.6} />
                        <ReferenceLine y={state.config.policy.thresholds.suspicious} stroke="#fbbf24" strokeDasharray="4 3" strokeOpacity={0.6} />
                        <ReferenceLine y={state.config.policy.thresholds.leak} stroke="#fb923c" strokeDasharray="4 3" strokeOpacity={0.6} />
                        <Area
                          type="monotone"
                          dataKey="trust"
                          stroke="none"
                          fill="url(#drillTrustFill)"
                          isAnimationActive={false}
                        />
                        <Line
                          type="monotone"
                          dataKey="trust"
                          stroke={trustStroke(chartData[chartData.length - 1].trust)}
                          strokeWidth={2}
                          dot={false}
                          isAnimationActive={false}
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                </section>
              )}

              {/* ---------- run lifecycle timeline ---------- */}
              {runs.length > 0 && (
                <section>
                  <div className="flex items-center gap-1.5 mb-2">
                    <ListOrdered className="h-3 w-3 text-violet-400" />
                    <h3 className="text-[10px] font-semibold tracking-wider text-slate-400 uppercase">
                      Attack run lifecycle · {prefix}
                    </h3>
                  </div>
                  <div className="space-y-2">
                    {runs.slice(0, 6).map((run) => {
                      const end = run.rolledBackAt ?? run.mitigatedAt ?? state.simTime;
                      const span = Math.max(end - run.injectedAt, 1);
                      const seg = (from: number, to: number) => `${Math.max(((to - run.injectedAt) / span) * 100 - ((from - run.injectedAt) / span) * 100, 0.5)}%`;
                      const left = (t: number) => `${Math.max(Math.min(((t - run.injectedAt) / span) * 100, 100), 0)}%`;
                      return (
                        <div key={`${run.runId}-${run.injectedAt}`} className="rounded-lg border border-slate-800 bg-slate-900/40 p-3">
                          <div className="flex items-center gap-2 flex-wrap text-[10px] font-mono mb-2">
                            <span className="text-slate-300 font-semibold">#{run.runId} · {run.scenarioId}</span>
                            <span className="text-slate-600">{run.scenarioName}</span>
                            <span className="text-slate-600">variant {run.phase === 'rolledback' ? '' : ''}{run.comparison ? '' : ''}</span>
                            {run.mttd !== null && <span className="text-amber-300">MTTD {run.mttd}s</span>}
                            {run.mttm !== null && <span className="text-orange-300">MTTM {run.mttm}s</span>}
                            {run.ribVerified && <span className="text-emerald-300">RIB ✓</span>}
                            <span className="ml-auto text-slate-600">
                              ground truth {CLASS_NAMES[run.groundTruth]}
                              {run.detectedClass !== null ? ` → detected ${CLASS_NAMES[run.detectedClass]}` : ' → undetected'}
                            </span>
                          </div>
                          {/* phase band */}
                          <div className="relative h-6 rounded overflow-hidden bg-slate-800/60 flex">
                            {run.detectedAt !== null && (
                              <div className={`${PHASE_TONE.injected.bg} flex items-center justify-center`} style={{ width: seg(run.injectedAt, run.detectedAt) }} title={`injected t=${run.injectedAt}s`} />
                            )}
                            {run.detectedAt !== null && run.mitigatedAt !== null && (
                              <div className={`${PHASE_TONE.detected.bg} flex items-center justify-center`} style={{ width: seg(run.detectedAt, run.mitigatedAt) }} title="detection → mitigation" />
                            )}
                            {run.mitigatedAt !== null && run.rolledBackAt !== null && (
                              <div className={`${PHASE_TONE.mitigated.bg} flex items-center justify-center`} style={{ width: seg(run.mitigatedAt, run.rolledBackAt) }} title="quarantine dwell" />
                            )}
                            {run.rolledBackAt !== null && (
                              <div className={`${PHASE_TONE.rolledback.bg} flex items-center justify-center`} style={{ width: seg(run.rolledBackAt, end + span) }} title={`rollback t=${run.rolledBackAt}s`} />
                            )}
                            {run.phase === 'failed' && (
                              <div className={`${PHASE_TONE.failed.bg} flex items-center justify-center w-full`} title="failed" />
                            )}
                          </div>
                          {/* time markers */}
                          <div className="relative h-4 mt-0.5 text-[8.5px] font-mono text-slate-600 tabular-nums">
                            <span className="absolute left-0">t={run.injectedAt}s</span>
                            {run.detectedAt !== null && (
                              <span className="absolute -translate-x-1/2 text-amber-400" style={{ left: left(run.detectedAt) }}>
                                ▲{run.detectedAt}s
                              </span>
                            )}
                            {run.mitigatedAt !== null && (
                              <span className="absolute -translate-x-1/2 text-red-400" style={{ left: left(run.mitigatedAt) }}>
                                ▼{run.mitigatedAt}s
                              </span>
                            )}
                            {run.rolledBackAt !== null && (
                              <span className="absolute -translate-x-1/2 text-emerald-400" style={{ left: left(run.rolledBackAt) }}>
                                ●{run.rolledBackAt}s
                              </span>
                            )}
                            <span className="absolute right-0">t={Math.round(end)}s</span>
                          </div>
                          {run.appliedPolicy && (
                            <div className="mt-1.5 text-[9.5px] font-mono text-slate-500">
                              policy: <span className="text-orange-300">{run.appliedPolicy}</span>
                              {run.appliedLocPref !== null && <> · applied LP <span className="text-slate-300">{run.appliedLocPref}</span></>}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </section>
              )}

              {/* ---------- per-prefix event stream + RIB audit ---------- */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <section>
                  <div className="flex items-center gap-1.5 mb-2">
                    <Radar className="h-3 w-3 text-sky-400" />
                    <h3 className="text-[10px] font-semibold tracking-wider text-slate-400 uppercase">
                      Event stream · newest first
                    </h3>
                  </div>
                  <div className="rounded-lg border border-slate-800 bg-slate-900/40 max-h-56 overflow-y-auto scrollbar-thin divide-y divide-slate-900">
                    {events.length === 0 ? (
                      <p className="py-6 text-center text-[10px] font-mono text-slate-600">no events mention this prefix</p>
                    ) : (
                      events.map((e) => (
                        <div key={e.id} className="px-2.5 py-1.5 flex gap-2 text-[10px] font-mono hover:bg-slate-900/60 transition-colors">
                          <span className="text-slate-600 shrink-0 tabular-nums w-10 text-right">{e.t}s</span>
                          <span className={`${LEVEL_STYLE[e.level] ?? 'text-slate-400'} shrink-0 w-[64px] truncate`}>{e.source}</span>
                          <span className="text-slate-400 min-w-0">{e.message}</span>
                        </div>
                      ))
                    )}
                  </div>
                </section>

                <section>
                  <div className="flex items-center gap-1.5 mb-2">
                    <ListOrdered className="h-3 w-3 text-amber-400" />
                    <h3 className="text-[10px] font-semibold tracking-wider text-slate-400 uppercase">
                      RIB commit audit
                    </h3>
                    {ribEntries.length > 0 && (
                      <span className="ml-auto text-[9px] font-mono text-slate-600">
                        {ribEntries.filter((e) => e.outcome === 'verified').length}/{ribEntries.length} verified
                      </span>
                    )}
                  </div>
                  <div className="rounded-lg border border-slate-800 bg-slate-900/40 max-h-56 overflow-y-auto scrollbar-thin">
                    {ribEntries.length === 0 ? (
                      <p className="py-6 text-center text-[10px] font-mono text-slate-600">no RIB commits for this prefix</p>
                    ) : (
                      <table className="w-full text-[10px] font-mono">
                        <thead className="sticky top-0 bg-slate-950/95">
                          <tr className="text-slate-500">
                            <th className="text-left py-1 px-2 font-medium">t</th>
                            <th className="text-center py-1 px-1 font-medium">LP</th>
                            <th className="text-center py-1 px-1 font-medium">try</th>
                            <th className="text-left py-1 px-2 font-medium">result</th>
                          </tr>
                        </thead>
                        <tbody>
                          {ribEntries.slice().reverse().map((e) => (
                            <tr key={e.id} className={`border-t border-slate-900/60 ${e.outcome === 'failed' ? 'bg-red-950/10' : ''}`}>
                              <td className="py-1 px-2 text-slate-500 tabular-nums">{e.t}s</td>
                              <td className={`py-1 px-1 text-center font-bold ${e.lp >= state.config.policy.lpNormal ? 'text-emerald-300' : e.lp > 0 ? 'text-amber-300' : 'text-red-400'}`}>
                                {e.lp}
                              </td>
                              <td className="py-1 px-1 text-center text-slate-500">{e.attempts}×</td>
                              <td className="py-1 px-2">
                                <span className="inline-flex items-center gap-1">
                                  {e.outcome === 'verified' ? (
                                    <>
                                      <CheckCircle2 className="h-3 w-3 text-emerald-400" />
                                      <span className="text-emerald-300">verified</span>
                                    </>
                                  ) : (
                                    <>
                                      <XCircle className="h-3 w-3 text-red-500" />
                                      <span className="text-red-400">failed</span>
                                    </>
                                  )}
                                  <span className="text-slate-600 truncate max-w-36 inline-block" title={e.action}>{e.action}</span>
                                </span>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )}
                  </div>
                </section>
              </div>

              {/* ---------- current feature vector ---------- */}
              {r && (
                <section>
                  <div className="flex items-center gap-1.5 mb-2">
                    <Activity className="h-3 w-3 text-violet-400" />
                    <h3 className="text-[10px] font-semibold tracking-wider text-slate-400 uppercase">
                      10-feature behavioral vector · live
                    </h3>
                  </div>
                  <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-3 grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-1">
                    {FEATURE_NAMES.map((name, i) => {
                      const v = r.features[i];
                      const norm = Math.min(1, Math.max(0, v / 25));
                      return (
                        <div key={name} className="flex items-center gap-2">
                          <span className="w-40 shrink-0 text-[10px] font-mono text-slate-500 truncate">{name}</span>
                          <div className="flex-1 h-1.5 rounded bg-slate-800 overflow-hidden">
                            <div
                              className={`h-full rounded transition-all ${norm > 0.6 ? 'bg-red-500/80' : norm > 0.35 ? 'bg-amber-500/80' : 'bg-emerald-500/70'}`}
                              style={{ width: `${Math.max(3, norm * 100)}%` }}
                            />
                          </div>
                          <span className="w-12 shrink-0 text-right text-[10px] font-mono text-slate-300 tabular-nums">{v}</span>
                        </div>
                      );
                    })}
                  </div>
                </section>
              )}
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
