'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { ATTACK_SCENARIOS, CLASS_NAMES, RunResult, SimConfig, SimState } from '@/lib/bgp-sim/types';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  FlaskConical,
  Play,
  Square,
  Loader2,
  ArrowRight,
  ShieldCheck,
  ShieldX,
  Eye,
  EyeOff,
  Timer,
  RotateCcw,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Gauge,
} from 'lucide-react';

export type LabPhase =
  | 'idle'
  | 'arm-a'
  | 'run-a'
  | 'arm-b'
  | 'run-b'
  | 'restore'
  | 'done'
  | 'cancelled'
  | 'error';

export interface ArmResult {
  variant: string;
  variantLabel: string;
  scenarioId: string;
  run: RunResult | null;
  timedOut: boolean;
}

/** experiment speed — fast modes inject shorter attacks so arms complete sooner */
export type LabSpeed = 'paper' | 'fast' | 'turbo';

export const LAB_SPEEDS: { id: LabSpeed; label: string; hint: string; duration: number | null; timeoutMs: number }[] = [
  { id: 'paper', label: '1×', hint: 'paper-faithful · full scenario duration (120-150s sim)', duration: null, timeoutMs: 150_000 },
  { id: 'fast', label: '2×', hint: 'fast · 60s injection — safe for every scenario incl. S4 MTTM 20s', duration: 60, timeoutMs: 90_000 },
  { id: 'turbo', label: '4×', hint: 'turbo · 45s injection — quickest full-lifecycle comparison', duration: 45, timeoutMs: 70_000 },
];

export interface AblationExperiment {
  phase: LabPhase;
  resultA: ArmResult | null;
  resultB: ArmResult | null;
  activeArm: 'a' | 'b' | null;
  speed: LabSpeed;
  start: (variantA: string, variantB: string, scenarioId: string, speed?: LabSpeed) => void;
  cancel: () => void;
}

const VARIANTS: { id: string; label: string; blurb: string }[] = [
  { id: 'A0', label: 'A0 · Standard BGP', blurb: 'no detector · no mitigation' },
  { id: 'A1', label: 'A1 · + Heuristics', blurb: 'rule-based static policy' },
  { id: 'A2', label: 'A2 · + ML Only', blurb: 'RF classes → policy' },
  { id: 'A3', label: 'A3 · + Trust', blurb: 'ML + 6-factor τ score' },
  { id: 'A4', label: 'A4 · Full System', blurb: '+ shadow + rollback' },
];

const PHASE_LABEL: Record<LabPhase, string> = {
  idle: 'ready',
  'arm-a': 'arming variant A',
  'run-a': 'executing variant A',
  'arm-b': 'arming variant B',
  'run-b': 'executing variant B',
  restore: 'restoring operator config',
  done: 'experiment complete',
  cancelled: 'aborted by operator',
  error: 'ended on timeout',
};

const SETTLE_MS = 2_500;

/**
 * Ablation experiment state machine — MUST live above the Tabs boundary
 * (page level) so it survives tab switches while running. Runs the SAME
 * scenario under two ablation variants back-to-back; snapshots and restores
 * the operator's original configuration.
 *
 * All transitions run from a single interval reading latest state via refs —
 * no setState inside effect bodies.
 */
