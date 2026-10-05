'use client';

import React from 'react';
import { RunPhase, SimEdge, SimNode } from '@/lib/bgp-sim/types';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';

interface Props {
  nodes: SimNode[];
  edges: SimEdge[];
  defenderAs: number;
  /** active hijack/leak propagation path for the topology overlay */
  attackPath?: { asnPath: number[]; prefix: string; scenarioId: string; phase: RunPhase } | null;
}

const ROLE_COLORS: Record<SimNode['role'], { fill: string; stroke: string; label: string }> = {
  tier1: { fill: '#134e4a', stroke: '#2dd4bf', label: 'Tier-1 Backbone' },
  regional: { fill: '#1e3a5f', stroke: '#38bdf8', label: 'Regional' },
  stub: { fill: '#3f3f46', stroke: '#a1a1aa', label: 'Stub' },
  rogue: { fill: '#4c1d24', stroke: '#f87171', label: 'Rogue' },
};

function nodeVisual(n: SimNode) {
  const base = ROLE_COLORS[n.role];
  if (n.status === 'attacker') return { fill: '#7f1d1d', stroke: '#ef4444', pulse: true };
  if (n.status === 'flapping') return { fill: '#78350f', stroke: '#f59e0b', pulse: true };
  if (n.status === 'defending') return { fill: '#064e3b', stroke: '#34d399', pulse: true };
  return { ...base, pulse: false };
}

const STATUS_TEXT: Record<SimNode['status'], string> = {
  up: 'Session established',
  attacker: 'Injecting anomalous routes',
  flapping: 'Route oscillation burst',
  defending: 'Active mitigation policy',
};

