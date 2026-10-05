'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { FEATURE_NAMES, RouteSnapshot, SimState, TrustPoint } from '@/lib/bgp-sim/types';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import {
  AlertTriangle, ArrowDownWideNarrow, ChevronDown, ChevronRight, Crosshair, ListFilter,
  Search, ShieldAlert, ShieldCheck, Star, TrendingDown, X,
} from 'lucide-react';
import { TrustSparkline } from './trust-sparkline';

const STATUS_STYLE: Record<string, { badge: string; dot: string; label: string; chip: string }> = {
  normal: {
    badge: 'border-emerald-800 bg-emerald-950/60 text-emerald-300', dot: 'bg-emerald-400', label: 'NORMAL',
    chip: 'border-emerald-800/70 text-emerald-300 bg-emerald-950/40',
  },
  suspicious: {
    badge: 'border-amber-800 bg-amber-950/60 text-amber-300', dot: 'bg-amber-400', label: 'SUSPICIOUS',
    chip: 'border-amber-800/70 text-amber-300 bg-amber-950/40',
  },
  leak: {
    badge: 'border-orange-800 bg-orange-950/60 text-orange-300', dot: 'bg-orange-400', label: 'ROUTE LEAK',
    chip: 'border-orange-800/70 text-orange-300 bg-orange-950/40',
  },
  hijack: {
    badge: 'border-red-800 bg-red-950/60 text-red-300', dot: 'bg-red-500', label: 'HIJACK',
    chip: 'border-red-800/70 text-red-300 bg-red-950/40',
  },
  recovering: {
    badge: 'border-cyan-800 bg-cyan-950/60 text-cyan-300', dot: 'bg-cyan-400', label: 'RECOVERING',
    chip: 'border-cyan-800/70 text-cyan-300 bg-cyan-950/40',
  },
  withdrawn: {
    badge: 'border-slate-700 bg-slate-900 text-slate-400', dot: 'bg-slate-600', label: 'WITHDRAWN',
    chip: 'border-slate-700/70 text-slate-400 bg-slate-900/40',
  },
};

/** severity rank for default "worst-first" ordering */
const SEVERITY_RANK: Record<string, number> = { hijack: 0, leak: 1, suspicious: 2, recovering: 3, normal: 4, withdrawn: 5 };

type SortMode = 'prefix' | 'severity' | 'trust-asc' | 'trust-desc';

/** page-level keyboard command routed into the route table ('/' focuses the search box) */
export type RouteCmd = { type: 'focus-search'; nonce: number } | null;

/** module-level: remembers the last consumed command nonce across remounts
 *  (Radix Tabs unmounts inactive content — without this, returning to the Control
 *  Room tab would replay the last '/' command and steal focus back to the search box) */
let lastConsumedCmdNonce = 0;

function trustColor(t: number): string {
  if (t >= 0.85) return 'bg-emerald-500';
  if (t >= 0.55) return 'bg-amber-500';
  if (t >= 0.25) return 'bg-orange-500';
  return 'bg-red-500';
}

function trustText(t: number): string {
  if (t >= 0.85) return 'text-emerald-300';
  if (t >= 0.55) return 'text-amber-300';
  if (t >= 0.25) return 'text-orange-300';
  return 'text-red-400';
}

/** status-colored left edge for route cards — terminal-log feel */
const EDGE_COLOR: Record<string, string> = {
  normal: 'bg-emerald-500/70',
  suspicious: 'bg-amber-500/80',
  leak: 'bg-orange-500/80',
  hijack: 'bg-red-500/90',
  recovering: 'bg-cyan-400/80',
  withdrawn: 'bg-slate-600/80',
};

/** highlight the search match inside a plain string */
function Highlight({ text, query }: { text: string; query: string }) {
  const q = query.trim().toLowerCase();
  if (!q) return <>{text}</>;
  const idx = text.toLowerCase().indexOf(q);
  if (idx === -1) return <>{text}</>;
  return (
    <>
      {text.slice(0, idx)}
      <mark className="bg-amber-500/25 text-amber-200 rounded-sm px-0.5">{text.slice(idx, idx + q.length)}</mark>
      {text.slice(idx + q.length)}
    </>
  );
}