export function useAblationExperiment({
  state,
  onApplyPreset,
  onUpdateConfig,
  onInject,
  onWithdraw,
  onStart,
}: {
  state: SimState | null;
  onApplyPreset: (variant: string) => void;
  onUpdateConfig: (config: SimConfig) => void;
  onInject: (scenarioId: string, durationSec?: number) => void;
  onWithdraw: () => void;
  onStart: () => void;
}): AblationExperiment {
  const [phase, setPhase] = useState<LabPhase>('idle');
  const [resultA, setResultA] = useState<ArmResult | null>(null);
  const [resultB, setResultB] = useState<ArmResult | null>(null);
  const [activeArm, setActiveArm] = useState<'a' | 'b' | null>(null);
  const [speed, setSpeed] = useState<LabSpeed>('paper');

  const stateRef = useRef(state);
  useEffect(() => {
    stateRef.current = state;
  }, [state]);
  const phaseRef = useRef<LabPhase>('idle');
  const armRef = useRef<'a' | 'b' | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const armStartRef = useRef(0);
  const savedConfigRef = useRef<SimConfig | null>(null);
  const savedLabelRef = useRef('');
  const baselineKeysRef = useRef<Set<string>>(new Set());
  const historyLenRef = useRef(0);
  const selRef = useRef({ variantA: 'A0', variantB: 'A4', scenarioId: 'S2' });
  const speedRef = useRef<LabSpeed>('paper');

  const setLabPhase = useCallback((p: LabPhase, arm: 'a' | 'b' | null = null) => {
    phaseRef.current = p;
    armRef.current = arm;
    setPhase(p);
    setActiveArm(arm);
  }, []);

  const runKey = (r: RunResult) => `${r.runId}:${r.injectedAt}`;

  const armVariant = useCallback(
    (which: 'a' | 'b') => {
      const { variantA: va, variantB: vb, scenarioId: sid } = selRef.current;
      const spd = LAB_SPEEDS.find((s) => s.id === speedRef.current) ?? LAB_SPEEDS[0];
      const v = which === 'a' ? va : vb;
      baselineKeysRef.current = new Set((stateRef.current?.history ?? []).map(runKey));
      historyLenRef.current = stateRef.current?.history.length ?? 0;
      armStartRef.current = Date.now();
      onApplyPreset(v);
      if (stateRef.current && !stateRef.current.running) onStart();
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => {
        // fast modes inject a shorter attack so the arm lands sooner
        onInject(sid, spd.duration ?? undefined);
        setLabPhase(which === 'a' ? 'run-a' : 'run-b', which);
      }, SETTLE_MS);
      setLabPhase(which === 'a' ? 'arm-a' : 'arm-b', which);
    },
    [onApplyPreset, onInject, onStart, setLabPhase]
  );

  const armTimeoutMs = useCallback(
    () => (LAB_SPEEDS.find((s) => s.id === speedRef.current) ?? LAB_SPEEDS[0]).timeoutMs,
    []
  );

  const finishExperiment = useCallback(
    (outcome: 'done' | 'cancelled' | 'error') => {
      if (timerRef.current) clearTimeout(timerRef.current);
      const saved = savedConfigRef.current;
      const savedLabel = savedLabelRef.current;
      // preset labels ("A4 preset", "A4 · Full System" initial default) restore exactly via applyPreset
      const presetMatch = savedLabel.match(/^A([0-4])(?:\s+preset|\s+·)/);
      if (presetMatch) {
        onApplyPreset(`A${presetMatch[1]}`);
      } else if (saved) {
        onUpdateConfig(saved);
      }
      setLabPhase(outcome, null);
    },
    [onApplyPreset, onUpdateConfig, setLabPhase]
  );

  /** one state-machine step, invoked from the interval */
  const step = useCallback(() => {
    const p = phaseRef.current;
    if (p !== 'run-a' && p !== 'run-b') return;
    const s = stateRef.current;
    if (!s) return;
    const which: 'a' | 'b' = p === 'run-a' ? 'a' : 'b';
    const { variantA: va, variantB: vb } = selRef.current;
    const armRes = (run: RunResult | null, timedOut: boolean): ArmResult => ({
      variant: which === 'a' ? va : vb,
      variantLabel: VARIANTS.find((v) => v.id === (which === 'a' ? va : vb))?.label ?? (which === 'a' ? va : vb),
      scenarioId: selRef.current.scenarioId,
      run,
      timedOut,
    });

    if (!s.running) onStart();

    // engine reset detection: history shrank → in-flight run lost → re-arm
    if (s.history.length < historyLenRef.current) {
      historyLenRef.current = s.history.length;
      armVariant(which);
      return;
    }

    // has a NEW run for our scenario landed in history?
    const landed = s.history.find(
      (r) => r.scenarioId === selRef.current.scenarioId && !baselineKeysRef.current.has(runKey(r))
    );
    if (landed) {
      if (which === 'a') {
        setResultA(armRes(landed, false));
        if (timerRef.current) clearTimeout(timerRef.current);
        timerRef.current = setTimeout(() => armVariant('b'), 1500);
        setLabPhase('arm-b', 'b');
      } else {
        setResultB(armRes(landed, false));
        finishExperiment('done');
      }
      return;
    }

    // active run vanished without landing — re-inject after grace
    if (!s.activeRun && Date.now() - armStartRef.current > 20_000 && s.history.length === historyLenRef.current) {
      armVariant(which);
      return;
    }

    // timeout watchdog (scaled by experiment speed)
    if (Date.now() - armStartRef.current > armTimeoutMs()) {
      onWithdraw();
      if (which === 'a') {
        setResultA(armRes(null, true));
        if (timerRef.current) clearTimeout(timerRef.current);
        timerRef.current = setTimeout(() => armVariant('b'), 2000);
        setLabPhase('arm-b', 'b');
      } else {
        setResultB(armRes(null, true));
        finishExperiment('error');
      }
    }
  }, [armVariant, finishExperiment, onWithdraw, onStart, setLabPhase]);

  // single driver interval — lives at page level, survives tab switches
  useEffect(() => {
    if (!['arm-a', 'run-a', 'arm-b', 'run-b'].includes(phase)) return;
    const id = setInterval(step, 600);
    return () => clearInterval(id);
  }, [phase, step]);

  useEffect(
    () => () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    },
    []
  );

  const start = useCallback(
    (variantA: string, variantB: string, scenarioId: string, spd: LabSpeed = 'paper') => {
      if (['arm-a', 'run-a', 'arm-b', 'run-b'].includes(phaseRef.current)) return;
      if (variantA === variantB) return;
      selRef.current = { variantA, variantB, scenarioId };
      speedRef.current = spd;
      setSpeed(spd);
      const s = stateRef.current;
      savedConfigRef.current = s ? s.config : null;
      savedLabelRef.current = s?.variantLabel ?? 'A4 · Full System';
      setResultA(null);
      setResultB(null);
      armVariant('a');
    },
    [armVariant]
  );

  const cancel = useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    onWithdraw();
    finishExperiment('cancelled');
  }, [onWithdraw, finishExperiment]);

  return { phase, resultA, resultB, activeArm, speed, start, cancel };
}

