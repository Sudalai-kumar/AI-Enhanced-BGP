/**
 * Per-prefix operator watchlist — star prefixes and get alerted (sound + toast +
 * visual flash) whenever their live status changes or their trust score crosses a
 * policy tier boundary. Watched set persists in localStorage across reloads.
 */
'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { RouteStatus, SimState } from './types';

const STORAGE_KEY = 'bgp-noc-watchlist';

/** a transition worth alerting on: status change or tier crossing */
export interface WatchAlert {
  prefix: string;
  t: number; // sim seconds
  kind: 'status' | 'tier';
  from: string;
  to: string;
  trust: number | null;
}

function loadWatched(): string[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter((x) => typeof x === 'string') : [];
  } catch {
    return [];
  }
}

function saveWatched(list: string[]): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(list));
  } catch {
    /* storage unavailable — session-only watchlist */
  }
}

function tierOf(trust: number | null | undefined): string {
  if (trust == null) return 'unscored';
  if (trust >= 0.85) return 'normal';
  if (trust >= 0.55) return 'suspicious';
  if (trust >= 0.25) return 'leak';
  return 'hijack';
}

export interface WatchlistApi {
  watched: string[];
  isWatched: (prefix: string) => boolean;
  toggle: (prefix: string) => void;
  clear: () => void;
  /** transitions of watched prefixes observed this session (newest first, capped) */
  alerts: WatchAlert[];
  /** prefixes currently flashing (recently transitioned — for row/strip glow) */
  flashing: Set<string>;
}

/**
 * Detects transitions on watched prefixes as `state` streams in. The caller wires
 * the side effects (sound + toast) via `onAlert` — fired once per transition.
 */
export function useWatchlist(
  state: SimState | null,
  onAlert?: (alert: WatchAlert) => void,
): WatchlistApi {
  const [watched, setWatched] = useState<string[]>(() => loadWatched());
  const [alerts, setAlerts] = useState<WatchAlert[]>([]);
  const [flashing, setFlashing] = useState<Set<string>>(new Set());

  const watchedRef = useRef(watched);
  useEffect(() => {
    watchedRef.current = watched;
  }, [watched]);

  /** snapshot of each watched prefix's { status, tier } on the previous state */
  const prevSnapshotRef = useRef<Map<string, { status: RouteStatus; tier: string }>>(new Map());
  const onAlertRef = useRef(onAlert);
  useEffect(() => {
    onAlertRef.current = onAlert;
  }, [onAlert]);

  /** flash decay timer */
  const flashTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const toggle = useCallback((prefix: string) => {
    setWatched((prev) => {
      const next = prev.includes(prefix) ? prev.filter((p) => p !== prefix) : [...prev, prefix];
      saveWatched(next);
      return next;
    });
  }, []);

  const clear = useCallback(() => {
    setWatched([]);
    saveWatched([]);
    setAlerts([]);
  }, []);

  const isWatched = useCallback((prefix: string) => watched.includes(prefix), [watched]);

  /** transition scan — runs on every state change */
  const routes = state?.routes;
  const simTime = state?.simTime ?? 0;
  useEffect(() => {
    if (!routes) return;
    const prev = prevSnapshotRef.current;
    const transitions: WatchAlert[] = [];

    for (const prefix of watchedRef.current) {
      const snap = routes[prefix];
      const now = {
        status: snap?.status ?? ('withdrawn' as RouteStatus),
        tier: tierOf(snap?.trust?.score),
      };
      const before = prev.get(prefix);
      if (before && (before.status !== now.status || before.tier !== now.tier)) {
        const kind: WatchAlert['kind'] = before.status !== now.status ? 'status' : 'tier';
        transitions.push({
          prefix,
          t: simTime,
          kind,
          from: kind === 'status' ? before.status : before.tier,
          to: kind === 'status' ? now.status : now.tier,
          trust: snap?.trust?.score ?? null,
        });
      }
      prev.set(prefix, now);
    }
    // prune snapshots for prefixes that are no longer watched
    for (const key of prev.keys()) {
      if (!watchedRef.current.includes(key)) prev.delete(key);
    }

    if (transitions.length > 0) {
      // apply the transition side effects out of the synchronous effect body
      // (react-compiler lint) — a 0ms deferral fires long before the next tick
      setTimeout(() => {
        setAlerts((list) => [...transitions.slice().reverse(), ...list].slice(0, 40));
        setFlashing((prevSet) => {
          const next = new Set(prevSet);
          for (const tr of transitions) next.add(tr.prefix);
          return next;
        });
        for (const tr of transitions) onAlertRef.current?.(tr);
        // decay the flash after 4.5s
        if (flashTimerRef.current) clearTimeout(flashTimerRef.current);
        flashTimerRef.current = setTimeout(() => setFlashing(new Set()), 4500);
      }, 0);
    }
  }, [routes, simTime]);

  // housekeeping: clear the flash timer on unmount
  useEffect(
    () => () => {
      if (flashTimerRef.current) clearTimeout(flashTimerRef.current);
    },
    [],
  );

  return useMemo(
    () => ({ watched, isWatched, toggle, clear, alerts, flashing }),
    [watched, isWatched, toggle, clear, alerts, flashing],
  );
}
