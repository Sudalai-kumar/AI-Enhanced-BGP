'use client';

import React, { useMemo, useState } from 'react';
import { SimConfig, DEFAULT_CONFIG } from '@/lib/bgp-sim/types';
import { Badge } from '@/components/ui/badge';
import { GitCompare, ChevronDown, ChevronRight, RotateCcw } from 'lucide-react';

/** Flatten a nested config object into dot-paths (leaf values only). */
function flatten(obj: Record<string, unknown>, prefix = ''): Map<string, unknown> {
  const out = new Map<string, unknown>();
  for (const [k, v] of Object.entries(obj)) {
    const path = prefix ? `${prefix}.${k}` : k;
    if (v !== null && typeof v === 'object' && !Array.isArray(v)) {
      const nested = flatten(v as Record<string, unknown>, path);
      for (const [np, nv] of nested) out.set(np, nv);
    } else {
      out.set(path, v);
    }
  }
  return out;
}

const SECTION_LABELS: Record<string, string> = {
  global: 'Global & Clock',
  telemetry: 'Telemetry',
  ml: 'ML Detector',
  trust: 'Trust Engine',
  shadow: 'Shadow Validation',
  policy: 'Policy Engine',
  rollback: 'Rollback',
  ribVerification: 'RIB Verification',
  comparison: 'Comparison Defenses',
};

const SECTION_TONES: Record<string, string> = {
  global: 'text-slate-300',
  telemetry: 'text-cyan-300',
  ml: 'text-amber-300',
  trust: 'text-teal-300',
  shadow: 'text-sky-300',
  policy: 'text-orange-300',
  rollback: 'text-emerald-300',
  ribVerification: 'text-violet-300',
  comparison: 'text-fuchsia-300',
};

interface DiffEntry {
  path: string;
  section: string;
  key: string;
  from: unknown;
  to: unknown;
  kind: 'toggle' | 'number' | 'string';
}

function fmt(v: unknown): string {
  if (typeof v === 'boolean') return v ? 'on' : 'off';
  if (typeof v === 'number') {
    if (v < 1 && v > 0 && Math.round(v * 1000) / 1000 === v) return String(v); // fractions like 0.15
    return String(Math.round(v * 100) / 100);
  }
  return String(v);
}

/**
 * Live configuration drift monitor — diffs the running config against the
 * A4 · Full System baseline (DEFAULT_CONFIG). Every editable knob the operator
 * touches shows up here with its baseline value for one-click visual review.
 */