/** terminal-phase tone for result cards */
function outcomeTone(run: RunResult | null, timedOut: boolean) {
  if (timedOut) return { text: 'timeout', cls: 'border-yellow-800 text-yellow-300 bg-yellow-950/40', icon: AlertTriangle };
  if (!run) return { text: 'no data', cls: 'border-slate-700 text-slate-400 bg-slate-900', icon: XCircle };
  if (run.phase === 'rolledback') return { text: 'rolled back', cls: 'border-emerald-800 text-emerald-300 bg-emerald-950/40', icon: RotateCcw };
  if (run.phase === 'mitigated') return { text: 'mitigated', cls: 'border-emerald-800 text-emerald-300 bg-emerald-950/40', icon: CheckCircle2 };
  if (run.phase === 'failed') return { text: run.detectedAt === null ? 'undetected' : 'failed', cls: 'border-red-900 text-red-400 bg-red-950/40', icon: ShieldX };
  return { text: run.phase, cls: 'border-slate-700 text-slate-400 bg-slate-900', icon: XCircle };
}

/**
 * Ablation A/B laboratory VIEW — pure presentation over the page-level
 * experiment state machine (useAblationExperiment). Local state holds only
 * the uncommitted selector picks.
 */
export function AblationLab({
  state,
  experiment,
}: {
  state: SimState;
  experiment: AblationExperiment;
}) {
  const { phase, resultA, resultB, speed } = experiment;
  // uncommitted selections (kept local so tab switches don't disturb an idle setup)
  const [variantA, setVariantA] = useState('A0');
  const [variantB, setVariantB] = useState('A4');
  const [scenarioId, setScenarioId] = useState('S2');
  const [speedSel, setSpeedSel] = useState<LabSpeed>('paper');
  const activeSpeed = LAB_SPEEDS.find((s) => s.id === speed) ?? LAB_SPEEDS[0];

  const SCENARIOS = ATTACK_SCENARIOS.filter((s) => s.id !== 'CX');
  const running = ['arm-a', 'run-a', 'arm-b', 'run-b'].includes(phase);
  const progressPct =
    phase === 'done' ? 100 : phase === 'run-b' || phase === 'arm-b' ? 55 : phase === 'run-a' || phase === 'arm-a' ? 20 : 0;

  // ---------- comparison derivation ----------
  const a = resultA;
  const b = resultB;
  const detectedA = a?.run?.detectedAt !== null && a?.run?.detectedAt !== undefined;
  const detectedB = b?.run?.detectedAt !== null && b?.run?.detectedAt !== undefined;
  const msrA = a?.run?.msr ?? false;
  const msrB = b?.run?.msr ?? false;
  const winner =
    a && b
      ? msrA !== msrB
        ? msrA
          ? 'a'
          : 'b'
        : detectedA !== detectedB
          ? detectedA
            ? 'a'
            : 'b'
          : a.run?.mttd != null && b.run?.mttd != null
            ? a.run.mttd <= b.run.mttd
              ? 'a'
              : 'b'
            : null
      : null;

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3">
      {/* header */}
      <div className="flex items-center justify-between mb-2 gap-2 flex-wrap">
        <div className="flex items-center gap-2">
          <FlaskConical className="h-4 w-4 text-violet-400" />
          <span className="text-xs font-semibold text-slate-200">Ablation A/B Laboratory</span>
          <span className="text-[10px] font-mono text-slate-600 hidden sm:inline">same scenario · two variants · side-by-side</span>
        </div>
        <div className="flex items-center gap-1.5">
          {/* speed selector — fast modes shorten the injected attack */}
          <div className="flex items-center rounded border border-slate-800 bg-slate-900/60 p-0.5" role="radiogroup" aria-label="experiment speed">
            {LAB_SPEEDS.map((s) => {
              const active = (running ? speed : speedSel) === s.id;
              return (
                <button
                  key={s.id}
                  role="radio"
                  aria-checked={active}
                  disabled={running}
                  onClick={() => setSpeedSel(s.id)}
                  title={s.hint}
                  className={`px-1.5 py-0.5 rounded text-[9.5px] font-mono transition-colors disabled:opacity-50 ${
                    active ? 'bg-cyan-900/60 text-cyan-200 border border-cyan-800' : 'text-slate-500 hover:text-slate-300 border border-transparent'
                  }`}
                >
                  {s.label}
                </button>
              );
            })}
          </div>
          {running ? (
            <Button
              size="sm"
              onClick={experiment.cancel}
              className="h-7 font-mono text-[10px] bg-red-900/70 hover:bg-red-800 text-red-100 border border-red-800"
            >
              <Square className="h-3 w-3 mr-1" /> ABORT
            </Button>
          ) : (
            <Button
              size="sm"
              onClick={() => experiment.start(variantA, variantB, scenarioId, speedSel)}
              disabled={variantA === variantB}
              title={variantA === variantB ? 'pick two different variants' : 'run the controlled experiment'}
              className="h-7 font-mono text-[10px] bg-violet-700 hover:bg-violet-600 text-white disabled:opacity-40"
            >
              <Play className="h-3 w-3 mr-1" /> RUN EXPERIMENT
            </Button>
          )}
        </div>
      </div>

      {/* speed hint strip */}
      <div className="flex items-center gap-2 mb-2 text-[9.5px] font-mono text-slate-500 flex-wrap">
        <Gauge className="h-3 w-3 text-cyan-400" />
        <span>
          speed <span className="text-cyan-300">{activeSpeed.label}</span> — {activeSpeed.hint}
        </span>
        {activeSpeed.duration !== null && (
          <span className="text-slate-600">· injection duration {activeSpeed.duration}s (paper: 120-150s)</span>
        )}
      </div>

      {/* setup row */}
      <div className="grid grid-cols-1 md:grid-cols-[1fr_auto_1fr_auto] gap-2 items-stretch mb-2">
        <div className="rounded border border-slate-800 bg-slate-900/40 p-2">
          <div className="text-[9px] font-mono uppercase tracking-wider text-slate-500 mb-1.5">variant A (control)</div>
          <div className="flex flex-wrap gap-1">
            {VARIANTS.map((v) => (
              <button
                key={v.id}
                onClick={() => !running && setVariantA(v.id)}
                disabled={running}
                aria-pressed={variantA === v.id}
                title={v.blurb}
                className={`px-2 py-0.5 rounded border text-[9.5px] font-mono transition-colors ${
                  variantA === v.id
                    ? 'border-amber-600 text-amber-200 bg-amber-950/50'
                    : 'border-slate-800 text-slate-500 hover:border-slate-600 hover:text-slate-300 disabled:opacity-50'
                }`}
              >
                {v.id}
              </button>
            ))}
          </div>
          <div className="mt-1 text-[9px] font-mono text-slate-600 truncate">{VARIANTS.find((v) => v.id === variantA)?.blurb}</div>
        </div>
        <div className="hidden md:flex items-center justify-center px-1">
          <ArrowRight className={`h-4 w-4 ${running ? 'text-violet-400 animate-pulse' : 'text-slate-700'}`} />
        </div>
        <div className="rounded border border-slate-800 bg-slate-900/40 p-2">
          <div className="text-[9px] font-mono uppercase tracking-wider text-slate-500 mb-1.5">variant B (treatment)</div>
          <div className="flex flex-wrap gap-1">
            {VARIANTS.map((v) => (
              <button
                key={v.id}
                onClick={() => !running && setVariantB(v.id)}
                disabled={running}
                aria-pressed={variantB === v.id}
                title={v.blurb}
                className={`px-2 py-0.5 rounded border text-[9.5px] font-mono transition-colors ${
                  variantB === v.id
                    ? 'border-violet-600 text-violet-200 bg-violet-950/50'
                    : 'border-slate-800 text-slate-500 hover:border-slate-600 hover:text-slate-300 disabled:opacity-50'
                }`}
              >
                {v.id}
              </button>
            ))}
          </div>
          <div className="mt-1 text-[9px] font-mono text-slate-600 truncate">{VARIANTS.find((v) => v.id === variantB)?.blurb}</div>
        </div>
        <div className="rounded border border-slate-800 bg-slate-900/40 p-2 md:w-40">
          <div className="text-[9px] font-mono uppercase tracking-wider text-slate-500 mb-1.5">scenario</div>
          <div className="flex flex-wrap gap-1">
            {SCENARIOS.map((s) => (
              <button
                key={s.id}
                onClick={() => !running && setScenarioId(s.id)}
                disabled={running}
                aria-pressed={scenarioId === s.id}
                className={`px-1.5 py-0.5 rounded border text-[9.5px] font-mono transition-colors ${
                  scenarioId === s.id
                    ? 'border-red-700 text-red-300 bg-red-950/50'
                    : 'border-slate-800 text-slate-500 hover:border-slate-600 hover:text-slate-300 disabled:opacity-50'
                }`}
                title={s.name}
              >
                {s.id}
              </button>
            ))}
          </div>
          <div className="mt-1 text-[9px] font-mono text-slate-600 truncate">{SCENARIOS.find((s) => s.id === scenarioId)?.shortName}</div>
        </div>
      </div>

      {/* progress + status */}
      {phase !== 'idle' && (
        <div className="mb-2">
          <div className="h-1.5 rounded-full bg-slate-900 overflow-hidden border border-slate-800/60 flex">
            <div
              className={`h-full transition-all duration-500 ${phase === 'done' ? 'bg-emerald-500' : 'bg-amber-500/80'}`}
              style={{ width: `${Math.min(progressPct, 50)}%` }}
            />
            <div
              className={`h-full transition-all duration-500 ${phase === 'done' ? 'bg-emerald-500' : phase.includes('b') ? 'bg-violet-500' : 'bg-slate-700/40'}`}
              style={{ width: `${Math.max(progressPct - 50, 0)}%` }}
            />
          </div>
          <div className="flex items-center gap-2 mt-1.5 flex-wrap text-[10px] font-mono">
            <span
              className={
                phase === 'done'
                  ? 'text-emerald-400'
                  : phase === 'cancelled' || phase === 'error'
                    ? 'text-red-400'
                    : 'text-violet-300'
              }
            >
              {PHASE_LABEL[phase]}
            </span>
            {running && <Loader2 className="h-3 w-3 animate-spin text-violet-400" />}
            {running && state.activeRun && (
              <span className="text-slate-500">
                · {state.activeRun.scenarioId} {state.activeRun.phase}
                {state.activeRun.mttd !== null && ` · MTTD ${state.activeRun.mttd}s`}
              </span>
            )}
          </div>
        </div>
      )}

      {phase === 'idle' && (
        <p className="text-[10.5px] font-mono text-slate-500 leading-relaxed">
          Controlled ablation experiment from the paper: injects the chosen scenario once under variant A and once under
          variant B (your current configuration is snapshotted and restored afterwards), then compares detection,
          MTTD/MTTM, mitigation success and policy response side-by-side.
        </p>
      )}

      {/* side-by-side results */}
      {a && b && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-2 mt-1">
          {[a, b].map((res, idx) => {
            const isWinner = winner === (idx === 0 ? 'a' : 'b');
            const oc = outcomeTone(res.run, res.timedOut);
            const detected = res.run?.detectedAt !== null && res.run?.detectedAt !== undefined;
            const OcIcon = oc.icon;
            return (
              <div
                key={res.variant}
                className={`rounded-lg border p-3 space-y-2 transition-all ${
                  isWinner
                    ? 'border-emerald-700/80 bg-emerald-950/20 shadow-[0_0_16px_-6px_rgba(52,211,153,0.5)]'
                    : 'border-slate-800 bg-slate-900/40'
                }`}
              >
                <div className="flex items-center gap-2 flex-wrap">
                  <span className={`text-[11px] font-mono font-bold ${idx === 0 ? 'text-amber-300' : 'text-violet-300'}`}>
                    {res.variant}
                  </span>
                  <span className="text-[10px] font-mono text-slate-500">{res.variantLabel.replace(`${res.variant} · `, '')}</span>
                  <Badge variant="outline" className={`ml-auto text-[9px] h-4.5 px-1.5 ${oc.cls}`}>
                    <OcIcon className="h-2.5 w-2.5 mr-0.5" /> {oc.text}
                  </Badge>
                  {isWinner && (
                    <Badge variant="outline" className="text-[9px] h-4.5 px-1.5 border-emerald-700 text-emerald-300 bg-emerald-950/50">
                      <span className="mr-0.5">★</span> wins
                    </Badge>
                  )}
                </div>

                <div className="grid grid-cols-2 gap-1.5">
                  <div className={`rounded border p-1.5 ${detected ? 'border-emerald-900/60 bg-emerald-950/20' : 'border-red-900/60 bg-red-950/20'}`}>
                    <div className="flex items-center gap-1 text-[8.5px] font-mono uppercase tracking-wider text-slate-500">
                      {detected ? <Eye className="h-2.5 w-2.5 text-emerald-400" /> : <EyeOff className="h-2.5 w-2.5 text-red-400" />}
                      detection
                    </div>
                    <div className={`mt-0.5 text-[11px] font-mono font-semibold ${detected ? 'text-emerald-300' : 'text-red-400'}`}>
                      {detected
                        ? `${res.run!.mttd !== null ? `${res.run!.mttd}s` : '—'} · ${res.run!.detectedClass !== null ? CLASS_NAMES[res.run!.detectedClass] : '—'}`
                        : 'never detected'}
                    </div>
                  </div>
                  <div className={`rounded border p-1.5 ${res.run?.msr ? 'border-emerald-900/60 bg-emerald-950/20' : 'border-red-900/60 bg-red-950/20'}`}>
                    <div className="flex items-center gap-1 text-[8.5px] font-mono uppercase tracking-wider text-slate-500">
                      {res.run?.msr ? <ShieldCheck className="h-2.5 w-2.5 text-emerald-400" /> : <ShieldX className="h-2.5 w-2.5 text-red-400" />}
                      mitigation
                    </div>
                    <div className={`mt-0.5 text-[11px] font-mono font-semibold ${res.run?.msr ? 'text-emerald-300' : 'text-red-400'}`}>
                      {res.run?.msr
                        ? `MSR ✓ · MTTM ${res.run!.mttm !== null ? `${res.run!.mttm}s` : '—'}`
                        : res.timedOut
                          ? 'timed out'
                          : 'not mitigated'}
                    </div>
                  </div>
                </div>

                <div className="flex flex-wrap gap-x-3 gap-y-1 text-[9.5px] font-mono text-slate-500">
                  <span>
                    policy <span className="text-orange-300">{res.run?.appliedPolicy || 'none (no override)'}</span>
                  </span>
                  <span>
                    RIB <span className={res.run?.ribVerified ? 'text-emerald-300' : 'text-slate-400'}>{res.run?.ribVerified ? 'verified ✓' : '—'}</span>
                  </span>
                  <span>
                    dwell{' '}
                    <span className="text-slate-300 tabular-nums">
                      {res.run?.mitigatedAt != null && res.run?.injectedAt != null
                        ? `${res.run.mitigatedAt - res.run.injectedAt}s`
                        : res.timedOut
                          ? '>150s'
                          : '—'}
                    </span>
                  </span>
                  <span className="ml-auto text-slate-600 tabular-nums">
                    run #{res.run?.runId ?? '—'} · t={res.run?.injectedAt ?? '—'}s
                  </span>
                </div>
              </div>
            );
          })}

          {/* verdict strip */}
          <div className="lg:col-span-2 rounded border border-violet-900/50 bg-violet-950/20 px-3 py-2 flex items-center gap-2 flex-wrap">
            <Timer className="h-3.5 w-3.5 text-violet-300 shrink-0" />
            <span className="text-[10.5px] font-mono text-slate-300">
              {detectedA !== detectedB ? (
                <>
                  <span className={detectedA ? 'text-emerald-300' : 'text-red-300'}>{a?.variant}</span>{' '}
                  {detectedA ? 'detected the anomaly' : 'never detected it'} while{' '}
                  <span className={detectedB ? 'text-emerald-300' : 'text-red-300'}>{b?.variant}</span>{' '}
                  {detectedB ? 'detected it' : 'never detected it'}
                  {detectedA && a?.run?.mttd != null ? ` — time-to-detect ${a.run.mttd}s vs ${b?.run?.mttd ?? '∞'}` : ''}
                  {detectedB && !detectedA && b?.run?.mttd != null ? ` — time-to-detect ${b.run.mttd}s vs ∞` : ''}.
                </>
              ) : detectedA && detectedB ? (
                <>
                  both variants detected the anomaly
                  {a?.run?.mttd != null && b?.run?.mttd != null
                    ? ` — ${Math.min(a.run.mttd, b.run.mttd) === a.run.mttd ? a.variant : b.variant} reacted faster (${Math.min(a.run.mttd, b.run.mttd)}s vs ${Math.max(a.run.mttd, b.run.mttd)}s)`
                    : ''}
                  {msrA !== msrB ? `, but only ${msrA ? a?.variant : b?.variant} completed a verified mitigation` : ' with equivalent mitigation'}.
                </>
              ) : (
                <>neither variant detected the anomaly under this scenario — detector coverage gap.</>
              )}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
