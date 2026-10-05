'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { SimState, RunResult, SimEvent, TrustPoint } from '@/lib/bgp-sim/types';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Clock,
  Play,
  Pause,
  SkipBack,
  SkipForward,
  Radio,
  Rewind,
  History,
} from 'lucide-react';

/* ------------------------------------------------------------------ */
/* helpers                                                             */
/* ------------------------------------------------------------------ */

const LEVEL_COLOR: Record<SimEvent['level'], string> = {
  danger: 'bg-red-500',
  warn: 'bg-amber-400',
  success: 'bg-cyan-400',
  info: 'bg-slate-500',
};

const PHASE_SEG: Record<string, { color: string; label: string }> = {
  injected: { color: 'bg-red-600/80', label: 'injected' },
  detected: { color: 'bg-amber-500/80', label: 'detected' },
  mitigated: { color: 'bg-cyan-500/80', label: 'mitigated' },
  rolledback: { color: 'bg-emerald-500/70', label: 'rolled back' },
};

/** Effective end of a run band (last known lifecycle timestamp). */
function runEndT(r: RunResult, simTime: number): number {
  return r.rolledBackAt ?? r.mitigatedAt ?? r.detectedAt ?? Math.min(r.injectedAt + 120, simTime);
}

/** Reconstructed run phase at arbitrary time T (pure function of timestamps). */
function phaseAtT(r: RunResult, T: number): string | null {
  if (T < r.injectedAt) return null;
  if (r.rolledBackAt != null && T >= r.rolledBackAt) return 'rolledback';
  if (r.mitigatedAt != null && T >= r.mitigatedAt) return 'mitigated';
  if (r.detectedAt != null && T >= r.detectedAt) return 'detected';
  return 'injected';
}

function trustTone(v: number): string {
  if (v >= 0.85) return 'bg-emerald-500';
  if (v >= 0.55) return 'bg-amber-400';
  if (v >= 0.25) return 'bg-orange-500';
  return 'bg-red-500';
}

/* ------------------------------------------------------------------ */
/* component                                                           */
/* ------------------------------------------------------------------ */

const SPEEDS = [5, 15, 40, 100];