export function ConfigDiff({
  config,
  variantLabel,
  onResetConfig,
}: {
  config: SimConfig;
  variantLabel: string;
  onResetConfig: () => void;
}) {
  const [open, setOpen] = useState(true);

  const diffs = useMemo<DiffEntry[]>(() => {
    const live = flatten(config as unknown as Record<string, unknown>);
    const base = flatten(DEFAULT_CONFIG as unknown as Record<string, unknown>);
    const out: DiffEntry[] = [];
    for (const [path, to] of live) {
      const from = base.get(path);
      if (from === undefined ? to !== undefined : from !== to) {
        const [section, ...rest] = path.split('.');
        out.push({
          path,
          section: SECTION_LABELS[section] ?? section,
          key: rest.join('.') || section,
          from: from ?? null,
          to,
          kind: typeof to === 'boolean' ? 'toggle' : typeof to === 'number' ? 'number' : 'string',
        });
      }
    }
    return out;
  }, [config]);

  const bySection = useMemo(() => {
    const groups = new Map<string, DiffEntry[]>();
    for (const d of diffs) {
      if (!groups.has(d.section)) groups.set(d.section, []);
      groups.get(d.section)!.push(d);
    }
    return [...groups.entries()];
  }, [diffs]);

  const togglesOff = diffs.filter((d) => d.kind === 'toggle' && d.to === false).length;

  return (
    <div className="rounded-lg border border-slate-700 bg-slate-900/60 p-3">
      <div className="flex items-center justify-between gap-2 mb-2">
        <button
          className="flex items-center gap-1.5 min-w-0 text-left"
          onClick={() => setOpen((o) => !o)}
          aria-expanded={open}
          aria-label="toggle config diff panel"
        >
          {open ? <ChevronDown className="h-3.5 w-3.5 text-slate-500" /> : <ChevronRight className="h-3.5 w-3.5 text-slate-500" />}
          <GitCompare className="h-3.5 w-3.5 text-violet-400" />
          <span className="text-xs font-semibold tracking-wide text-slate-200">Config Diff</span>
          {diffs.length === 0 ? (
            <Badge variant="outline" className="text-[9px] px-1.5 h-4 border-emerald-800 bg-emerald-950/50 text-emerald-300 shrink-0">
              matches A4 baseline
            </Badge>
          ) : (
            <Badge variant="outline" className="text-[9px] px-1.5 h-4 border-violet-800 bg-violet-950/50 text-violet-300 shrink-0 tabular-nums">
              {diffs.length} changed
            </Badge>
          )}
        </button>
        <button
          onClick={onResetConfig}
          className="inline-flex items-center gap-1 text-[10px] font-mono text-slate-500 hover:text-emerald-300 transition-colors"
          title="restore every parameter to the A4 baseline"
        >
          <RotateCcw className="h-2.5 w-2.5" /> restore A4
        </button>
      </div>

      <div className="flex items-center gap-2 text-[10px] font-mono text-slate-500">
        <span className="truncate">
          variant: <span className="text-slate-300">{variantLabel}</span>
        </span>
        {togglesOff > 0 && (
          <span className="shrink-0 px-1.5 py-px rounded-full border border-amber-900 bg-amber-950/40 text-amber-300">
            {togglesOff} subsystem{togglesOff > 1 ? 's' : ''} disabled
          </span>
        )}
      </div>

      {open && (
        <div className="mt-2 space-y-2 max-h-64 overflow-y-auto scrollbar-thin pr-1">
          {diffs.length === 0 ? (
            <div className="text-[11px] font-mono text-slate-600 py-2 text-center">
              every knob at baseline — the engine is running the paper&apos;s proposed configuration
            </div>
          ) : (
            bySection.map(([section, entries]) => (
              <div key={section} className="rounded border border-slate-800 bg-slate-950/60 overflow-hidden">
                <div className={`px-2 py-1 text-[10px] font-mono font-semibold border-b border-slate-800 bg-slate-900/60 ${SECTION_TONES[section.split(' ')[0].toLowerCase()] ?? 'text-slate-300'}`}>
                  {section}
                  <span className="float-right text-slate-600 tabular-nums">{entries.length}</span>
                </div>
                <div className="divide-y divide-slate-800/60">
                  {entries.map((e) => {
                    const turnedOff = e.kind === 'toggle' && e.to === false;
                    const turnedOn = e.kind === 'toggle' && e.to === true && e.from === false;
                    return (
                      <div key={e.path} className="flex items-center gap-2 px-2 py-1 hover:bg-slate-900/50 transition-colors">
                        <span className="w-28 shrink-0 truncate text-[10px] font-mono text-slate-400" title={e.path}>
                          {e.key}
                        </span>
                        <span className={`shrink-0 text-[10px] font-mono ${turnedOff ? 'text-red-400' : 'text-slate-600'}`}>{fmt(e.from)}</span>
                        <span className={`shrink-0 text-slate-600 ${turnedOff ? 'text-red-500' : 'text-slate-600'}`}>→</span>
                        <span
                          className={`ml-auto shrink-0 text-[10px] font-mono font-semibold px-1.5 py-px rounded ${
                            turnedOff
                              ? 'text-red-300 bg-red-950/50 border border-red-900/60'
                              : turnedOn
                                ? 'text-emerald-300 bg-emerald-950/50 border border-emerald-900/60'
                                : 'text-amber-300 bg-amber-950/40 border border-amber-900/50'
                          }`}
                        >
                          {fmt(e.to)}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
