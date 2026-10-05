'use client';

import React, { useState } from 'react';
import { SimState, RunResult, ATTACK_SCENARIOS } from '@/lib/bgp-sim/types';
import {
  ResponsiveContainer,
  RadarChart,
  Radar,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Tooltip as RTooltip,
  Legend,
} from 'recharts';
import { Crosshair, Zap, Timer, ShieldCheck, Eye } from 'lucide-react';
import { Badge } from '@/components/ui/badge';

interface ScenarioAgg {
  id: string;
  name: string;
  runs: number;
  detected: number;
  mitigated: number;
  mttds: number[];
  mttms: number[];
  ribOk: number;
  bestMttd: number | null;
  worstMttd: number | null;
  comparison: {
    standardBgp: number;
    rpki: number;
    heuristic: number;
    aiControl: number;
  } | null;
}

function aggregate(state: SimState): ScenarioAgg[] {
  const all: RunResult[] = [...state.history];
  if (state.activeRun) all.push(state.activeRun);
  const map = new Map<string, RunResult[]>();
  for (const r of all) {
    if (!map.has(r.scenarioId)) map.set(r.scenarioId, []);
    map.get(r.scenarioId)!.push(r);
  }
  return ATTACK_SCENARIOS.filter((s) => s.id !== 'CX').map((s) => {
    const runs = map.get(s.id) ?? [];
    const detected = runs.filter((r) => r.detectedAt !== null);
    const mitigated = runs.filter((r) => r.msr);
    const mttds = detected.map((r) => r.mttd ?? 0);
    const mttms = mitigated.map((r) => r.mttm ?? 0);
    const latest = runs[runs.length - 1];
    const cmp = latest
      ? {
          standardBgp: runs.filter((r) => r.comparison.standardBgp.detected).length,
          rpki: runs.filter((r) => r.comparison.rpki.detected).length,
          heuristic: runs.filter((r) => r.comparison.heuristic.detected).length,
          aiControl: runs.filter((r) => r.comparison.aiControl.detected).length,
        }
      : null;
    return {
      id: s.id,
      name: s.shortName,
      runs: runs.length,
      detected: detected.length,
      mitigated: mitigated.length,
      mttds,
      mttms,
      ribOk: runs.filter((r) => r.ribVerified).length,
      bestMttd: mttds.length ? Math.min(...mttds) : null,
      worstMttd: mttds.length ? Math.max(...mttds) : null,
      comparison: cmp,
    };
  }).filter((a) => a.runs > 0);
}

/** defense-detection radar: how often each defense saw the scenario (per run, %) */
function radarData(aggs: ScenarioAgg[]) {
  return [
    { defense: 'AI Control', key: 'aiControl' },
    { defense: 'Heuristics', key: 'heuristic' },
    { defense: 'RPKI ROV', key: 'rpki' },
    { defense: 'Std BGP', key: 'standardBgp' },
  ].map(({ defense, key }) => {
    const row: Record<string, string | number> = { defense };
    for (const a of aggs) {
      row[a.id] = a.comparison ? Math.round((a.comparison[key as keyof typeof a.comparison] / a.runs) * 100) : 0;
    }
    return row;
  });
}

const SCENARIO_COLORS: Record<string, string> = {
  S1: '#34d399',
  S2: '#f87171',
  S3: '#fbbf24',
  S4: '#fb923c',
  S5: '#38bdf8',
  S6: '#f472b6',
};

