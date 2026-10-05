'use client';

import React, { useState } from 'react';
import { ATTACK_SCENARIOS, CustomAttackSpec, RunPhase } from '@/lib/bgp-sim/types';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Slider } from '@/components/ui/slider';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { AlertTriangle, Crosshair, History, Undo2, Zap } from 'lucide-react';

interface Props {
  activeScenarioId: string | null;
  activePhase?: RunPhase | null;
  activeElapsedSec?: number;
  activeRemainingSec?: number | null;
  onInject: (scenarioId: string, durationSec?: number) => void;
  onWithdraw: () => void;
  onCustom: (spec: CustomAttackSpec) => void;
}

/** live phase wording for the active scenario card */
const LIVE_PHASE: Record<RunPhase, { label: string; tone: string; bar: string }> = {
  idle: { label: 'idle', tone: 'text-slate-500', bar: 'bg-slate-700' },
  injected: { label: 'propagating through testbed…', tone: 'text-amber-300', bar: 'bg-gradient-to-r from-amber-500 to-orange-500' },
  detected: { label: 'detected — policy engaging…', tone: 'text-orange-300', bar: 'bg-gradient-to-r from-orange-500 to-red-500' },
  mitigated: { label: 'quarantined · LP 0 + no-export', tone: 'text-red-300', bar: 'bg-red-600' },
  rolledback: { label: 'rolled back — trust restored', tone: 'text-emerald-300', bar: 'bg-emerald-600' },
  failed: { label: 'mitigation failed', tone: 'text-red-400', bar: 'bg-red-800' },
};

const CLASS_TONE: Record<number, string> = {
  3: 'text-red-400 border-red-900 bg-red-950/40',
  2: 'text-orange-400 border-orange-900 bg-orange-950/40',
  1: 'text-amber-400 border-amber-900 bg-amber-950/40',
  0: 'text-emerald-400 border-emerald-900 bg-emerald-950/40',
};

/** threat severity: 5-segment meter, red = hijack-tier, orange = leak, amber = churn */
const SEVERITY: Record<string, { level: number; label: string; seg: string }> = {
  S1: { level: 4, label: 'sev 4/5', seg: 'bg-red-500' },
  S2: { level: 5, label: 'sev 5/5', seg: 'bg-red-500' },
  S3: { level: 2, label: 'sev 2/5', seg: 'bg-amber-500' },
  S4: { level: 5, label: 'sev 5/5', seg: 'bg-red-500' },
  S5: { level: 3, label: 'sev 3/5', seg: 'bg-orange-500' },
  S6: { level: 3, label: 'sev 3/5', seg: 'bg-orange-500' },
};

function SeverityMeter({ level, seg, label }: { level: number; seg: string; label: string }) {
  return (
    <span className="flex items-center gap-1" title={`threat severity ${label}`} aria-label={`threat severity ${level} of 5`}>
      <span className="flex gap-0.5">
        {[1, 2, 3, 4, 5].map((i) => (
          <span key={i} className={`w-1 h-2 rounded-[1px] ${i <= level ? seg : 'bg-slate-800'}`} />
        ))}
      </span>
      <span className="text-[8.5px] font-mono text-slate-500 tabular-nums">{label}</span>
    </span>
  );
}

