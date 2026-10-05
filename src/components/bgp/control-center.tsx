'use client';

import React, { useEffect, useState } from 'react';
import { SimConfig } from '@/lib/bgp-sim/types';
import { Switch } from '@/components/ui/switch';
import { Slider } from '@/components/ui/slider';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { Button } from '@/components/ui/button';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { Info, Save, Trash2, Upload } from 'lucide-react';

interface PresetInfo {
  id: string;
  name: string;
  variant: string | null;
  config: SimConfig;
  updatedAt: string;
}

interface Props {
  config: SimConfig;
  onUpdate: (patch: Record<string, unknown>) => void;
  onPreset: (variant: string) => void;
  onResetConfig: () => void;
  onLoadPreset: (config: SimConfig) => void;
}

const PRESETS = [
  { id: 'A0', name: 'A0 · Standard BGP', desc: 'No detector, no mitigation — RFC 4271 baseline', tone: 'text-slate-400 border-slate-700 hover:border-slate-500' },
  { id: 'A1', name: 'A1 · + Heuristics', desc: 'Rule-based detection, immediate static policy', tone: 'text-amber-400 border-amber-800 hover:border-amber-600' },
  { id: 'A2', name: 'A2 · + ML Only', desc: 'Random Forest → direct class-to-policy mapping', tone: 'text-cyan-300 border-cyan-800 hover:border-cyan-600' },
  { id: 'A3', name: 'A3 · + Trust', desc: 'ML + 6-factor behavioral trust scoring', tone: 'text-teal-300 border-teal-800 hover:border-teal-600' },
  { id: 'A4', name: 'A4 · Full System', desc: 'ML + Trust + Shadow + Rollback (proposed)', tone: 'text-emerald-300 border-emerald-800 hover:border-emerald-500' },
];

function Section({
  title,
  badge,
  hint,
  enabled,
  onToggle,
  children,
}: {
  title: string;
  badge?: string;
  hint: string;
  enabled: boolean;
  onToggle: (v: boolean) => void;
  children: React.ReactNode;
}) {
  return (
    <div className={`rounded-lg border p-3 transition-colors ${enabled ? 'border-slate-700 bg-slate-900/60' : 'border-slate-800 bg-slate-900/30 opacity-75'}`}>
      <div className="flex items-center justify-between gap-2 mb-2">
        <div className="flex items-center gap-1.5 min-w-0">
          <span className="text-xs font-semibold tracking-wide text-slate-200 truncate">{title}</span>
          {badge && <Badge variant="outline" className="text-[9px] px-1 py-0 h-4 border-slate-600 text-slate-400 shrink-0">{badge}</Badge>}
          <Tooltip>
            <TooltipTrigger asChild>
              <button aria-label={`hint: ${title}`} className="text-slate-500 hover:text-slate-300 shrink-0">
                <Info className="h-3 w-3" />
              </button>
            </TooltipTrigger>
            <TooltipContent side="right" className="max-w-56 bg-slate-900 border-slate-700 text-slate-300 text-[11px]">
              {hint}
            </TooltipContent>
          </Tooltip>
        </div>
        <Switch checked={enabled} onCheckedChange={onToggle} aria-label={`toggle ${title}`} />
      </div>
      <div className={`space-y-3 ${enabled ? '' : 'pointer-events-none'}`}>{children}</div>
    </div>
  );
}

function NumSlider({
  label,
  value,
  min,
  max,
  step,
  unit,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  unit?: string;
  onChange: (v: number) => void;
}) {
  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <Label className="text-[11px] text-slate-400 font-normal">{label}</Label>
        <span className="text-[11px] font-mono text-emerald-300">
          {value}
          {unit ?? ''}
        </span>
      </div>
      <Slider value={[value]} min={min} max={max} step={step} onValueChange={(v) => onChange(v[0])} className="py-0.5" aria-label={label} />
    </div>
  );
}