export function TimeTravelScrubber({ state, initialT = null }: { state: SimState; initialT?: number | null }) {
  const { events, history, activeRun, ribLog, trustHistory, simTime } = state;

  const [scrubT, setScrubT] = useState<number>(initialT ?? simTime);
  const [following, setFollowing] = useState(initialT == null);
  const [playing, setPlaying] = useState(false);
  const [speedIdx, setSpeedIdx] = useState(1);
  const timelineRef = useRef<HTMLDivElement>(null);

  const speed = SPEEDS[speedIdx];

  // derived effective cursor: following tracks the live clock; manual/replay uses scrubT
  const T = following ? simTime : Math.min(scrubT, simTime);

  // latest-value refs so the replay interval can read current values (no setState-in-effect)
  const simTimeRef = useRef(simTime);
  const cursorRef = useRef(T);
  useEffect(() => {
    simTimeRef.current = simTime;
    cursorRef.current = T;
  });

  // replay loop — advance the cursor inside the interval callback
  useEffect(() => {
    if (!playing) return;
    const id = window.setInterval(() => {
      const cap = simTimeRef.current;
      const next = cursorRef.current + speed / 5; // interval 200ms -> speed sim-s per real-s
      if (next >= cap) {
        setScrubT(cap);
        setPlaying(false); // replay reached the live edge
      } else {
        setScrubT(next);
      }
    }, 200);
    return () => window.clearInterval(id);
  }, [playing, speed]);

  const takeControl = useCallback((t: number) => {
    setFollowing(false);
    setPlaying(false);
    setScrubT(t);
  }, []);

  const allRuns = useMemo(
    () => [...history, ...(activeRun ? [activeRun] : [])].slice(-14),
    [history, activeRun]
  );

  const sortedEvents = useMemo(() => [...events].sort((a, b) => a.t - b.t), [events]);

  // bucket-sample markers so the timeline stays renderable at any event volume
  const markers = useMemo(() => {
    if (sortedEvents.length <= 130) return sortedEvents;
    const step = Math.ceil(sortedEvents.length / 130);
    return sortedEvents.filter((_, i) => i % step === 0 || i === sortedEvents.length - 1);
  }, [sortedEvents]);

  // events visible at T (newest first)
  const eventsAtT = useMemo(() => {
    const before = sortedEvents.filter((e) => e.t <= T);
    return before.slice(-40).reverse();
  }, [sortedEvents, T]);

  const ribAtT = useMemo(() => ribLog.filter((e) => e.t <= T), [ribLog, T]);

  // per-prefix trust reconstruction at T
  const trustAtT = useMemo(() => {
    const byPrefix = new Map<string, TrustPoint>();
    for (const p of trustHistory) {
      if (p.t <= T) {
        const cur = byPrefix.get(p.prefix);
        if (!cur || p.t >= cur.t) byPrefix.set(p.prefix, p);
      }
    }
    return Array.from(byPrefix.values()).sort((a, b) => a.trust - b.trust);
  }, [trustHistory, T]);

  const activeRunsAtT = useMemo(
    () => allRuns.filter((r) => phaseAtT(r, T) !== null),
    [allRuns, T]
  );

  const nextEvent = sortedEvents.find((e) => e.t > T);
  const prevEvent = [...sortedEvents].reverse().find((e) => e.t < T);

  const pct = simTime > 0 ? (T / simTime) * 100 : 0;

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950/60 top-accent">
      {/* header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-slate-800 bg-slate-900/50 rounded-t-lg flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <History className="h-4 w-4 text-violet-400" />
          <span className="text-xs font-semibold text-slate-200">Time-Travel Event Scrubber</span>
          <Badge variant="outline" className="text-[9px] h-4 px-1.5 border-violet-800 text-violet-300 bg-violet-950/40">
            replay any t
          </Badge>
        </div>
        <div className="flex items-center gap-1.5">
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              setFollowing(true);
              setPlaying(false);
            }}
            className={`h-6 px-2 text-[10px] font-mono ${
              following
                ? 'border-emerald-700 text-emerald-300 bg-emerald-950/40'
                : 'border-slate-700 text-slate-400 hover:bg-slate-800'
            }`}
            aria-pressed={following}
            title="Follow the live simulation clock"
          >
            <Radio className="h-3 w-3 mr-1" /> LIVE
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              if (playing) {
                setPlaying(false);
              } else {
                setFollowing(false);
                if (T >= simTime) setScrubT(0);
                setPlaying(true);
              }
            }}
            className="h-6 px-2 text-[10px] font-mono border-violet-800 text-violet-300 bg-violet-950/40 hover:bg-violet-900/40"
            aria-pressed={playing}
            title="Replay the timeline from the scrub position"
          >
            {playing ? <Pause className="h-3 w-3" /> : <Play className="h-3 w-3" />}
            {playing ? 'pause' : 'replay'}
          </Button>
          <div className="flex rounded-md border border-slate-800 overflow-hidden" role="group" aria-label="replay speed">
            {SPEEDS.map((s, i) => (
              <button
                key={s}
                onClick={() => setSpeedIdx(i)}
                className={`px-1.5 py-1 text-[9px] font-mono transition-colors ${
                  i === speedIdx ? 'bg-violet-900/60 text-violet-200' : 'bg-slate-900 text-slate-500 hover:bg-slate-800'
                }`}
                aria-pressed={i === speedIdx}
              >
                {s}×
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="p-3 space-y-3">
        {/* timeline track */}
        <div
          ref={timelineRef}
          className="relative h-24 rounded-md border border-slate-800 bg-slate-900/40 overflow-hidden cursor-crosshair"
          role="img"
          aria-label={`timeline of ${sortedEvents.length} events and ${allRuns.length} runs`}
          onClick={(e) => {
            const rect = e.currentTarget.getBoundingClientRect();
            const ratio = (e.clientX - rect.left) / rect.width;
            takeControl(Math.max(0, Math.min(1, ratio)) * simTime);
          }}
        >
          {/* grid ticks every 25% */}
          {[25, 50, 75].map((g) => (
            <div key={g} className="absolute top-0 bottom-0 w-px bg-slate-800/60" style={{ left: `${g}%` }} />
          ))}

          {/* run lifecycle bands (top lane) */}
          <div className="absolute top-2 left-0 right-0 h-9 space-y-1">
            {allRuns.slice(-4).map((r) => {
              const start = (r.injectedAt / simTime) * 100;
              const end = (runEndT(r, simTime) / simTime) * 100;
              if (!isFinite(start) || end <= start) return null;
              return (
                <div
                  key={r.runId}
                  className="absolute h-2.5 rounded-full overflow-hidden flex border border-slate-800/80"
                  style={{ left: `${start}%`, width: `${Math.max(end - start, 0.5)}%` }}
                  title={`${r.scenarioId} · ${r.scenarioName} · injected t=${r.injectedAt}s`}
                >
                  {/* phase segments */}
                  {(['detected', 'mitigated', 'rolledback'] as const).map((seg) => {
                    const segStartTs =
                      seg === 'detected' ? r.detectedAt : seg === 'mitigated' ? r.mitigatedAt : r.rolledBackAt;
                    if (segStartTs == null) return null;
                    const relStart = ((segStartTs - r.injectedAt) / (runEndT(r, simTime) - r.injectedAt)) * 100;
                    return (
                      <div
                        key={seg}
                        className={`absolute top-0 bottom-0 ${PHASE_SEG[seg].color}`}
                        style={{ left: `${relStart}%`, right: 0 }}
                      />
                    );
                  })}
                  <div className={`flex-1 ${PHASE_SEG.injected.color}`} />
                  <span className="absolute inset-0 flex items-center px-1 text-[8px] font-mono text-slate-100/90 pointer-events-none whitespace-nowrap">
                    {r.scenarioId}
                  </span>
                </div>
              );
            })}
          </div>

          {/* event markers (bottom lane) */}
          <div className="absolute bottom-2 left-0 right-0 h-3">
            {markers.map((e) => {
              const left = (e.t / simTime) * 100;
              if (!isFinite(left)) return null;
              return (
                <button
                  key={e.id}
                  onClick={(ev) => {
                    ev.stopPropagation();
                    takeControl(e.t);
                  }}
                  className={`absolute w-1.5 h-1.5 -translate-x-1/2 rounded-sm ${LEVEL_COLOR[e.level]} hover:scale-150 transition-transform`}
                  style={{ left: `${left}%`, top: '50%', marginTop: -3 }}
                  title={`t=${e.t}s [${e.source}] ${e.message.slice(0, 80)}`}
                  aria-label={`jump to t=${e.t} seconds: ${e.message.slice(0, 60)}`}
                />
              );
            })}
          </div>

          {/* scrub cursor */}
          <div
            className={`absolute top-0 bottom-0 w-0.5 bg-violet-400 pointer-events-none ${following ? '' : 'scrub-ping'}`}
            style={{ left: `${pct}%` }}
          >
            <div className="absolute -top-0.5 -left-1 w-2.5 h-2.5 rounded-full bg-violet-400 shadow-[0_0_8px_rgba(167,139,250,0.8)]" />
          </div>

          {/* axis labels */}
          <span className="absolute bottom-0.5 left-1 text-[8px] font-mono text-slate-600 pointer-events-none">t=0s</span>
          <span className="absolute bottom-0.5 right-1 text-[8px] font-mono text-slate-600 pointer-events-none">
            t={simTime.toFixed(0)}s
          </span>
        </div>

        {/* slider + step buttons */}
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="ghost"
            disabled={!prevEvent}
            onClick={() => prevEvent && takeControl(prevEvent.t)}
            className="h-7 w-7 p-0 border border-slate-800 text-slate-400"
            title="previous event"
            aria-label="previous event"
          >
            <SkipBack className="h-3.5 w-3.5" />
          </Button>
          <input
            type="range"
            min={0}
            max={Math.max(simTime, 1)}
            step={Math.max(1, Math.round(simTime / 400))}
            value={T}
            onChange={(e) => takeControl(Number(e.target.value))}
            onMouseDown={() => setFollowing(false)}
            onTouchStart={() => setFollowing(false)}
            className="scrub-range flex-1"
            aria-label="scrub to simulation time"
          />
          <Button
            size="sm"
            variant="ghost"
            disabled={!nextEvent}
            onClick={() => nextEvent && takeControl(nextEvent.t)}
            className="h-7 w-7 p-0 border border-slate-800 text-slate-400"
            title="next event"
            aria-label="next event"
          >
            <SkipForward className="h-3.5 w-3.5" />
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => takeControl(0)}
            className="h-7 w-7 p-0 border border-slate-800 text-slate-400"
            title="rewind to start"
            aria-label="rewind to start"
          >
            <Rewind className="h-3.5 w-3.5" />
          </Button>
        </div>

        {/* readout strip */}
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] font-mono text-slate-500">
          <span className="flex items-center gap-1 text-violet-300">
            <Clock className="h-3 w-3" /> T = {T.toFixed(0)}s
          </span>
          <span>
            Δ live = {(simTime - T).toFixed(0)}s
          </span>
          <span>
            {eventsAtT.length}/{sortedEvents.length} events ≤ T
          </span>
          <span>{ribAtT.length} RIB commits ≤ T</span>
          {activeRunsAtT.length > 0 ? (
            <span className="flex items-center gap-1 flex-wrap">
              {activeRunsAtT.map((r) => {
                const ph = phaseAtT(r, T);
                return (
                  <Badge
                    key={r.runId}
                    variant="outline"
                    className={`h-4 px-1.5 text-[9px] ${
                      ph === 'injected'
                        ? 'border-red-800 text-red-300 bg-red-950/40'
                        : ph === 'detected'
                          ? 'border-amber-800 text-amber-300 bg-amber-950/40'
                          : ph === 'mitigated'
                            ? 'border-cyan-800 text-cyan-300 bg-cyan-950/40'
                            : 'border-emerald-800 text-emerald-300 bg-emerald-950/40'
                    }`}
                  >
                    {r.scenarioId} {PHASE_SEG[ph ?? 'injected'].label}
                  </Badge>
                );
              })}
            </span>
          ) : (
            <span className="text-slate-600">no run active at T · baseline</span>
          )}
        </div>

        {/* state reconstruction row */}
        <div className="grid grid-cols-1 lg:grid-cols-[240px_1fr] gap-3">
          {/* trust at T */}
          <div className="rounded-md border border-slate-800 bg-slate-900/40 p-2.5">
            <div className="text-[10px] font-mono text-slate-500 mb-2 uppercase tracking-wider">Trust τ at T</div>
            {trustAtT.length === 0 ? (
              <p className="text-[10px] font-mono text-slate-600">no telemetry recorded before T</p>
            ) : (
              <div className="space-y-1.5 max-h-36 overflow-y-auto scrollbar-thin pr-1">
                {trustAtT.map((p) => (
                  <div key={p.prefix} className="flex items-center gap-2">
                    <span className="text-[9.5px] font-mono text-slate-400 w-28 truncate" title={p.prefix}>
                      {p.prefix}
                    </span>
                    <div className="flex-1 h-2 rounded-full bg-slate-800 overflow-hidden">
                      <div
                        className={`h-full rounded-full ${trustTone(p.trust)} transition-all duration-300`}
                        style={{ width: `${Math.round(p.trust * 100)}%` }}
                      />
                    </div>
                    <span className="text-[9.5px] font-mono tabular-nums text-slate-300 w-8 text-right">
                      {p.trust.toFixed(2)}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* events ≤ T */}
          <div className="rounded-md border border-slate-800 bg-slate-900/40 p-2.5">
            <div className="text-[10px] font-mono text-slate-500 mb-2 uppercase tracking-wider">
              Event stream ≤ T · newest first
            </div>
            {eventsAtT.length === 0 ? (
              <p className="text-[10px] font-mono text-slate-600">nothing recorded yet at this point in time</p>
            ) : (
              <div className="max-h-36 overflow-y-auto scrollbar-thin pr-1 space-y-1">
                {eventsAtT.map((e) => (
                  <button
                    key={e.id}
                    onClick={() => takeControl(e.t)}
                    className="w-full text-left flex items-baseline gap-2 rounded px-1.5 py-1 hover:bg-slate-800/60 transition-colors group"
                    title="jump to this event"
                  >
                    <span className="text-[9px] font-mono text-slate-600 tabular-nums w-10 shrink-0">{e.t}s</span>
                    <span
                      className={`text-[8px] font-mono uppercase w-14 shrink-0 ${
                        e.level === 'danger'
                          ? 'text-red-400'
                          : e.level === 'warn'
                            ? 'text-amber-400'
                            : e.level === 'success'
                              ? 'text-cyan-400'
                              : 'text-slate-500'
                      }`}
                    >
                      {e.source}
                    </span>
                    <span className="text-[10px] font-mono text-slate-400 group-hover:text-slate-300 truncate">
                      {e.message}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
