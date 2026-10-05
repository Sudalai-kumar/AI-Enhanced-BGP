'use client';

import React from 'react';
import { TrustPoint } from '@/lib/bgp-sim/types';

/**
 * Compact per-prefix trust sparkline with policy-tier threshold bands.
 * Pure inline SVG — no chart library, renders in any density.
 */
export function TrustSparkline({
  points,
  thresholds,
  width = 560,
  height = 64,
  showBands = true,
  ariaLabel = 'trust score history',
}: {
  points: TrustPoint[];
  thresholds?: { normal: number; suspicious: number; leak: number };
  width?: number;
  height?: number;
  showBands?: boolean;
  ariaLabel?: string;
}) {
  const pts = points.slice(-80);
  if (pts.length < 2) {
    return (
      <div className="h-10 flex items-center justify-center text-[10px] font-mono text-slate-600">
        insufficient history — collecting telemetry…
      </div>
    );
  }

  const pad = 4;
  const t0 = pts[0].t;
  const t1 = pts[pts.length - 1].t;
  const span = Math.max(1, t1 - t0);
  const x = (t: number) => pad + ((t - t0) / span) * (width - pad * 2);
  const y = (trust: number) => height - pad - trust * (height - pad * 2);

  // trust polyline + area
  const line = pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${x(p.t).toFixed(1)},${y(p.trust).toFixed(1)}`).join(' ');
  const area = `${line} L${x(t1).toFixed(1)},${height - pad} L${x(t0).toFixed(1)},${height - pad} Z`;

  const last = pts[pts.length - 1];
  const lastTone =
    last.trust >= (thresholds?.normal ?? 0.85)
      ? '#34d399'
      : last.trust >= (thresholds?.suspicious ?? 0.55)
        ? '#fbbf24'
        : last.trust >= (thresholds?.leak ?? 0.25)
          ? '#fb923c'
          : '#f87171';

  const min = Math.min(...pts.map((p) => p.trust));
  const minPoint = pts.find((p) => p.trust === min)!;

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="w-full h-auto select-none"
      role="img"
      aria-label={`${ariaLabel}: last trust ${last.trust.toFixed(2)}, minimum ${min.toFixed(2)} over ${pts.length} samples`}
    >
      {/* tier threshold bands */}
      {showBands && thresholds && (
        <g>
          <rect x={pad} y={y(1)} width={width - pad * 2} height={Math.max(0, y(thresholds.normal) - y(1))} fill="#34d399" opacity="0.05" />
          <rect x={pad} y={y(thresholds.normal)} width={width - pad * 2} height={Math.max(0, y(thresholds.suspicious) - y(thresholds.normal))} fill="#fbbf24" opacity="0.05" />
          <rect x={pad} y={y(thresholds.suspicious)} width={width - pad * 2} height={Math.max(0, y(thresholds.leak) - y(thresholds.suspicious))} fill="#fb923c" opacity="0.05" />
          <rect x={pad} y={y(thresholds.leak)} width={width - pad * 2} height={Math.max(0, y(0) - y(thresholds.leak))} fill="#f87171" opacity="0.07" />
          <line x1={pad} x2={width - pad} y1={y(thresholds.normal)} y2={y(thresholds.normal)} stroke="#34d399" strokeWidth="0.6" strokeDasharray="3 3" opacity="0.4" />
          <line x1={pad} x2={width - pad} y1={y(thresholds.suspicious)} y2={y(thresholds.suspicious)} stroke="#fbbf24" strokeWidth="0.6" strokeDasharray="3 3" opacity="0.4" />
          <line x1={pad} x2={width - pad} y1={y(thresholds.leak)} y2={y(thresholds.leak)} stroke="#fb923c" strokeWidth="0.6" strokeDasharray="3 3" opacity="0.4" />
        </g>
      )}

      {/* area under curve */}
      <path d={area} fill={lastTone} opacity="0.12" />
      {/* trust line */}
      <path d={line} fill="none" stroke={lastTone} strokeWidth="1.6" strokeLinejoin="round" strokeLinecap="round" />

      {/* minimum marker */}
      <circle cx={x(minPoint.t)} cy={y(min)} r="2.4" fill="#f87171" opacity="0.9" />
      {/* last point + pulse */}
      <circle cx={x(last.t)} cy={y(last.trust)} r="2.6" fill={lastTone} />

      {/* axis labels */}
      <text x={pad} y={y(1) + 7} fontSize="7" fill="#475569" fontFamily="monospace">1.00</text>
      <text x={pad} y={height - 1} fontSize="7" fill="#475569" fontFamily="monospace">0.00</text>
      <text x={width - pad} y={height - 1} fontSize="7" fill="#475569" fontFamily="monospace" textAnchor="end">
        t={t1.toFixed(0)}s
      </text>
    </svg>
  );
}