function NumField({
  label,
  value,
  min,
  max,
  onChange,
  width = 'w-20',
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  onChange: (v: number) => void;
  width?: string;
}) {
  return (
    <div className="flex items-center justify-between gap-2">
      <Label className="text-[11px] text-slate-400 font-normal">{label}</Label>
      <Input
        type="number"
        value={value}
        min={min}
        max={max}
        onChange={(e) => {
          const v = parseFloat(e.target.value);
          if (Number.isFinite(v)) onChange(Math.min(max, Math.max(min, v)));
        }}
        className={`h-7 ${width} font-mono text-xs bg-slate-950 border-slate-700 text-emerald-300`}
      />
    </div>
  );
}

export function ControlCenter({ config, onUpdate, onPreset, onResetConfig, onLoadPreset }: Props) {
  const c = config;
  const [presets, setPresets] = useState<PresetInfo[]>([]);
  const [presetName, setPresetName] = useState('');
  const [saving, setSaving] = useState(false);

  const loadPresets = async () => {
    try {
      const res = await fetch('/api/sim-presets');
      const data = await res.json();
      if (Array.isArray(data.presets)) setPresets(data.presets);
    } catch {
      /* offline */
    }
  };

  useEffect(() => {
    loadPresets();
  }, []);

  const savePreset = async () => {
    const name = presetName.trim();
    if (!name || saving) return;
    setSaving(true);
    try {
      await fetch('/api/sim-presets', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, config }),
      });
      setPresetName('');
      await loadPresets();
    } finally {
      setSaving(false);
    }
  };

  const deletePreset = async (id: string) => {
    await fetch(`/api/sim-presets?id=${encodeURIComponent(id)}`, { method: 'DELETE' });
    await loadPresets();
  };

  return (
    <TooltipProvider delayDuration={150}>
      <div className="space-y-3">
        {/* Ablation presets */}
        <div className="rounded-lg border border-slate-700 bg-slate-900/60 p-3">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-semibold tracking-wide text-slate-200">Ablation Presets</span>
            <button onClick={onResetConfig} className="text-[10px] font-mono text-slate-500 hover:text-emerald-300 underline underline-offset-2">
              reset defaults
            </button>
          </div>
          <div className="grid grid-cols-1 gap-1.5">
            {PRESETS.map((p) => (
              <Tooltip key={p.id}>
                <TooltipTrigger asChild>
                  <button
                    onClick={() => onPreset(p.id)}
                    className={`text-left text-[11px] font-mono px-2 py-1.5 rounded border bg-slate-950/60 transition-colors ${p.tone}`}
                  >
                    {p.name}
                  </button>
                </TooltipTrigger>
                <TooltipContent side="right" className="bg-slate-900 border-slate-700 text-slate-300 text-[11px] max-w-56">
                  {p.desc}
                </TooltipContent>
              </Tooltip>
            ))}
          </div>
        </div>

        {/* Saved operator presets (persisted in SQLite) */}
        <div className="rounded-lg border border-slate-700 bg-slate-900/60 p-3">
          <span className="text-xs font-semibold tracking-wide text-slate-200">Operator Presets</span>
          <div className="flex gap-1.5 mt-2">
            <Input
              value={presetName}
              onChange={(e) => setPresetName(e.target.value)}
              placeholder="preset name…"
              className="h-7 flex-1 font-mono text-[11px] bg-slate-950 border-slate-700"
              onKeyDown={(e) => e.key === 'Enter' && savePreset()}
            />
            <Button
              size="sm"
              onClick={savePreset}
              disabled={!presetName.trim() || saving}
              className="h-7 px-2 bg-emerald-700 hover:bg-emerald-600 text-[10px] font-mono"
            >
              <Save className="h-3 w-3" />
            </Button>
          </div>
          {presets.length > 0 && (
            <div className="mt-2 space-y-1">
              {presets.map((p) => (
                <div key={p.id} className="flex items-center gap-1.5">
                  <button
                    onClick={() => onLoadPreset(p.config)}
                    className="flex-1 text-left text-[11px] font-mono px-2 py-1 rounded border border-slate-800 bg-slate-950/60 text-slate-300 hover:border-emerald-700 hover:text-emerald-300 transition-colors truncate"
                    title={`load preset "${p.name}"`}
                  >
                    <Upload className="h-2.5 w-2.5 inline mr-1" />
                    {p.name}
                  </button>
                  <button
                    onClick={() => deletePreset(p.id)}
                    className="p-1 rounded text-slate-600 hover:text-red-400 transition-colors"
                    aria-label={`delete preset ${p.name}`}
                  >
                    <Trash2 className="h-3 w-3" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Global */}
        <div className="rounded-lg border border-slate-700 bg-slate-900/60 p-3 space-y-3">
          <span className="text-xs font-semibold tracking-wide text-slate-200">Global & Clock</span>
          <div className="flex items-center justify-between gap-2">
            <Label className="text-[11px] text-slate-400 font-normal">Defender vantage</Label>
            <Select value={String(c.global.defenderAs)} onValueChange={(v) => onUpdate({ global: { defenderAs: parseInt(v, 10) } })}>
              <SelectTrigger className="h-7 w-44 font-mono text-xs bg-slate-950 border-slate-700">
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="bg-slate-900 border-slate-700">
                <SelectItem value="65003">AS65003 · Edge Defender</SelectItem>
                <SelectItem value="65001">AS65001 · Core Defender</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <NumSlider label="Tick interval (real ms)" value={c.global.tickIntervalMs} min={200} max={3000} step={100} onChange={(v) => onUpdate({ global: { tickIntervalMs: v } })} />
          <NumSlider label="Sim seconds per tick" value={c.global.simSecondsPerTick} min={1} max={30} step={1} onChange={(v) => onUpdate({ global: { simSecondsPerTick: v } })} />
          <div className="flex items-center justify-between">
            <Label className="text-[11px] text-slate-400 font-normal">Telemetry noise / FPR stress</Label>
            <Switch checked={c.global.telemetryNoise} onCheckedChange={(v) => onUpdate({ global: { telemetryNoise: v } })} aria-label="telemetry noise" />
          </div>
          {c.global.telemetryNoise && (
            <NumSlider label="Transient false-alarm rate" value={Math.round(c.global.noiseFpr * 100)} min={0} max={20} step={1} unit="%" onChange={(v) => onUpdate({ global: { noiseFpr: v / 100 } })} />
          )}
        </div>

        {/* Telemetry */}
        <Section
          title="Telemetry Collector"
          badge="async vtysh"
          hint="Asynchronous polling of show bgp ipv4 unicast + sliding-window event aggregation (0.4-0.5s in the live system)."
          enabled={c.telemetry.enabled}
          onToggle={(v) => onUpdate({ telemetry: { enabled: v } })}
        >
          <NumSlider label="Collection jitter (sim s)" value={c.telemetry.jitterSec} min={0} max={2} step={0.1} onChange={(v) => onUpdate({ telemetry: { jitterSec: v } })} />
        </Section>

        {/* ML Detector */}
        <Section
          title="ML Anomaly Detector"
          badge={c.ml.mode === 'ml' ? c.ml.model.replace('_', ' ') : 'rule-based'}
          hint="Calibrated Random Forest (85.06% acc) vs Logistic Regression (79.31%), or deterministic heuristic rules. Sensitivity sharpens evidence scores."
          enabled={c.ml.enabled}
          onToggle={(v) => onUpdate({ ml: { enabled: v } })}
        >
          <div className="flex items-center justify-between gap-2">
            <Label className="text-[11px] text-slate-400 font-normal">Detector mode</Label>
            <Select value={c.ml.mode} onValueChange={(v) => onUpdate({ ml: { mode: v as 'ml' | 'heuristic' } })}>
              <SelectTrigger className="h-7 w-32 font-mono text-xs bg-slate-950 border-slate-700">
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="bg-slate-900 border-slate-700">
                <SelectItem value="ml">ML classifier</SelectItem>
                <SelectItem value="heuristic">Heuristic rules</SelectItem>
              </SelectContent>
            </Select>
          </div>
          {c.ml.mode === 'ml' && (
            <div className="flex items-center justify-between gap-2">
              <Label className="text-[11px] text-slate-400 font-normal">Model</Label>
              <Select value={c.ml.model} onValueChange={(v) => onUpdate({ ml: { model: v as 'random_forest' | 'logistic_regression' } })}>
                <SelectTrigger className="h-7 w-40 font-mono text-xs bg-slate-950 border-slate-700">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="bg-slate-900 border-slate-700">
                  <SelectItem value="random_forest">Random Forest</SelectItem>
                  <SelectItem value="logistic_regression">Logistic Reg.</SelectItem>
                </SelectContent>
              </Select>
            </div>
          )}
          <NumSlider label="Sensitivity" value={c.ml.sensitivity} min={0.5} max={2} step={0.1} unit="×" onChange={(v) => onUpdate({ ml: { sensitivity: v } })} />
        </Section>

        {/* Trust */}
        <Section
          title="Behavioral Trust Engine"
          badge="6-factor"
          hint="Continuous trust score in [0,1] from weighted indicators: origin stability, path plausibility (valley-free + edit distance), flap quiescence, prefix legitimacy, peer diversity, ML confidence."
          enabled={c.trust.enabled}
          onToggle={(v) => onUpdate({ trust: { enabled: v } })}
        >
          {(['origin', 'path', 'flap', 'prefix', 'peer', 'ml'] as const).map((k) => (
            <NumSlider
              key={k}
              label={`weight · ${k}`}
              value={c.trust.weights[k]}
              min={0}
              max={0.5}
              step={0.05}
              onChange={(v) => onUpdate({ trust: { weights: { [k]: v } } })}
            />
          ))}
          <div className="text-[10px] font-mono text-slate-500">
            Σ weights = {(Object.values(c.trust.weights) as number[]).reduce((a, b) => a + b, 0).toFixed(2)}
          </div>
        </Section>

        {/* Shadow */}
        <Section
          title="Shadow Validator"
          badge="anti-thrashing"
          hint="Streak-breaking staging buffer: policy candidates must persist N consecutive ticks and M seconds before promotion. Hijacks can bypass staging for immediate quarantine."
          enabled={c.shadow.enabled}
          onToggle={(v) => onUpdate({ shadow: { enabled: v } })}
        >
          <NumSlider label="Shadow duration" value={c.shadow.shadowDurationSec} min={5} max={90} step={5} unit=" s" onChange={(v) => onUpdate({ shadow: { shadowDurationSec: v } })} />
          <NumSlider label="Required consecutive ticks" value={c.shadow.requiredConsecutiveTicks} min={1} max={10} step={1} onChange={(v) => onUpdate({ shadow: { requiredConsecutiveTicks: v } })} />
          <NumSlider label="Minimum dwell time" value={c.shadow.minDwellSec} min={0} max={120} step={5} unit=" s" onChange={(v) => onUpdate({ shadow: { minDwellSec: v } })} />
          <div className="flex items-center justify-between">
            <Label className="text-[11px] text-slate-400 font-normal">Immediate quarantine (hijack fast-path)</Label>
            <Switch checked={c.shadow.immediateQuarantine} onCheckedChange={(v) => onUpdate({ shadow: { immediateQuarantine: v } })} aria-label="immediate quarantine" />
          </div>
        </Section>

        {/* Policy */}
        <Section
          title="Policy Engine"
          badge="route-maps"
          hint="Trust/class → LocalPref tiers with asymmetric hysteresis. Quarantine = LP 0 + RFC 1997 no-export community (dual action)."
          enabled={c.policy.enabled}
          onToggle={(v) => onUpdate({ policy: { enabled: v } })}
        >
          <div className="grid grid-cols-2 gap-x-3 gap-y-2">
            <NumField label="LP normal" value={c.policy.lpNormal} min={0} max={500} onChange={(v) => onUpdate({ policy: { lpNormal: v } })} width="w-16" />
            <NumField label="LP suspicious" value={c.policy.lpSuspicious} min={0} max={500} onChange={(v) => onUpdate({ policy: { lpSuspicious: v } })} width="w-16" />
            <NumField label="LP leak" value={c.policy.lpLeak} min={0} max={500} onChange={(v) => onUpdate({ policy: { lpLeak: v } })} width="w-16" />
            <NumField label="LP hijack" value={c.policy.lpHijack} min={0} max={500} onChange={(v) => onUpdate({ policy: { lpHijack: v } })} width="w-16" />
          </div>
          <Separator className="bg-slate-800" />
          <div className="grid grid-cols-3 gap-x-3 gap-y-2">
            <NumField label="T normal" value={c.policy.thresholds.normal} min={0.5} max={1} step={undefined as never} onChange={(v) => onUpdate({ policy: { thresholds: { normal: v } } })} width="w-14" />
            <NumField label="T susp" value={c.policy.thresholds.suspicious} min={0.2} max={0.9} onChange={(v) => onUpdate({ policy: { thresholds: { suspicious: v } } })} width="w-14" />
            <NumField label="T leak" value={c.policy.thresholds.leak} min={0} max={0.6} onChange={(v) => onUpdate({ policy: { thresholds: { leak: v } } })} width="w-14" />
          </div>
          <NumSlider label="Hysteresis Δ" value={c.policy.hysteresisDelta} min={0} max={0.2} step={0.01} onChange={(v) => onUpdate({ policy: { hysteresisDelta: v } })} />
          <div className="flex items-center justify-between gap-2">
            <Label className="text-[11px] text-slate-400 font-normal">Quarantine community</Label>
            <Input
              value={c.policy.quarantineCommunity}
              onChange={(e) => onUpdate({ policy: { quarantineCommunity: e.target.value } })}
              className="h-7 w-28 font-mono text-xs bg-slate-950 border-slate-700 text-amber-300"
            />
          </div>
        </Section>

        {/* Rollback */}
        <Section
          title="Rollback Engine"
          badge="multi-criteria"
          hint="Autonomous reversion to LP 100 after M sustained healthy ticks (normal class + trust ≥ threshold + flap quiescence + route active)."
          enabled={c.rollback.enabled}
          onToggle={(v) => onUpdate({ rollback: { enabled: v } })}
        >
          <NumSlider label="Required healthy ticks" value={c.rollback.requiredNormalTicks} min={1} max={10} step={1} onChange={(v) => onUpdate({ rollback: { requiredNormalTicks: v } })} />
        </Section>

        {/* RIB verification */}
        <Section
          title="RIB Verification"
          badge="two-layer"
          hint="Layer 1: route-map config in FRR. Layer 2: best-path LocalPref/community in show bgp RIB. Failed commits are retried."
          enabled={c.ribVerification.enabled}
          onToggle={(v) => onUpdate({ ribVerification: { enabled: v } })}
        >
          <NumSlider label="Commit latency" value={c.ribVerification.latencyTicks} min={1} max={5} step={1} unit=" ticks" onChange={(v) => onUpdate({ ribVerification: { latencyTicks: v } })} />
          <NumSlider label="Verification failure rate" value={Math.round(c.ribVerification.failureRate * 100)} min={0} max={60} step={1} unit="%" onChange={(v) => onUpdate({ ribVerification: { failureRate: v / 100 } })} />
        </Section>

        {/* Comparison */}
        <Section
          title="Comparison Defenses"
          badge="4-way matrix"
          hint="Parallel evaluation of Standard BGP, RPKI ROV (RFC 6811), behavioural heuristics, and the AI control plane."
          enabled={c.comparison.enabled}
          onToggle={(v) => onUpdate({ comparison: { enabled: v } })}
        >
          {(['standardBgp', 'rpki', 'heuristic'] as const).map((k) => (
            <div key={k} className="flex items-center justify-between">
              <Label className="text-[11px] text-slate-400 font-normal">
                {k === 'standardBgp' ? 'Standard BGP (analytical)' : k === 'rpki' ? 'RPKI ROV (emulated)' : 'Heuristics (modelled)'}
              </Label>
              <Switch checked={c.comparison[k]} onCheckedChange={(v) => onUpdate({ comparison: { [k]: v } })} aria-label={k} />
            </div>
          ))}
        </Section>
      </div>
    </TooltipProvider>
  );
}
