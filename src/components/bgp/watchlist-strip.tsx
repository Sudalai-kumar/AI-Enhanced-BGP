'use client';

import React from 'react';
import { SimState } from '@/lib/bgp-sim/types';
import { WatchAlert, WatchlistApi } from '@/lib/bgp-sim/watchlist';
import { Star, Eye, Trash2, Activity } from 'lucide-react';

/** status → dot + label tone for the compact strip rows */
const STATUS_TONE: Record<string, { dot: string; text: string }> = {
  normal: { dot: 'bg-emerald-400', text: 'text-emerald-300' },
  suspicious: { dot: 'bg-amber-400', text: 'text-amber-300' },
  leak: { dot: 'bg-orange-400', text: 'text-orange-300' },
  hijack: { dot: 'bg-red-500', text: 'text-red-300' },
  recovering: { dot: 'bg-cyan-400', text: 'text-cyan-300' },
  withdrawn: { dot: 'bg-slate-600', text: 'text-slate-500' },
};

function trustTone(t: number): string {
  if (t >= 0.85) return 'text-emerald-300';
  if (t >= 0.55) return 'text-amber-300';
  if (t >= 0.25) return 'text-orange-300';
  return 'text-red-400';
}

/** compact toast of the latest transition (shown when one just happened) */
function LatestAlert({ alert }: { alert: WatchAlert }) {
  const hostile = alert.to === 'hijack' || alert.to === 'leak' || alert.to === 'suspicious';
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border text-[9.5px] font-mono leading-relaxed ${
        hostile
          ? 'border-amber-600/80 bg-amber-950/50 text-amber-200'
          : 'border-emerald-800/80 bg-emerald-950/50 text-emerald-300'
      }`}
      title={`t=${alert.t}s · trust ${alert.trust != null ? alert.trust.toFixed(2) : '—'}`}
    >
      <Activity className="h-2.5 w-2.5" />
      <span className="text-slate-400">{alert.prefix}</span>
      <span>{alert.from}</span>→<span className={hostile ? 'font-semibold' : ''}>{alert.to}</span>
      {alert.trust != null && <span className={trustTone(alert.trust)}>τ {alert.trust.toFixed(2)}</span>}
    </span>
  );
}

/**
 * Operator watchlist strip — pinned prefixes with live status, trust and a
 * one-glance alert ticker. Collapses to nothing when the list is empty.
 */
export function WatchlistStrip({
  state,
  watchlist,
  onFocusPrefix,
}: {
  state: SimState;
  watchlist: WatchlistApi;
  onFocusPrefix: (prefix: string) => void;
}) {
  const { watched, alerts, flashing } = watchlist;
  if (watched.length === 0) return null;

  const latest = alerts[0] ?? null;

  return (
    <div
      className={`rounded-lg border p-2 transition-colors ${
        flashing.size > 0
          ? 'border-amber-600/70 bg-amber-950/25 watch-glow'
          : 'border-violet-900/60 bg-violet-950/20'
      }`}
      role="region"
      aria-label="prefix watchlist"
    >
      <div className="flex items-center gap-2 mb-1.5 flex-wrap">
        <Star className={`h-3.5 w-3.5 ${flashing.size > 0 ? 'text-amber-300' : 'text-violet-300 star-shimmer'} ${flashing.size > 0 ? 'animate-pulse' : ''}`} />
        <span className="text-[10px] font-semibold tracking-widest text-slate-300 uppercase">watchlist</span>
        <span className="text-[9px] font-mono text-slate-500">
          {watched.length} watched · sound + flash on status/tier change
        </span>
        {latest && <span className="ml-auto"><LatestAlert alert={latest} /></span>}
        <button
          onClick={watchlist.clear}
          className={`px-1.5 py-0.5 rounded border border-slate-800 text-[8.5px] font-mono uppercase text-slate-500 hover:text-red-300 hover:border-red-800/60 transition-colors ${latest ? '' : 'ml-auto'}`}
          title="unwatch every prefix"
          aria-label="clear watchlist"
        >
          <Trash2 className="h-2.5 w-2.5 inline mr-0.5 -mt-px" /> clear
        </button>
      </div>

      <div className="flex items-stretch gap-1.5 flex-wrap">
        {watched.map((prefix) => {
          const snap = state.routes[prefix];
          const status = snap?.status ?? 'withdrawn';
          const tone = STATUS_TONE[status] ?? STATUS_TONE.normal;
          const trust = snap?.trust?.score ?? null;
          const isFlashing = flashing.has(prefix);
          const quarantined = snap?.underOverride && snap?.route.locPref === 0;
          return (
            <button
              key={prefix}
              onClick={() => onFocusPrefix(prefix)}
              title={`drill into ${prefix} — status ${status}${trust != null ? ` · τ ${trust.toFixed(2)}` : ''}${
                quarantined ? ' · QUARANTINED' : ''
              }`}
              className={`group flex items-center gap-1.5 px-2 py-1 rounded-md border font-mono text-[10px] transition-all ${
                isFlashing
                  ? 'border-amber-500/80 bg-amber-950/40 status-flash'
                  : 'border-slate-800 bg-slate-950/60 hover:border-violet-700/60 hover:bg-violet-950/30'
              }`}
            >
              <span className={`w-1.5 h-1.5 rounded-full ${tone.dot} ${status !== 'normal' ? 'animate-pulse' : ''}`} />
              <span className="text-slate-200">{prefix}</span>
              {trust != null && <span className={trustTone(trust)}>τ{trust.toFixed(2)}</span>}
              {quarantined && (
                <span className="px-1 rounded bg-red-950/60 border border-red-800/70 text-red-300 text-[8px] uppercase">quar</span>
              )}
              <Eye className="h-2.5 w-2.5 text-slate-600 group-hover:text-violet-300 transition-colors" />
            </button>
          );
        })}
      </div>
    </div>
  );
}