function FeatureRow({ name, value }: { name: string; value: number }) {
  const norm = Math.min(1, Math.max(0, value / 25));
  return (
    <div className="flex items-center gap-2">
      <span className="w-40 shrink-0 text-[10px] font-mono text-slate-500 truncate">{name}</span>
      <div className="flex-1 h-1.5 rounded bg-slate-800 overflow-hidden">
        <div
          className={`h-full rounded transition-all ${norm > 0.6 ? 'bg-red-500/80' : norm > 0.35 ? 'bg-amber-500/80' : 'bg-emerald-500/70'}`}
          style={{ width: `${Math.max(3, norm * 100)}%` }}
        />
      </div>
      <span className="w-12 shrink-0 text-right text-[10px] font-mono text-slate-300">{value}</span>
    </div>
  );
}

export function RouteTable({
  state,
  onFocusPrefix,
  cmd,
  anomalousOnly,
  onToggleAnomalous,
  watchlist,
}: {
  state: SimState;
  onFocusPrefix?: (prefix: string) => void;
  cmd?: RouteCmd;
  anomalousOnly?: boolean;
  onToggleAnomalous?: () => void;
  watchlist?: { isWatched: (prefix: string) => boolean; toggle: (prefix: string) => void; flashing: Set<string> };
}) {
  const [expanded, setExpanded] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<Set<string>>(new Set());
  const [sortMode, setSortMode] = useState<SortMode>('prefix');
  const searchRef = useRef<HTMLInputElement>(null);
  const anomalous = anomalousOnly ?? false;

  /** keyboard command from the page ('/' focuses search after a cross-tab jump) */
  useEffect(() => {
    if (!cmd || cmd.nonce === lastConsumedCmdNonce) return;
    lastConsumedCmdNonce = cmd.nonce;
    if (cmd.type === 'focus-search') {
      searchRef.current?.focus();
      searchRef.current?.select();
    }
  }, [cmd]);

  const allRoutes = useMemo(() => Object.values(state.routes), [state.routes]);

  /** status counts for the filter chips (pre-text-filter, so counts stay stable) */
  const statusCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const r of allRoutes) counts[r.status] = (counts[r.status] ?? 0) + 1;
    return counts;
  }, [allRoutes]);

  const visibleRoutes = useMemo(() => {
    let list = allRoutes;
    const q = query.trim().toLowerCase();
    if (q) {
      list = list.filter(
        (r) =>
          r.route.prefix.toLowerCase().includes(q) ||
          r.route.asPath.toLowerCase().includes(q) ||
          String(r.route.originAs).includes(q),
      );
    }
    if (statusFilter.size > 0) list = list.filter((r) => statusFilter.has(r.status));
    if (anomalous) list = list.filter((r) => r.status !== 'normal' || r.underOverride);
    const sorted = [...list];
    switch (sortMode) {
      case 'severity':
        sorted.sort((a, b) => (SEVERITY_RANK[a.status] ?? 9) - (SEVERITY_RANK[b.status] ?? 9));
        break;
      case 'trust-asc':
        sorted.sort((a, b) => (a.trust?.score ?? 2) - (b.trust?.score ?? 2));
        break;
      case 'trust-desc':
        sorted.sort((a, b) => (b.trust?.score ?? 2) - (a.trust?.score ?? 2));
        break;
      default:
        sorted.sort((a, b) => a.route.prefix.localeCompare(b.route.prefix));
    }
    return sorted;
  }, [allRoutes, query, statusFilter, anomalous, sortMode]);

  const filtering = query.trim() !== '' || statusFilter.size > 0 || anomalous;

  const toggleStatus = (status: string) => {
    setStatusFilter((prev) => {
      const next = new Set(prev);
      if (next.has(status)) next.delete(status);
      else next.add(status);
      return next;
    });
  };

  const clearFilters = () => {
    setQuery('');
    setStatusFilter(new Set());
    if (anomalous) onToggleAnomalous?.();
  };

  return (
    <TooltipProvider delayDuration={100}>
      <div className="space-y-2">
        {/* ── live filter / sort bar ─────────────────────────────── */}
        <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-2 flex items-center gap-2 flex-wrap">
          <div className="relative flex-1 min-w-40 sm:max-w-64">
            <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-600 pointer-events-none" />
            <Input
              ref={searchRef}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Escape') {
                  e.stopPropagation();
                  if (query) setQuery('');
                  else searchRef.current?.blur();
                }
              }}
              placeholder="filter prefix · AS path · origin…"
              aria-label="filter routes"
              className="h-7 pl-7 pr-7 text-[11px] font-mono bg-slate-950 border-slate-800 placeholder:text-slate-600 focus-visible:ring-1 focus-visible:ring-emerald-600"
            />
            {query && (
              <button
                onClick={() => setQuery('')}
                aria-label="clear search"
                className="absolute right-1.5 top-1/2 -translate-y-1/2 text-slate-600 hover:text-slate-300"
              >
                <X className="h-3 w-3" />
              </button>
            )}
          </div>

          <span className="flex items-center gap-1 flex-wrap" role="group" aria-label="status filter">
            {(['hijack', 'leak', 'suspicious', 'normal', 'recovering'] as const).map((status) => {
              const on = statusFilter.has(status);
              const count = statusCounts[status] ?? 0;
              const st = STATUS_STYLE[status];
              return (
                <button
                  key={status}
                  onClick={() => toggleStatus(status)}
                  aria-pressed={on}
                  className={`px-1.5 py-0.5 rounded-full border text-[8.5px] font-mono uppercase transition-colors leading-relaxed ${
                    on ? st.chip : 'border-slate-800 text-slate-600 hover:text-slate-400 hover:border-slate-700'
                  }`}
                  title={on ? `hide ${STATUS_STYLE[status]?.label ?? status} routes` : `show only ${STATUS_STYLE[status]?.label ?? status} routes (multi-select)`}
                >
                  {status} {count > 0 && <span className="tabular-nums opacity-70">{count}</span>}
                </button>
              );
            })}
          </span>

          <button
            onClick={() => onToggleAnomalous?.()}
            aria-pressed={anomalous}
            className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full border text-[8.5px] font-mono uppercase transition-colors leading-relaxed ${
              anomalous
                ? 'border-amber-700 text-amber-300 bg-amber-950/50'
                : 'border-slate-800 text-slate-600 hover:text-amber-400/80 hover:border-amber-800/50'
            }`}
            title="only routes with a non-normal status or active policy override (F)"
          >
            <AlertTriangle className="h-2.5 w-2.5" /> anomalous
          </button>

          <Select value={sortMode} onValueChange={(v: SortMode) => setSortMode(v)}>
            <SelectTrigger
              className="h-7 w-[132px] text-[10px] font-mono bg-slate-950 border-slate-800 text-slate-300 px-2 focus-visible:ring-1 focus-visible:ring-emerald-600"
              aria-label="sort routes"
            >
              <ArrowDownWideNarrow className="h-3 w-3 mr-1 text-slate-600" />
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="bg-slate-900 border-slate-800">
              <SelectItem value="prefix" className="text-[11px] font-mono">prefix A→Z</SelectItem>
              <SelectItem value="severity" className="text-[11px] font-mono">worst severity first</SelectItem>
              <SelectItem value="trust-asc" className="text-[11px] font-mono">τ lowest first</SelectItem>
              <SelectItem value="trust-desc" className="text-[11px] font-mono">τ highest first</SelectItem>
            </SelectContent>
          </Select>

          <span className="text-[9.5px] font-mono text-slate-500 tabular-nums flex items-center gap-1" aria-live="polite">
            <ListFilter className="h-3 w-3 text-slate-600" />
            {visibleRoutes.length}/{allRoutes.length}
          </span>

          {filtering && (
            <button
              onClick={clearFilters}
              className="px-1.5 py-0.5 rounded-full border border-slate-800 text-[8.5px] font-mono text-slate-400 hover:text-slate-200 hover:border-slate-600 leading-relaxed"
              title="clear all route filters (search · status · anomalous)"
            >
              clear
            </button>
          )}
        </div>

        {allRoutes.length > 0 && visibleRoutes.length === 0 && (
          <div className="rounded-lg border border-dashed border-slate-800 bg-slate-950/40 p-4 text-center">
            <p className="text-[11px] font-mono text-slate-500">no routes match the current filters</p>
            <button onClick={clearFilters} className="mt-1 text-[11px] font-mono text-emerald-400 hover:text-emerald-300 underline underline-offset-2">
              reset filters
            </button>
          </div>
        )}

        {visibleRoutes.map((r: RouteSnapshot) => {
          const st = STATUS_STYLE[r.status] ?? STATUS_STYLE.normal;
          const trust = r.trust?.score;
          const isOpen = expanded === r.route.prefix;
          const quarantined = r.underOverride && r.route.locPref === 0;
          const starred = watchlist?.isWatched(r.route.prefix) ?? false;
          return (
            <RouteRow
              key={r.route.prefix}
              r={r}
              st={st}
              trust={trust}
              isOpen={isOpen}
              quarantined={quarantined}
              starred={starred}
              flashing={watchlist?.flashing.has(r.route.prefix) ?? false}
              onToggle={() => setExpanded(isOpen ? null : r.route.prefix)}
              onToggleWatch={watchlist ? () => watchlist.toggle(r.route.prefix) : undefined}
              rollbackTicks={state.config.rollback.requiredNormalTicks}
              simTime={state.simTime}
              trustHistory={state.trustHistory.filter((p) => p.prefix === r.route.prefix)}
              thresholds={state.config.policy.thresholds}
              onFocus={onFocusPrefix ? () => onFocusPrefix(r.route.prefix) : undefined}
              query={query}
            />
          );
        })}
      </div>
    </TooltipProvider>
  );
}

/** route card wrapper that flashes when its status changes (keyed overlay, no effect-state) */
function RouteRow({
  r,
  st,
  trust,
  isOpen,
  quarantined,
  starred,
  flashing,
  onToggle,
  onToggleWatch,
  rollbackTicks,
  simTime,
  trustHistory,
  thresholds,
  onFocus,
  query = '',
}: {
  r: RouteSnapshot;
  st: { badge: string; dot: string; label: string };
  trust: number | undefined;
  isOpen: boolean;
  quarantined: boolean;
  starred: boolean;
  flashing: boolean;
  onToggle: () => void;
  onToggleWatch?: () => void;
  rollbackTicks: number;
  simTime: number;
  trustHistory: TrustPoint[];
  thresholds: { normal: number; suspicious: number; leak: number };
  onFocus?: () => void;
  query?: string;
}) {
  const flashKey = `${r.status}:${r.route.locPref}`;
  const hostile = r.status === 'hijack' || r.status === 'leak';
  return (
            <div
              className={`group relative rounded-lg border transition-all ${
                quarantined
                  ? 'border-red-800/70 bg-red-950/20'
                  : r.underOverride
                    ? 'border-amber-800/60 bg-amber-950/10'
                    : 'border-slate-800 bg-slate-950/50'
              } ${flashing ? 'border-amber-500/80 shadow-[0_0_14px_rgba(245,158,11,0.22)]' : ''} ${starred ? 'ring-1 ring-violet-800/50' : ''}`}
            >
              <div key={flashKey} className="pointer-events-none absolute inset-0 rounded-lg status-flash" aria-hidden />
              <span
                aria-hidden
                className={`absolute left-0 top-2 bottom-2 w-[2.5px] rounded-full ${EDGE_COLOR[r.status] ?? 'bg-slate-700'}`}
              />
              <div className="flex items-stretch">
                <button
                  className="flex-1 min-w-0 text-left p-3"
                  onClick={onToggle}
                  aria-expanded={isOpen}
                  aria-label={`${r.route.prefix} — expand diagnostics`}
                >
                <div className="flex items-center gap-2 flex-wrap">
                  {isOpen ? <ChevronDown className="h-3.5 w-3.5 text-slate-500" /> : <ChevronRight className="h-3.5 w-3.5 text-slate-500" />}
                  <span
                    className={`font-mono text-sm font-semibold text-slate-100 ${hostile ? 'text-red-200 drop-shadow-[0_0_6px_rgba(239,68,68,0.5)]' : ''}`}
                  >
                    <Highlight text={r.route.prefix} query={query} />
                  </span>
                  <Badge variant="outline" className={`text-[9px] h-4.5 px-1.5 ${st.badge}`}>
                    <span className={`inline-block w-1.5 h-1.5 rounded-full mr-1 ${st.dot} ${r.status !== 'normal' ? 'animate-pulse' : ''}`} />
                    {st.label}
                  </Badge>
                  {r.route.active ? (
                    <span className="text-[10px] font-mono text-slate-500">via {r.route.asPath}</span>
                  ) : (
                    <span className="text-[10px] font-mono text-slate-600">withdrawn</span>
                  )}
                  <span className="ml-auto flex items-center gap-2">
                    {quarantined && (
                      <Badge variant="outline" className="text-[9px] h-4 px-1.5 border-red-800 text-red-300 bg-red-950/50">
                        QUARANTINED · LP {r.route.locPref} · {r.route.community ?? 'no-export'}
                      </Badge>
                    )}
                    {r.underOverride && !quarantined && (
                      <Badge variant="outline" className="text-[9px] h-4 px-1.5 border-amber-800 text-amber-300 bg-amber-950/50">
                        LP {r.route.locPref} · OVERRIDE
                      </Badge>
                    )}
                    {trust !== undefined && (
                      <span className={`font-mono text-xs font-semibold ${trustText(trust)}`}>τ {trust.toFixed(2)}</span>
                    )}
                    {r.ml && (
                      <span className="text-[10px] font-mono text-slate-500">{r.ml.className}</span>
                    )}
                  </span>
                </div>

                {/* trust bar */}
                {trust !== undefined && (
                  <div className="mt-2 h-1.5 rounded bg-slate-800 overflow-hidden">
                    <div className={`h-full transition-all duration-500 ${trustColor(trust)}`} style={{ width: `${trust * 100}%` }} />
                  </div>
                )}

                {!isOpen && (
                  <div className="mt-1.5 flex items-center gap-2 text-[10px] font-mono text-slate-500 truncate">
                    {r.underOverride && r.recoveryStreak > 0 && (
                      <span className="text-cyan-400">recovery {r.recoveryStreak}/{rollbackTicks}</span>
                    )}
                    <span className="truncate">{r.policyAction}</span>
                    <span className="ml-auto hidden sm:inline text-slate-600 shrink-0">age {Math.max(0, Math.round(simTime - r.route.lastUpdateEpoch))}s</span>
                  </div>
                )}
                </button>
                {onToggleWatch && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onToggleWatch();
                    }}
                    title={starred ? 'unwatch — remove from watchlist alerts' : 'watch — get sound + flash alerts when this prefix changes status or trust tier'}
                    aria-pressed={starred}
                    aria-label={`${starred ? 'unwatch' : 'watch'} ${r.route.prefix}`}
                    className={`shrink-0 w-8 flex items-center justify-center rounded transition-colors focus-visible:ring-1 focus-visible:ring-violet-600 outline-none ${
                      starred
                        ? 'text-violet-300 hover:text-violet-200 hover:bg-violet-950/40'
                        : 'text-slate-600 hover:text-violet-300 hover:bg-violet-950/30'
                    } ${onFocus ? '' : 'rounded-r-lg'}`}
                  >
                    <Star className={`h-3.5 w-3.5 ${starred ? 'fill-violet-400/70 star-shimmer' : 'group-hover:text-violet-300/70'}`} />
                  </button>
                )}
                {onFocus && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onFocus();
                    }}
                    title="open prefix drill-down — full history, trust decomposition, RIB audit (deep-linked into the URL)"
                    aria-label={`drill down into ${r.route.prefix}`}
                    className="shrink-0 min-w-11 px-2.5 flex items-center justify-center text-slate-600 hover:text-emerald-300 hover:bg-emerald-950/30 rounded-r-lg transition-colors focus-visible:ring-1 focus-visible:ring-emerald-600 outline-none"
                  >
                    <Crosshair className="h-3.5 w-3.5" />
                  </button>
                )}
              </div>

              {isOpen && (
                <div className="px-3 pb-3 space-y-3 border-t border-slate-800 pt-2">
                  {/* trust trajectory sparkline */}
                  <div>
                    <div className="flex items-center gap-1.5 mb-1">
                      <TrendingDown className="h-3 w-3 text-cyan-400" />
                      <span className="text-[10px] font-semibold tracking-wider text-slate-400">TRUST TRAJECTORY</span>
                      <span className="ml-auto text-[9px] font-mono text-slate-600">
                        {trustHistory.length} samples · min {trustHistory.length > 0 ? Math.min(...trustHistory.map((p) => p.trust)).toFixed(2) : '—'} · tier bands shaded
                      </span>
                    </div>
                    <div className="rounded border border-slate-800 bg-slate-950/70 px-1.5 pt-1 pb-0.5">
                      <TrustSparkline points={trustHistory} thresholds={thresholds} ariaLabel={`trust history for ${r.route.prefix}`} />
                    </div>
                  </div>

                  {/* explainability */}
                  <div>
                    <div className="flex items-center gap-1.5 mb-1">
                      {r.status === 'normal' ? <ShieldCheck className="h-3 w-3 text-emerald-400" /> : <ShieldAlert className="h-3 w-3 text-amber-400" />}
                      <span className="text-[10px] font-semibold tracking-wider text-slate-400">EXPLAINABLE DIAGNOSTICS</span>
                    </div>
                    <ul className="space-y-0.5">
                      {r.reasons.map((reason, i) => (
                        <li key={i} className="text-[11px] font-mono text-slate-400 flex gap-1.5">
                          <span className="text-slate-600">›</span> {reason}
                        </li>
                      ))}
                    </ul>
                  </div>

                  {/* ML probabilities */}
                  {r.ml && (
                    <div>
                      <span className="text-[10px] font-semibold tracking-wider text-slate-400">
                        ML · {r.ml.model} ({Math.round(r.ml.confidence * 100)}% conf)
                      </span>
                      <div className="mt-1 grid grid-cols-4 gap-1.5">
                        {['Normal', 'Suspicious', 'Leak', 'Hijack'].map((label, i) => {
                          const p = r.ml?.probabilities[i] ?? 0;
                          const tone = ['bg-emerald-500', 'bg-amber-500', 'bg-orange-500', 'bg-red-500'][i];
                          return (
                            <Tooltip key={label}>
                              <TooltipTrigger asChild>
                                <div className="h-8 rounded bg-slate-900 border border-slate-800 overflow-hidden relative flex items-end">
                                  <div className={`absolute bottom-0 left-0 right-0 ${tone} opacity-60`} style={{ height: `${p * 100}%` }} />
                                  <span className="relative z-10 w-full text-center text-[9px] font-mono text-slate-200">
                                    {label.slice(0, 4)} {(p * 100).toFixed(0)}%
                                  </span>
                                </div>
                              </TooltipTrigger>
                              <TooltipContent className="bg-slate-900 border-slate-700 text-[10px] font-mono">
                                P({label}) = {p.toFixed(3)}
                              </TooltipContent>
                            </Tooltip>
                          );
                        })}
                      </div>
                    </div>
                  )}

                  {/* trust indicators */}
                  {r.trust && (
                    <div>
                      <span className="text-[10px] font-semibold tracking-wider text-slate-400">TRUST INDICATORS</span>
                      <div className="mt-1 grid grid-cols-6 gap-1">
                        {Object.entries(r.trust.indicators).map(([k, v]) => (
                          <div key={k} className="rounded bg-slate-900 border border-slate-800 p-1 text-center">
                            <div className="text-[9px] font-mono text-slate-500 uppercase">{k}</div>
                            <div className={`text-[11px] font-mono font-semibold ${trustText(v)}`}>{v.toFixed(2)}</div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* 10-feature vector */}
                  <div>
                    <span className="text-[10px] font-semibold tracking-wider text-slate-400">10-FEATURE BEHAVIORAL VECTOR</span>
                    <div className="mt-1 space-y-1">
                      {r.features.map((v, i) => (
                        <FeatureRow key={FEATURE_NAMES[i]} name={FEATURE_NAMES[i]} value={v} />
                      ))}
                    </div>
                  </div>

                  <div className="flex flex-wrap gap-x-4 gap-y-1 text-[10px] font-mono text-slate-500">
                    <span>origin AS<span className="text-slate-300 ml-1">{r.route.originAs}</span></span>
                    <span>age<span className="text-slate-300 ml-1">{r.features[7]}s</span></span>
                    <span>route age raw<span className="text-slate-300 ml-1">{Math.round(simTime - r.route.lastUpdateEpoch)}s</span></span>
                  </div>
                </div>
              )}
            </div>
  );
}
