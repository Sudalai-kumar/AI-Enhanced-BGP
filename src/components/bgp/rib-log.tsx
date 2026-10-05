'use client';

import React, { useState } from 'react';
import { SimState, RibLogEntry } from '@/lib/bgp-sim/types';
import { Badge } from '@/components/ui/badge';
import { CheckCircle2, XCircle, ShieldCheck, ChevronDown, ChevronRight, Layers } from 'lucide-react';

function lpTone(lp: number, cfgNormal: number) {
  if (lp >= cfgNormal) return 'text-emerald-300';
  if (lp >= 50) return 'text-amber-300';
  if (lp > 0) return 'text-orange-300';
  return 'text-red-400';
}

export function RibLogViewer({ state, onFocusPrefix }: { state: SimState; onFocusPrefix?: (prefix: string) => void }) {
  const [open, setOpen] = useState(false);
  const entries = state.ribLog;
  const normalLp = state.config.policy.lpNormal;

  const verified = entries.filter((e) => e.outcome === 'verified');
  const failed = entries.filter((e) => e.outcome === 'failed');
  const passRate = entries.length ? Math.round((verified.length / entries.length) * 100) : 100;
  const retried = entries.filter((e) => e.attempts > 1).length;
  const maxAttempts = entries.reduce((m, e) => Math.max(m, e.attempts), 0);

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950/60">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-3 py-2 text-left hover:bg-slate-900/40 transition-colors rounded-t-lg"
        aria-expanded={open}
      >
        <div className="flex items-center gap-2">
          {open ? <ChevronDown className="h-3.5 w-3.5 text-slate-500" /> : <ChevronRight className="h-3.5 w-3.5 text-slate-500" />}
          <Layers className="h-4 w-4 text-amber-400" />
          <span className="text-xs font-semibold text-slate-200">RIB Verification Log</span>
          <span className="text-[10px] font-mono text-slate-600">two-layer commit audit</span>
        </div>
        <div className="flex items-center gap-2 text-[10px] font-mono">
          <span className={passRate >= 90 ? 'text-emerald-400' : passRate >= 60 ? 'text-amber-400' : 'text-red-400'}>
            {passRate}% pass
          </span>
          <Badge variant="outline" className="text-[9px] h-4 px-1.5 border-amber-900/60 text-amber-300 bg-amber-950/30">
            {entries.length} commits
          </Badge>
          {retried > 0 && (
            <Badge variant="outline" className="text-[9px] h-4 px-1.5 border-red-900/60 text-red-400 bg-red-950/30">
              {retried} retried
            </Badge>
          )}
        </div>
      </button>

      {open && (
        <div className="border-t border-slate-800/60">
          {/* stats strip */}
          <div className="grid grid-cols-4 gap-px bg-slate-800/40">
            {[
              { label: 'verified', value: verified.length, tone: 'text-emerald-300' },
              { label: 'failed', value: failed.length, tone: 'text-red-400' },
              { label: 'max attempts', value: maxAttempts || '—', tone: 'text-amber-300' },
              { label: 'failure rate cfg', value: `${Math.round(state.config.ribVerification.failureRate * 100)}%`, tone: 'text-slate-300' },
            ].map((s) => (
              <div key={s.label} className="bg-slate-950/80 px-2 py-1.5 text-center">
                <div className={`text-[13px] font-mono font-bold ${s.tone}`}>{s.value}</div>
                <div className="text-[8.5px] font-mono uppercase tracking-wider text-slate-600">{s.label}</div>
              </div>
            ))}
          </div>

          {/* entries */}
          <div className="max-h-64 overflow-y-auto scrollbar-thin">
            {entries.length === 0 ? (
              <div className="py-6 text-center text-[11px] font-mono text-slate-600">
                <ShieldCheck className="h-4 w-4 mx-auto mb-1.5 text-slate-700" />
                no verification commits yet — policy overrides appear here with attempt counts
              </div>
            ) : (
              <table className="w-full text-[10px] font-mono">
                <thead>
                  <tr className="text-slate-500 border-b border-slate-800 sticky top-0 bg-slate-950/95 backdrop-blur">
                    <th className="text-left py-1.5 px-2 font-medium">t</th>
                    <th className="text-left py-1.5 px-2 font-medium">prefix</th>
                    <th className="text-center py-1.5 px-2 font-medium">LP</th>
                    <th className="text-left py-1.5 px-2 font-medium">community</th>
                    <th className="text-center py-1.5 px-2 font-medium">attempt</th>
                    <th className="text-left py-1.5 px-2 font-medium">action</th>
                    <th className="text-center py-1.5 px-2 font-medium">result</th>
                  </tr>
                </thead>
                <tbody>
                  {entries.map((e: RibLogEntry) => (
                    <tr key={e.id} className={`border-b border-slate-900/60 ${e.outcome === 'failed' ? 'bg-red-950/10' : ''}`}>
                      <td className="py-1.5 px-2 text-slate-500">{e.t}s</td>
                      <td className="py-1.5 px-2 text-slate-300">
                        {onFocusPrefix ? (
                          <button
                            onClick={() => onFocusPrefix(e.prefix)}
                            className="font-mono hover:text-emerald-300 hover:underline decoration-dotted underline-offset-2 transition-colors"
                            title={`drill down into ${e.prefix}`}
                          >
                            {e.prefix}
                          </button>
                        ) : (
                          e.prefix
                        )}
                      </td>
                      <td className={`py-1.5 px-2 text-center font-bold ${lpTone(e.lp, normalLp)}`}>{e.lp}</td>
                      <td className="py-1.5 px-2 text-violet-300">{e.community ?? '—'}</td>
                      <td className="py-1.5 px-2 text-center">
                        <span className={e.attempts > 1 ? 'text-amber-400' : 'text-slate-500'}>{e.attempts}×</span>
                      </td>
                      <td className="py-1.5 px-2 text-slate-500 max-w-52 truncate" title={e.action}>{e.action}</td>
                      <td className="py-1.5 px-2 text-center">
                        {e.outcome === 'verified' ? (
                          <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400 mx-auto" />
                        ) : (
                          <XCircle className="h-3.5 w-3.5 text-red-500 mx-auto" />
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