export function ScenarioDeepDive({ state }: { state: SimState }) {
  // aggregate per scenario (history + active run)
  const aggs = aggregate(state);
  const [selected, setSelected] = useState<string | null>(null);
  const activeId = selected ?? aggs[0]?.id ?? null;
  const current = aggs.find((a) => a.id === activeId) ?? aggs[0];
  const data = radarData(aggs);

  if (aggs.length === 0) {
    return (
      <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3">
        <div className="flex items-center gap-2 mb-2">
          <Crosshair className="h-4 w-4 text-fuchsia-400" />
          <span className="text-xs font-semibold text-slate-200">Per-Scenario Deep-Dive</span>
        </div>
        <div className="py-6 text-center text-[11px] font-mono text-slate-600">
          no scenario data yet — inject attacks (or run the auto-benchmark sweep) to populate this analysis
        </div>
      </div>
    );
  }

  const activeScenarios = aggs.map((a) => a.id);
  const avg = (xs: number[]) => (xs.length ? xs.reduce((x, y) => x + y, 0) / xs.length : null);

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3">
      <div className="flex items-center justify-between mb-2 flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <Crosshair className="h-4 w-4 text-fuchsia-400" />
          <span className="text-xs font-semibold text-slate-200">Per-Scenario Deep-Dive</span>
          <span className="text-[10px] font-mono text-slate-600">{aggs.length} scenarios · {aggs.reduce((s, a) => s + a.runs, 0)} runs</span>
        </div>
        <div className="flex flex-wrap gap-1">
          {aggs.map((a) => (
            <button
              key={a.id}
              onClick={() => setSelected(a.id)}
              className={`px-2 py-0.5 rounded text-[9.5px] font-mono border transition-colors ${
                activeId === a.id
                  ? 'border-fuchsia-700 text-fuchsia-200 bg-fuchsia-950/40'
                  : 'border-slate-800 text-slate-500 hover:text-slate-300 hover:border-slate-700'
              }`}
            >
              {a.id}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-3">
        {/* radar: defense detection rate per selected scenario */}
        <div>
          <div className="flex items-center gap-1.5 mb-1">
            <Eye className="h-3 w-3 text-slate-500" />
            <span className="text-[10px] font-mono text-slate-400">
              detection rate by defense — {current.name} ({current.runs} runs)
            </span>
          </div>
          <div className="h-60">
            <ResponsiveContainer width="100%" height="100%">
              <RadarChart data={data} outerRadius="72%">
                <PolarGrid stroke="#1e293b" />
                <PolarAngleAxis dataKey="defense" tick={{ fill: '#94a3b8', fontSize: 10, fontFamily: 'monospace' }} />
                <PolarRadiusAxis domain={[0, 100]} tick={{ fill: '#475569', fontSize: 8.5, fontFamily: 'monospace' }} stroke="#1e293b" />
                <RTooltip
                  contentStyle={{ background: '#020617', border: '1px solid #334155', borderRadius: 8, fontSize: 11, fontFamily: 'monospace' }}
                  formatter={(v: number, name: string) => [`${v}%`, name]}
                />
                {activeScenarios.map((sid) => (
                  <Radar
                    key={sid}
                    name={sid}
                    dataKey={sid}
                    stroke={SCENARIO_COLORS[sid] ?? '#94a3b8'}
                    fill={SCENARIO_COLORS[sid] ?? '#94a3b8'}
                    fillOpacity={activeId === sid ? 0.35 : 0.06}
                    strokeWidth={activeId === sid ? 2 : 1}
                    isAnimationActive={false}
                  />
                ))}
                <Legend wrapperStyle={{ fontSize: 10, fontFamily: 'monospace', color: '#94a3b8' }} />
              </RadarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* selected scenario stats */}
        <div className="space-y-1.5">
          <div className="text-[10.5px] font-mono font-semibold text-slate-300">{current.name}</div>
          {[
            { icon: Zap, label: 'runs', value: `${current.runs}`, tone: 'text-slate-200' },
            { icon: Eye, label: 'detected', value: `${current.detected}/${current.runs} (${Math.round((current.detected / current.runs) * 100)}%)`, tone: 'text-cyan-300' },
            { icon: ShieldCheck, label: 'mitigated (MSR)', value: `${current.mitigated}/${current.runs} (${Math.round((current.mitigated / current.runs) * 100)}%)`, tone: 'text-emerald-300' },
            { icon: Timer, label: 'avg MTTD', value: avg(current.mttds) !== null ? `${avg(current.mttds)!.toFixed(1)}s` : '—', tone: 'text-amber-300' },
            { icon: Timer, label: 'avg MTTM', value: avg(current.mttms) !== null ? `${avg(current.mttms)!.toFixed(1)}s` : '—', tone: 'text-orange-300' },
            { icon: Timer, label: 'best / worst MTTD', value: current.bestMttd !== null ? `${current.bestMttd}s / ${current.worstMttd}s` : '—', tone: 'text-slate-300' },
          ].map((s) => (
            <div key={s.label} className="flex items-center justify-between rounded border border-slate-800/60 bg-slate-900/40 px-2 py-1">
              <div className="flex items-center gap-1.5 text-[9.5px] font-mono text-slate-500">
                <s.icon className="h-3 w-3" /> {s.label}
              </div>
              <span className={`text-[10.5px] font-mono ${s.tone}`}>{s.value}</span>
            </div>
          ))}
          {current.comparison && (
            <div className="flex flex-wrap gap-1 pt-0.5">
              <Badge variant="outline" className="text-[9px] h-4 px-1.5 border-slate-700 text-slate-500">
                std-bgp {current.comparison.standardBgp}/{current.runs}
              </Badge>
              <Badge variant="outline" className="text-[9px] h-4 px-1.5 border-sky-800 text-sky-300 bg-sky-950/30">
                rpki {current.comparison.rpki}/{current.runs}
              </Badge>
              <Badge variant="outline" className="text-[9px] h-4 px-1.5 border-amber-800 text-amber-300 bg-amber-950/30">
                heur {current.comparison.heuristic}/{current.runs}
              </Badge>
              <Badge variant="outline" className="text-[9px] h-4 px-1.5 border-emerald-800 text-emerald-300 bg-emerald-950/30">
                ai {current.comparison.aiControl}/{current.runs}
              </Badge>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