export function AttackPanel({ activeScenarioId, activePhase, activeElapsedSec = 0, activeRemainingSec = null, onInject, onWithdraw, onCustom }: Props) {
  const [prefix, setPrefix] = useState('203.0.113.0/24');
  const [originAs, setOriginAs] = useState('65010');
  const [asPath, setAsPath] = useState('65001 65002 65006 65010');
  const [duration, setDuration] = useState(120);
  const [flapping, setFlapping] = useState(false);
  const [flapInterval, setFlapInterval] = useState(5);
  const [customError, setCustomError] = useState<string | null>(null);
  const [advanced, setAdvanced] = useState(false);

  const submitCustom = () => {
    setCustomError(null);
    const spec: CustomAttackSpec = {
      prefix: prefix.trim(),
      originAs: parseInt(originAs, 10) || 65010,
      asPath: asPath.trim(),
      maskLen: parseInt(prefix.split('/')[1] ?? '24', 10) || 24,
      durationSec: duration,
      flapping,
      flapIntervalSec: flapInterval,
    };
    if (!/^\d{1,3}(\.\d{1,3}){3}\/\d{1,2}$/.test(spec.prefix)) {
      setCustomError('Prefix must look like 203.0.113.0/24');
      return;
    }
    if (!spec.asPath.split(/\s+/).every((t) => /^\d+$/.test(t)) || !spec.asPath.trim()) {
      setCustomError('AS-Path must be space-separated AS numbers');
      return;
    }
    onCustom(spec);
  };

  return (
    <TooltipProvider delayDuration={120}>
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Crosshair className="h-4 w-4 text-red-400" />
            <span className="text-sm font-semibold text-slate-100">Attack Injection</span>
          </div>
          {activeScenarioId && (
            <Button
              size="sm"
              variant="outline"
              onClick={onWithdraw}
              className="h-7 text-[11px] font-mono border-amber-700 text-amber-300 hover:bg-amber-950/50"
            >
              <Undo2 className="h-3 w-3 mr-1" /> withdraw
            </Button>
          )}
        </div>

        <div className="space-y-2">
          {ATTACK_SCENARIOS.map((s) => {
            const active = activeScenarioId === s.id;
            return (
              <Tooltip key={s.id}>
                <TooltipTrigger asChild>
                  <button
                    onClick={() => onInject(s.id)}
                    className={`attack-card w-full text-left rounded-lg border p-2.5 group ${
                      active
                        ? 'attack-card-active border-red-500 bg-red-950/40'
                        : 'border-slate-800 bg-slate-950/60 hover:border-slate-600'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2 mb-1">
                      <span className={`text-xs font-mono font-semibold ${active ? 'text-red-300' : 'text-slate-200'}`}>
                        {s.shortName}
                      </span>
                      <Badge variant="outline" className={`text-[9px] px-1.5 h-4 ${CLASS_TONE[s.groundTruthClass]}`}>
                        {s.groundTruthClass === 3 ? 'HIJACK' : s.groundTruthClass === 2 ? 'LEAK' : 'CHURN'}
                      </Badge>
                    </div>
                    <div className="flex items-center justify-between gap-2 mb-1">
                      <div className="text-[10px] font-mono text-slate-500 truncate">
                        {s.prefix} · AS{s.injectedOrigin} {s.historical && <span className="text-violet-400/80">· replay</span>}
                      </div>
                      <SeverityMeter {...(SEVERITY[s.id] ?? { level: 3, label: 'sev 3/5', seg: 'bg-orange-500' })} />
                    </div>
                    <div className="flex items-center gap-2 text-[9px] font-mono text-slate-600">
                      <span title="auto-withdraw timer" className="shrink-0">⏱ {s.defaultDurationSec}s</span>
                      <span className="w-px h-2 bg-slate-800" />
                      <span title="best-path competition" className="shrink-0">{s.bestPathCompetition ? 'best-path race' : 'longest-match'}</span>
                      <span className="w-px h-2 bg-slate-800" />
                      <span className="truncate" title="attacker vantage">AS{s.attackerNode}</span>
                    </div>
                    {active && (
                      <div className="mt-1.5 space-y-1">
                        <div className="flex items-center justify-between gap-2 text-[10px] font-mono">
                          <span className={`flex items-center gap-1.5 ${LIVE_PHASE[activePhase ?? 'injected'].tone}`}>
                            <span className="inline-block w-1.5 h-1.5 rounded-full bg-current animate-pulse" />
                            {LIVE_PHASE[activePhase ?? 'injected'].label}
                          </span>
                          <span className="text-slate-500 tabular-nums shrink-0">
                            t+{activeElapsedSec}s{activeRemainingSec !== null && activeRemainingSec > 0 ? ` · withdraw in ${activeRemainingSec}s` : ''}
                          </span>
                        </div>
                        {/* lifecycle progress: elapsed vs auto-withdraw window */}
                        <div className="h-1 rounded bg-slate-800/80 overflow-hidden" role="progressbar" aria-label="attack elapsed time">
                          {activeRemainingSec !== null ? (
                            <div
                              className={`h-full rounded transition-all duration-700 ${LIVE_PHASE[activePhase ?? 'injected'].bar}`}
                              style={{ width: `${Math.min(100, Math.max(3, (activeElapsedSec / Math.max(activeElapsedSec + activeRemainingSec, 1)) * 100))}%` }}
                            />
                          ) : (
                            <div className="h-full w-full rounded opacity-40 animate-pulse bg-red-900" />
                          )}
                        </div>
                      </div>
                    )}
                  </button>
                </TooltipTrigger>
                <TooltipContent side="left" className="max-w-64 bg-slate-900 border-slate-700 text-slate-300 text-[11px]">
                  <p className="font-semibold text-slate-100 mb-1">{s.name}</p>
                  <p>{s.description}</p>
                  <p className="mt-1 font-mono text-slate-500">auto-withdraw: {s.defaultDurationSec}s · path: {s.injectedPath}</p>
                </TooltipContent>
              </Tooltip>
            );
          })}
        </div>

        {/* Custom attack builder */}
        <div className="rounded-lg border border-slate-700 bg-slate-900/60 p-3">
          <button
            className="flex items-center justify-between w-full"
            onClick={() => setAdvanced((a) => !a)}
            aria-expanded={advanced}
          >
            <div className="flex items-center gap-2">
              <Zap className="h-3.5 w-3.5 text-amber-400" />
              <span className="text-xs font-semibold text-slate-200">Custom Anomaly Builder</span>
            </div>
            <span className="text-[10px] font-mono text-slate-500">{advanced ? 'hide ▲' : 'show ▼'}</span>
          </button>

          {advanced && (
            <div className="mt-3 space-y-2.5">
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <Label className="text-[10px] text-slate-400 font-normal">Target prefix</Label>
                  <Input value={prefix} onChange={(e) => setPrefix(e.target.value)} className="h-7 mt-0.5 font-mono text-xs bg-slate-950 border-slate-700" />
                </div>
                <div>
                  <Label className="text-[10px] text-slate-400 font-normal">Origin AS</Label>
                  <Input value={originAs} onChange={(e) => setOriginAs(e.target.value)} className="h-7 mt-0.5 font-mono text-xs bg-slate-950 border-slate-700" />
                </div>
              </div>
              <div>
                <Label className="text-[10px] text-slate-400 font-normal">AS-Path (space-separated, as seen at defender)</Label>
                <Input value={asPath} onChange={(e) => setAsPath(e.target.value)} className="h-7 mt-0.5 font-mono text-xs bg-slate-950 border-slate-700" />
              </div>
              <div>
                <div className="flex items-center justify-between mb-1">
                  <Label className="text-[10px] text-slate-400 font-normal">Auto-withdraw after</Label>
                  <span className="text-[10px] font-mono text-emerald-300">{duration}s</span>
                </div>
                <Slider value={[duration]} min={15} max={300} step={15} onValueChange={(v) => setDuration(v[0])} />
              </div>
              <div className="flex items-center justify-between">
                <Label className="text-[10px] text-slate-400 font-normal">Flapping burst mode</Label>
                <Switch checked={flapping} onCheckedChange={setFlapping} aria-label="flapping mode" />
              </div>
              {flapping && (
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <Label className="text-[10px] text-slate-400 font-normal">Flap interval</Label>
                    <span className="text-[10px] font-mono text-emerald-300">{flapInterval}s</span>
                  </div>
                  <Slider value={[flapInterval]} min={1} max={20} step={1} onValueChange={(v) => setFlapInterval(v[0])} />
                </div>
              )}
              {customError && (
                <div className="flex items-center gap-1.5 text-[11px] text-red-400 font-mono">
                  <AlertTriangle className="h-3 w-3" /> {customError}
                </div>
              )}
              <Button
                size="sm"
                onClick={submitCustom}
                className="w-full h-8 bg-amber-600 hover:bg-amber-500 text-black font-mono text-xs"
              >
                <History className="h-3 w-3 mr-1 rotate-180" /> Inject Custom Attack
              </Button>
            </div>
          )}
        </div>
      </div>
    </TooltipProvider>
  );
}
