'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { Database, RefreshCw, Loader2, Eye, ShieldCheck, Timer } from 'lucide-react';

interface ArchivedRun {
  id: string;
  runId: number;
  scenarioId: string;
  variantLabel: string;
  mttd: number | null;
  mttm: number | null;
  msr: boolean;
  detectedClass: number | null;
  phase: string;
}

interface VariantStat {
  label: string;
  runs: number;
  detected: number;
  mitigated: number;
  mttds: number[];
  mttms: number[];
  scenarios: Set<string>;
}

const VARIANT_TONE: { match: RegExp; tone: string; bar: string }[] = [
  { match: /^A0/, tone: 'text-slate-400', bar: 'bg-slate-500' },
  { match: /^A1/, tone: 'text-lime-300', bar: 'bg-lime-500' },
  { match: /^A2/, tone: 'text-cyan-300', bar: 'bg-cyan-500' },
  { match: /^A3/, tone: 'text-teal-300', bar: 'bg-teal-500' },
  { match: /^A4/, tone: 'text-emerald-300', bar: 'bg-emerald-500' },
];

function toneFor(label: string) {
  return VARIANT_TONE.find((v) => v.match.test(label)) ?? { tone: 'text-violet-300', bar: 'bg-violet-500' };
}

function avg(nums: number[]): number | null {
  if (nums.length === 0) return null;
  return nums.reduce((a, b) => a + b, 0) / nums.length;
}

/**
 * Variant performance aggregated from the PERSISTED run archive (SQLite) —
 * the long-horizon ablation story across every run ever recorded, as opposed
 * to the live engine history which resets with the reviewer cadence.
 */
