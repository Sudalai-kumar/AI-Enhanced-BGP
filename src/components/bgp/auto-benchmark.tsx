'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { SimState, ATTACK_SCENARIOS, RunResult } from '@/lib/bgp-sim/types';
import { Button } from '@/components/ui/button';
import { Play, Square, CheckCircle2, Loader2, ListChecks } from 'lucide-react';

type SweepStatus = 'idle' | 'running' | 'done' | 'cancelled' | 'error';

interface SweepResult {
  id: string;
  phase: string;
  msr: boolean;
  mttd: number | null;
}

const TERMINAL_TIMEOUT_MS = 150_000; // hard cap per scenario
const SETTLE_GAP_MS = 1500;

/**
 * Auto-benchmark sweep: sequentially injects S1..S6, waits for each run to reach a
 * terminal phase (rolledback | failed) or timeout, then continues to the next scenario.
 * The engine keeps running; results land in state.history (and are persisted separately).
 *
 * State-machine transitions are driven by a single interval callback (external-subscription
 * style) reading the latest engine state via a ref — no setState inside effect bodies.
 */
export function AutoBenchmarkRunner({
  state,
  onInject,
  onWithdraw,
  onStart,
}: {
  state: SimState;
  onInject: (scenarioId: string) => void;
  onWithdraw: () => void;
  onStart: () => void;
}) {
  const [status, setStatus] = useState<SweepStatus>('idle');
  const [currentIdx, setCurrentIdx] = useState(-1);
  const [results, setResults] = useState<SweepResult[]>([]);

  const SEQUENCE = ATTACK_SCENARIOS.filter((s) => s.id !== 'CX');

  // latest-value refs (interval reads these — avoids stale closures & effect setState)
  const stateRef = useRef(state);
  useEffect(() => {
    stateRef.current = state;
  }, [state]);
  const currentIdxRef = useRef(-1);
  const statusRef = useRef<SweepStatus>('idle');
  const resultsRef = useRef<SweepResult[]>([]);
  const waitStartRef = useRef(0);
  const settleTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const historyLenRef = useRef(0);

  const setSweepStatus = useCallback((s: SweepStatus) => {
    statusRef.current = s;
    setStatus(s);
    if (s !== 'running') {
      currentIdxRef.current = -1;
      setCurrentIdx(-1);
    }
  }, []);

  const goTo = useCallback((idx: number) => {
    currentIdxRef.current = idx;
    setCurrentIdx(idx);
    waitStartRef.current = Date.now();
    onInject(SEQUENCE[idx].id);
  }, [SEQUENCE, onInject]);

  /** record a finished run and advance (or finish) the sweep */
  const recordAndAdvance = useCallback(
    (rec: SweepResult, idx: number) => {
      resultsRef.current = [...resultsRef.current, rec];
      setResults(resultsRef.current);
      const next = idx + 1;
      if (next >= SEQUENCE.length) {
        setSweepStatus(rec.phase === 'timeout' ? 'error' : 'done');
        return;
      }
      settleTimerRef.current = setTimeout(() => goTo(next), SETTLE_GAP_MS);
      waitStartRef.current = Date.now() + SETTLE_GAP_MS; // extend timeout during the gap
    },
    [SEQUENCE.length, goTo, setSweepStatus]
  );

  /** one state-machine step, invoked from the interval */
  const step = useCallback(() => {
    const s = stateRef.current;
    const st = statusRef.current;
    if (st !== 'running') return;
    const idx = currentIdxRef.current;
    if (idx < 0 || idx >= SEQUENCE.length) return;
    const expectedId = SEQUENCE[idx].id;

    // keep the clock running during a sweep (guard against concurrent pausing)
    if (!s.running) onStart();

    // engine reset detection: history shrank → the current attack was lost with it
    if (s.history.length < historyLenRef.current) {
      historyLenRef.current = s.history.length;
      goTo(idx); // re-inject the current scenario
      return;
    }
    historyLenRef.current = s.history.length;

    const active = s.activeRun;

    // terminal phase for the current scenario?
    if (active && active.scenarioId === expectedId) {
      if (active.phase === 'rolledback' || active.phase === 'failed') {
        recordAndAdvance({ id: active.scenarioId, phase: active.phase, msr: active.msr, mttd: active.mttd }, idx);
        return;
      }
    } else {
      // active run vanished: completed (archived to history) or lost (external withdraw/reset)
      const archived = s.history.find(
        (r) => r.scenarioId === expectedId && !resultsRef.current.some((x) => x.id === expectedId)
      );
      if (archived) {
        recordAndAdvance({ id: archived.scenarioId, phase: archived.phase, msr: archived.msr, mttd: archived.mttd }, idx);
        return;
      }
      // lost without a trace — re-inject after a short grace period
      if (Date.now() - waitStartRef.current > 8000) {
        goTo(idx);
        return;
      }
    }

    // timeout watchdog
    if (waitStartRef.current && Date.now() - waitStartRef.current > TERMINAL_TIMEOUT_MS) {
      onWithdraw(); // force-clear a stuck attack
      recordAndAdvance({ id: expectedId, phase: 'timeout', msr: false, mttd: null }, idx);
    }
  }, [SEQUENCE, goTo, onWithdraw, onStart, recordAndAdvance]);

  // single driver interval while sweeping
  useEffect(() => {
    if (status !== 'running') return;
    const id = setInterval(step, 600);
    return () => clearInterval(id);
  }, [status, step]);

  useEffect(
    () => () => {
      if (settleTimerRef.current) clearTimeout(settleTimerRef.current);
    },
    []
  );

  const startSweep = () => {
    if (statusRef.current === 'running') return;
    resultsRef.current = [];
    setResults([]);
    historyLenRef.current = stateRef.current.history.length;
    setSweepStatus('running');
    if (!stateRef.current.running) onStart();
    goTo(0);
  };

  const cancelSweep = () => {
    if (settleTimerRef.current) clearTimeout(settleTimerRef.current);
    onWithdraw();
    setSweepStatus('cancelled');
  };

  const completed = results.length;
  const progressPct = status === 'running' ? Math.round((completed / SEQUENCE.length) * 100) : status === 'done' ? 100 : 0;
  const phaseIcon = (phase: string) =>
    phase === 'rolledback' ? '↺' : phase === 'failed' ? '✗' : phase === 'timeout' ? '⏱' : '✓';

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <ListChecks className="h-4 w-4 text-cyan-400" />
          <span className="text-xs font-semibold text-slate-200">Auto-Benchmark Sweep</span>
          <span className="text-[10px] font-mono text-slate-600 hidden sm:inline">S1→S6 sequential · auto-recorded</span>
        </div>
        {status === 'running' ? (
          <Button
            size="sm"
            onClick={cancelSweep}
            className="h-7 font-mono text-[10px] bg-red-900/70 hover:bg-red-800 text-red-100 border border-red-800"
          >
            <Square className="h-3 w-3 mr-1" /> ABORT
          </Button>
        ) : (
          <Button
            size="sm"
            onClick={startSweep}
            className="h-7 font-mono text-[10px] bg-cyan-700 hover:bg-cyan-600 text-black"
          >
            <Play className="h-3 w-3 mr-1" /> RUN SWEEP
          </Button>
        )}
      </div>

      {status !== 'idle' && (
        <>
          {/* progress bar */}
          <div className="h-1.5 rounded-full bg-slate-900 overflow-hidden border border-slate-800/60">
            <div
              className={`h-full transition-all duration-500 ${status === 'done' ? 'bg-emerald-500' : status === 'cancelled' || status === 'error' ? 'bg-red-500' : 'bg-cyan-500'}`}
              style={{ width: `${Math.max(progressPct, status === 'running' ? 4 : 0)}%` }}
            />
          </div>
          <div className="flex items-center gap-2 mt-1.5 flex-wrap">
            <span className="text-[10px] font-mono text-slate-500">
              {status === 'running' && currentIdx >= 0 && `executing ${SEQUENCE[currentIdx]?.id} · phase ${state.activeRun?.phase ?? 'injected'} (${completed}/${SEQUENCE.length})`}
              {status === 'done' && `sweep complete — ${results.filter((r) => r.msr).length}/${results.length} mitigated`}
              {status === 'cancelled' && 'sweep aborted by operator'}
              {status === 'error' && 'sweep ended on timeout'}
            </span>
            {status === 'running' && <Loader2 className="h-3 w-3 animate-spin text-cyan-400" />}
          </div>

          {/* per-scenario chips */}
          <div className="flex flex-wrap gap-1.5 mt-2">
            {SEQUENCE.map((s, i) => {
              const res = results.find((r) => r.id === s.id);
              const isCurrent = status === 'running' && i === currentIdx;
              return (
                <span
                  key={s.id}
                  className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[9.5px] font-mono border transition-colors ${
                    res
                      ? res.msr
                        ? 'border-emerald-800 text-emerald-300 bg-emerald-950/40'
                        : 'border-red-900 text-red-400 bg-red-950/40'
                      : isCurrent
                        ? 'border-cyan-700 text-cyan-300 bg-cyan-950/40 animate-pulse'
                        : 'border-slate-800 text-slate-600 bg-slate-900/40'
                  }`}
                  title={res ? `${res.id}: phase=${res.phase} mttd=${res.mttd ?? '—'}s` : isCurrent ? 'in progress' : 'queued'}
                >
                  {res ? <span>{phaseIcon(res.phase)}</span> : isCurrent ? <Loader2 className="h-3 w-3 animate-spin" /> : null}
                  {s.id}
                  {res?.mttd != null && <span className="opacity-70">{res.mttd}s</span>}
                </span>
              );
            })}
          </div>
        </>
      )}

      {status === 'idle' && (
        <p className="text-[10.5px] font-mono text-slate-500 leading-relaxed">
          Injects all six attack scenarios back-to-back under the current configuration, waiting for each run&apos;s
          full lifecycle (inject → detect → mitigate → rollback) before advancing. Results are aggregated into the
          defense matrix below and persisted to the run archive.
        </p>
      )}
    </div>
  );
}