export function TopologyGraph({ nodes, edges, defenderAs, attackPath }: Props) {
  const nodeMap = new Map(nodes.map((n) => [n.asn, n]));
  const W = 1120;
  const H = 470;

  // animated telemetry packets along a subset of healthy edges (deterministic pick)
  const packetEdges = edges
    .map((e, i) => ({ e, i }))
    .filter(({ e }) => e.status === 'normal' && e.rel === 'customer-to-provider')
    .filter((_, idx) => idx % 3 === 0)
    .slice(0, 6);

  // ---- hijack propagation overlay: segments from origin (last ASN) toward defender side ----
  const blocked = attackPath?.phase === 'mitigated';
  const pathAsns = React.useMemo(
    () => (attackPath ? attackPath.asnPath.map((a) => nodeMap.get(a)).filter((n): n is SimNode => !!n) : []),
    [attackPath, nodes],
  );
  const overlaySegs = React.useMemo(() => {
    if (!attackPath || pathAsns.length < 2) return [];
    const segs: { d: string; from: SimNode; to: SimNode; i: number }[] = [];
    for (let i = pathAsns.length - 1; i > 0; i--) {
      const a = pathAsns[i]; // upstream (toward origin)
      const b = pathAsns[i - 1]; // downstream (toward defender)
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const len = Math.hypot(dx, dy) || 1;
      const ox = (-dy / len) * 16; // perpendicular offset — lifts overlay off real edges
      const oy = (dx / len) * 16;
      const cx = (a.x + b.x) / 2 + ox;
      const cy = (a.y + b.y) / 2 + oy;
      segs.push({ d: `M ${a.x} ${a.y} Q ${cx} ${cy} ${b.x} ${b.y}`, from: a, to: b, i: segs.length });
    }
    return segs;
  }, [attackPath, pathAsns]);
  const originNode = pathAsns.length > 0 ? pathAsns[pathAsns.length - 1] : null;

  return (
    <TooltipProvider delayDuration={80}>
      <div className="relative w-full">
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto select-none" role="img" aria-label="10-AS BGP topology map">
          <defs>
            <pattern id="grid" width="28" height="28" patternUnits="userSpaceOnUse">
              <path d="M 28 0 L 0 0 0 28" fill="none" stroke="#1e293b" strokeWidth="0.6" />
            </pattern>
            <marker id="arrowhead" markerWidth="6" markerHeight="4" refX="5" refY="2" orient="auto">
              <polygon points="0 0, 6 2, 0 4" fill="#64748b" />
            </marker>
            <filter id="edge-glow" x="-40%" y="-40%" width="180%" height="180%">
              <feGaussianBlur stdDeviation="2.2" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>
          <rect width={W} height={H} fill="url(#grid)" rx="8" />

          {/* edges */}
          {edges.map((e) => {
            const a = nodeMap.get(e.from);
            const b = nodeMap.get(e.to);
            if (!a || !b) return null;
            const anomalous = e.status !== 'normal';
            const quarantined = e.status === 'quarantined';
            const midX = (a.x + b.x) / 2;
            const midY = (a.y + b.y) / 2;
            return (
              <g key={`${e.from}-${e.to}`}>
                <line
                  x1={a.x}
                  y1={a.y}
                  x2={b.x}
                  y2={b.y}
                  stroke={anomalous ? (quarantined ? '#ef4444' : '#f59e0b') : '#334155'}
                  strokeWidth={anomalous ? 2.4 : 1.4}
                  strokeDasharray={
                    e.rel === 'peer-to-peer' ? '7 5' : quarantined ? '4 4' : undefined
                  }
                  className={anomalous ? 'animate-pulse' : undefined}
                  filter={anomalous ? 'url(#edge-glow)' : undefined}
                  markerEnd={e.rel === 'customer-to-provider' ? 'url(#arrowhead)' : undefined}
                />
                {anomalous && (
                  <circle cx={midX} cy={midY} r="4" fill={quarantined ? '#ef4444' : '#f59e0b'}>
                    <animate attributeName="r" values="3;6;3" dur="1.2s" repeatCount="indefinite" />
                  </circle>
                )}
                <text
                  x={midX}
                  y={midY - 8}
                  textAnchor="middle"
                  fontSize="9"
                  fill={anomalous ? '#fbbf24' : '#475569'}
                  className="font-mono"
                >
                  {e.rel === 'peer-to-peer' ? 'peer' : e.rel === 'customer-to-provider' ? 'c2p' : 'p2c'}
                </text>
              </g>
            );
          })}

          {/* animated telemetry packets on healthy transit edges */}
          {packetEdges.map(({ e, i }) => {
            const a = nodeMap.get(e.from);
            const b = nodeMap.get(e.to);
            if (!a || !b) return null;
            const dur = 3.2 + (i % 3) * 1.1;
            const delay = (i * 0.7).toFixed(1);
            return (
              <circle key={`pkt-${e.from}-${e.to}`} r="2.6" fill="#38bdf8" opacity="0.85">
                <animateMotion
                  dur={`${dur}s`}
                  begin={`${delay}s`}
                  repeatCount="indefinite"
                  path={`M ${a.x} ${a.y} L ${b.x} ${b.y}`}
                />
                <animate attributeName="opacity" values="0;0.9;0" dur={`${dur}s`} begin={`${delay}s`} repeatCount="indefinite" />
              </circle>
            );
          })}

          {/* hijack propagation overlay — curved red flow from origin toward defender */}
          {overlaySegs.length > 0 && (
            <g pointerEvents="none">
              {overlaySegs.map((seg) => (
                <path
                  key={`atk-${seg.i}`}
                  d={seg.d}
                  fill="none"
                  stroke={blocked ? '#7f1d1d' : '#ef4444'}
                  strokeWidth={blocked ? 2.5 : 3.2}
                  strokeLinecap="round"
                  opacity={blocked ? 0.85 : 0.95}
                  filter="url(#edge-glow)"
                  className={blocked ? undefined : 'attack-flow'}
                />
              ))}
              {/* origin marker chip: scenario + prefix */}
              {originNode && attackPath && (
                <g transform={`translate(${originNode.x + 26}, ${originNode.y - 30})`}>
                  <rect
                    x="0"
                    y="0"
                    rx="4"
                    height="17"
                    width={Math.max(attackPath.prefix.length * 5.6 + attackPath.scenarioId.length * 6 + 26, 96)}
                    fill={blocked ? '#450a0a' : '#7f1d1d'}
                    stroke={blocked ? '#b91c1c' : '#ef4444'}
                    strokeWidth="1"
                    opacity="0.96"
                  />
                  <circle cx="9" cy="8.5" r="3" fill={blocked ? '#f87171' : '#ef4444'} className={blocked ? undefined : 'animate-pulse'} />
                  <text x="17" y="12" fontSize="8.5" fill="#fecaca" className="font-mono">
                    {attackPath.scenarioId} · {attackPath.prefix}
                  </text>
                </g>
              )}
              {/* attack packets flowing origin → defender */}
              {!blocked &&
                overlaySegs.map((seg) => (
                  <circle key={`atkpkt-${seg.i}`} r="3.4" fill="#fca5a5">
                    <animateMotion dur="2.1s" begin={`${seg.i * 0.55}s`} repeatCount="indefinite" path={seg.d} />
                    <animate attributeName="opacity" values="0;1;1;0" keyTimes="0;0.15;0.8;1" dur="2.1s" begin={`${seg.i * 0.55}s`} repeatCount="indefinite" />
                  </circle>
                ))}
              {/* quarantine block: X at the defender-entry segment when mitigated */}
              {blocked && overlaySegs.length > 0 && (
                <g>
                  {(() => {
                    const seg = overlaySegs[overlaySegs.length - 1];
                    const mx = (seg.from.x + seg.to.x) / 2;
                    const my = (seg.from.y + seg.to.y) / 2;
                    return (
                      <g transform={`translate(${mx}, ${my})`}>
                        <circle r="11" fill="#020617" stroke="#ef4444" strokeWidth="2" />
                        <line x1="-5" y1="-5" x2="5" y2="5" stroke="#ef4444" strokeWidth="2.2" strokeLinecap="round" />
                        <line x1="5" y1="-5" x2="-5" y2="5" stroke="#ef4444" strokeWidth="2.2" strokeLinecap="round" />
                        <animate attributeName="opacity" values="0.65;1;0.65" dur="1.6s" repeatCount="indefinite" />
                      </g>
                    );
                  })()}
                </g>
              )}
            </g>
          )}

          {/* red rings on ASes carrying the attack path */}
          {pathAsns.length > 1 &&
            pathAsns.map((n) => (
              <circle
                key={`atk-ring-${n.asn}`}
                cx={n.x}
                cy={n.y}
                r={(n.role === 'tier1' ? 34 : 28) + 4.5}
                fill="none"
                stroke={blocked ? '#7f1d1d' : '#ef4444'}
                strokeWidth="1.6"
                strokeDasharray="3 4"
                opacity={blocked ? 0.7 : 0.95}
                pointerEvents="none"
              />
            ))}

          {/* nodes */}
          {nodes.map((n) => {
            const v = nodeVisual(n);
            const r = n.role === 'tier1' ? 34 : 28;
            const isDefender = n.asn === defenderAs;
            return (
              <Tooltip key={n.asn}>
                <TooltipTrigger asChild>
                  <g className="cursor-pointer transition-opacity hover:opacity-90">
                    <circle cx={n.x} cy={n.y} r={r + 3} fill="transparent" className="node-hit" />
                    {isDefender && (
                      <circle
                        cx={n.x}
                        cy={n.y}
                        r={r + 8}
                        fill="none"
                        stroke="#34d399"
                        strokeWidth="1.6"
                        strokeDasharray="5 3"
                        className="animate-[spin_8s_linear_infinite]"
                        style={{ transformOrigin: `${n.x}px ${n.y}px` }}
                      />
                    )}
                    <circle cx={n.x} cy={n.y} r={r} fill={v.fill} stroke={v.stroke} strokeWidth={v.pulse ? 2.5 : 1.6} className={v.pulse ? 'animate-pulse' : undefined} />
                    <text x={n.x} y={n.y - 4} textAnchor="middle" fontSize="11.5" fill="#f1f5f9" className="font-mono font-semibold">
                      AS{n.asn}
                    </text>
                    <text x={n.x} y={n.y + 11} textAnchor="middle" fontSize="8" fill="#94a3b8" className="font-mono">
                      {n.role === 'rogue' ? 'ROGUE' : n.role === 'tier1' ? 'TIER-1' : n.role === 'regional' ? 'REGIONAL' : 'STUB'}
                    </text>
                    {isDefender && (
                      <text x={n.x} y={n.y + r + 13} textAnchor="middle" fontSize="8.5" fill="#34d399" className="font-mono font-semibold tracking-wider">
                        ◆ {n.asn === 65001 ? 'CORE DEFENDER' : 'EDGE DEFENDER'}
                      </text>
                    )}
                  </g>
                </TooltipTrigger>
                <TooltipContent side="top" className="bg-slate-900 border-slate-700 text-slate-200">
                  <div className="text-xs font-mono space-y-0.5">
                    <div className="font-semibold text-slate-100">AS{n.asn}</div>
                    <div className="text-slate-400">{n.tier}</div>
                    <div className={n.status === 'up' ? 'text-emerald-400' : n.status === 'attacker' ? 'text-red-400' : 'text-amber-400'}>
                      ● {STATUS_TEXT[n.status]}
                    </div>
                  </div>
                </TooltipContent>
              </Tooltip>
            );
          })}
        </svg>

        <div className="absolute bottom-2 right-3 flex flex-wrap gap-x-3 gap-y-1 text-[10px] font-mono text-slate-500">
          <span className="flex items-center gap-1"><span className="inline-block w-3 h-0.5 bg-slate-600" /> eBGP session</span>
          <span className="flex items-center gap-1"><span className="inline-block w-3 h-0.5 border-t border-dashed border-slate-500" /> peer-to-peer</span>
          <span className="flex items-center gap-1"><span className="inline-block w-2 h-2 rounded-full bg-sky-400 animate-pulse" /> telemetry packet</span>
          <span className="flex items-center gap-1"><span className="inline-block w-2 h-2 rounded-full bg-amber-500" /> anomalous path</span>
          <span className="flex items-center gap-1"><span className="inline-block w-2 h-2 rounded-full bg-red-500" /> quarantined</span>
          <span className="flex items-center gap-1"><span className="inline-block w-4 h-[3px] rounded bg-red-500 attack-flow" /> attack flow</span>
          <span className="flex items-center gap-1 text-red-400">✕ blocked</span>
        </div>
      </div>
    </TooltipProvider>
  );
}