export function VariantPerformance() {
  const [runs, setRuns] = useState<ArchivedRun[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch('/api/sim-runs');
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error ?? `HTTP ${res.status}`);
      setRuns(data.runs ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const stats: VariantStat[] = React.useMemo(() => {
    if (!runs) return [];
    const byVariant = new Map<string, VariantStat>();
    for (const r of runs) {
      if (!byVariant.has(r.variantLabel)) {
        byVariant.set(r.variantLabel, {
          label: r.variantLabel,
          runs: 0,
          detected: 0,
          mitigated: 0,
          mttds: [],
          mttms: [],
          scenarios: new Set(),
        });
      }
      const v = byVariant.get(r.variantLabel)!;
      v.runs += 1;
      if (r.detectedClass !== null) v.detected += 1;
      if (r.msr) v.mitigated += 1;
      if (r.mttd !== null) v.mttds.push(r.mttd);
      if (r.mttm !== null) v.mttms.push(r.mttm);
      v.scenarios.add(r.scenarioId);
    }
    return Array.from(byVariant.values()).sort((a, b) => b.runs - a.runs || b.mitigated - a.mitigated);
  }, [runs]);

  const maxRuns = Math.max(...stats.map((s) => s.runs), 1);

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3">
      <div className="flex items-center justify-between mb-2 gap-2 flex-wrap">
        <div className="flex items-center gap-2">
          <Database className="h-4 w-4 text-teal-400" />
          <span className="text-xs font-semibold text-slate-200">Variant Performance · Run Archive</span>
          <span className="text-[10px] font-mono text-slate-600 hidden sm:inline">
            {runs ? `${runs.length} persisted runs · ${stats.length} variants` : 'loading archive…'}
          </span>
        </div>
        <button
          onClick={load}
          disabled={loading}
          title="reload from the SQLite run archive"
          aria-label="reload variant performance"
          className="inline-flex items-center gap-1 px-2 py-1 rounded border border-slate-800 text-[9.5px] font-mono text-slate-500 hover:text-teal-300 hover:border-teal-800 transition-colors disabled:opacity-50"
        >
          {loading ? <Loader2 className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />} reload
        </button>
      </div>

      {error && (
        <div className="text-[10.5px] font-mono text-red-400 py-2">
          archive unavailable — {error}
        </div>
      )}

      {runs && stats.length === 0 && (
        <div className="py-4 text-center text-[11px] font-mono text-slate-600">no persisted runs yet</div>
      )}

      {stats.length > 0 && (
        <div className="space-y-1.5">
          {/* column header */}
          <div className="hidden sm:grid grid-cols-[minmax(140px,1.2fr)_44px_repeat(4,minmax(72px,1fr))] gap-2 px-2 text-[8.5px] font-mono uppercase tracking-wider text-slate-600">
            <span>variant</span>
            <span className="text-right">runs</span>
            <span>detection rate</span>
            <span>mitigation (MSR)</span>
            <span>avg MTTD</span>
            <span>avg MTTM</span>
          </div>
          {stats.map((v) => {
            const tone = toneFor(v.label);
            const detPct = Math.round((v.detected / v.runs) * 100);
            const msrPct = Math.round((v.mitigated / v.runs) * 100);
            const aMttd = avg(v.mttds);
            const aMttm = avg(v.mttms);
            return (
              <div
                key={v.label}
                className="grid grid-cols-2 sm:grid-cols-[minmax(140px,1.2fr)_44px_repeat(4,minmax(72px,1fr))] gap-x-2 gap-y-1.5 items-center rounded border border-slate-800/70 bg-slate-900/40 px-2 py-1.5 hover:border-slate-700 transition-colors"
              >
                {/* variant label + scenario coverage */}
                <div className="col-span-2 sm:col-span-1 min-w-0">
                  <div className="flex items-center gap-1.5">
                    <span className={`text-[11px] font-mono font-semibold truncate ${tone.tone}`}>{v.label}</span>
                    <span
                      className="shrink-0 h-1.5 rounded-full bg-slate-800 overflow-hidden relative"
                      style={{ width: `${Math.max(12, (v.runs / maxRuns) * 60)}px` }}
                      title={`${v.runs} runs`}
                    >
                      <span className={`absolute inset-y-0 left-0 rounded-full ${tone.bar}`} style={{ width: '100%' }} />
                    </span>
                  </div>
                  <div className="text-[8.5px] font-mono text-slate-600 truncate">
                    {v.scenarios.size} scenario{v.scenarios.size !== 1 ? 's' : ''} · {[...v.scenarios].sort().join(' ')}
                  </div>
                </div>

                <div className="hidden sm:block text-right text-[11px] font-mono font-bold text-slate-300 tabular-nums">{v.runs}</div>

                {/* detection rate bar */}
                <div>
                  <div className="flex items-center gap-1 h-4">
                    <Eye className={`h-2.5 w-2.5 shrink-0 ${detPct >= 50 ? 'text-cyan-400' : 'text-slate-600'}`} />
                    <div className="flex-1 h-1.5 rounded bg-slate-800 overflow-hidden">
                      <div
                        className={`h-full rounded transition-all duration-700 ${detPct >= 80 ? 'bg-cyan-500' : detPct >= 40 ? 'bg-cyan-600/70' : 'bg-cyan-800/60'}`}
                        style={{ width: `${Math.max(detPct, 2)}%` }}
                      />
                    </div>
                  </div>
                  <div className="text-[8.5px] font-mono text-slate-500 tabular-nums">{detPct}%</div>
                </div>

                {/* MSR bar */}
                <div>
                  <div className="flex items-center gap-1 h-4">
                    <ShieldCheck className={`h-2.5 w-2.5 shrink-0 ${msrPct >= 50 ? 'text-emerald-400' : 'text-red-400/70'}`} />
                    <div className="flex-1 h-1.5 rounded bg-slate-800 overflow-hidden">
                      <div
                        className={`h-full rounded transition-all duration-700 ${msrPct >= 80 ? 'bg-emerald-500' : msrPct >= 40 ? 'bg-emerald-600/70' : 'bg-emerald-900'}`}
                        style={{ width: `${Math.max(msrPct, 2)}%` }}
                      />
                    </div>
                  </div>
                  <div className="text-[8.5px] font-mono text-slate-500 tabular-nums">{msrPct}%</div>
                </div>

                {/* avg MTTD / MTTM */}
                <div className="text-[10.5px] font-mono tabular-nums">
                  {aMttd !== null ? (
                    <span className="flex items-center gap-1">
                      <Timer className="h-2.5 w-2.5 text-amber-400/80 shrink-0" />
                      <span className="text-amber-300">{aMttd.toFixed(1)}s</span>
                    </span>
                  ) : (
                    <span className="text-slate-600">—</span>
                  )}
                </div>
                <div className="text-[10.5px] font-mono tabular-nums">
                  {aMttm !== null ? (
                    <span className="flex items-center gap-1">
                      <Timer className="h-2.5 w-2.5 text-orange-400/80 shrink-0" />
                      <span className="text-orange-300">{aMttm.toFixed(1)}s</span>
                    </span>
                  ) : (
                    <span className="text-slate-600">—</span>
                  )}
                </div>
              </div>
            );
          })}

          <p className="pt-1 text-[9px] font-mono text-slate-600 leading-relaxed">
            aggregated from the SQLite run archive (every completed run since deployment) — the live engine history resets
            with the review cadence, this view does not.
          </p>
        </div>
      )}
    </div>
  );
}
