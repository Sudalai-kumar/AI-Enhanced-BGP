'use client';

import React, { useState, useMemo } from 'react';
import { SimConfig } from '@/lib/bgp-sim/types';
import { Button } from '@/components/ui/button';
import { FileTerminal, Copy, Download, ChevronDown, ChevronRight, Check } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';

/** Generate an FRR-style route-map / BGP config preview from the live policy config. */
export function buildRouteMapConfig(c: SimConfig, defenderAs: number): string {
  const p = c.policy;
  const q = c.shadow;
  const lines: string[] = [];
  lines.push(`! ============================================================`);
  lines.push(`! FRR (FRRouting) configuration preview — AI-Enhanced BGP`);
  lines.push(`! generated from live control-plane config (variant: editable)`);
  lines.push(`! defender AS${defenderAs} · policy engine ${p.enabled ? 'ENABLED' : 'DISABLED'}`);
  lines.push(`! ============================================================`);
  lines.push(`!`);
  lines.push(`! --- community lists -----------------------------------------`);
  lines.push(`bgp community-list standard ${p.quarantineCommunity.toUpperCase().replace(/-/g, '_')} permit ${p.quarantineCommunity}`);
  lines.push(`!`);
  lines.push(`! --- trust-tier route-map (applied inbound) ------------------`);
  lines.push(`route-map AI-TRUST-POLICY permit ${p.lpNormal}`);
  lines.push(`  description Normal (trust >= ${p.thresholds.normal})`);
  lines.push(`  set local-preference ${p.lpNormal}`);
  lines.push(`route-map AI-TRUST-POLICY permit ${p.lpSuspicious}`);
  lines.push(`  description Suspicious (${p.thresholds.suspicious} <= trust < ${p.thresholds.normal})`);
  lines.push(`  set local-preference ${p.lpSuspicious}`);
  lines.push(`route-map AI-TRUST-POLICY permit ${p.lpLeak}`);
  lines.push(`  description Route Leak (${p.thresholds.leak} <= trust < ${p.thresholds.suspicious})`);
  lines.push(`  set local-preference ${p.lpLeak}`);
  lines.push(`route-map AI-TRUST-POLICY permit ${p.lpHijack}`);
  lines.push(`  description Prefix Hijack (trust < ${p.thresholds.leak}) — QUARANTINE`);
  lines.push(`  set local-preference ${p.lpHijack}`);
  lines.push(`  set community ${p.quarantineCommunity} additive`);
  lines.push(`route-map AI-TRUST-POLICY deny 65535`);
  lines.push(`  description implicit deny — unmatched routes rejected`);
  lines.push(`!`);
  lines.push(`! --- anti-thrashing / shadow staging -------------------------`);
  if (c.shadow.enabled) {
    lines.push(`! shadow validator: ${q.requiredConsecutiveTicks} consecutive ticks · ${q.shadowDurationSec}s staging · ${q.minDwellSec}s dwell`);
    lines.push(`! hysteresis delta: ${p.hysteresisDelta} · immediate quarantine: ${q.immediateQuarantine ? 'ON (hijack fast-path)' : 'OFF'}`);
  } else {
    lines.push(`! shadow validator DISABLED — policy commits apply immediately`);
  }
  lines.push(`!`);
  lines.push(`! --- router bgp core ------------------------------------------`);
  lines.push(`router bgp ${defenderAs}`);
  lines.push(`  no bgp ebgp-requires-policy`);
  lines.push(`  no bgp default ipv4-unicast`);
  lines.push(`  bgp bestpath as-path multipath-relax`);
  if (c.rollback.enabled) {
    lines.push(`  ! autonomous rollback: restore LP ${p.lpNormal} after ${c.rollback.requiredNormalTicks} consecutive normal observations`);
  }
  lines.push(`  neighbor EDGE-PEERS route-map AI-TRUST-POLICY in`);
  lines.push(`  neighbor EDGE-PEERS route-map AI-TRUST-POLICY out`);
  lines.push(`  address-family ipv4 unicast`);
  lines.push(`    neighbor EDGE-PEERS activate`);
  lines.push(`    neighbor EDGE-PEERS send-community both`);
  if (c.ribVerification.enabled) {
    lines.push(`    ! two-layer RIB verification: latency ${c.ribVerification.latencyTicks} tick(s) · failure-rate ${Math.round(c.ribVerification.failureRate * 100)}% (retry loop)`);
  }
  lines.push(`    network 192.0.2.0/24`);
  lines.push(`    network 198.51.100.0/24`);
  lines.push(`    network 203.0.113.0/24`);
  lines.push(`  exit-address-family`);
  lines.push(`!`);
  lines.push(`! --- detector pipeline (control-plane, non-dataplane) ---------`);
  lines.push(`! telemetry collector: ${c.telemetry.enabled ? `enabled (jitter ${c.telemetry.jitterSec}s)` : 'disabled'}`);
  lines.push(`! ML detector: ${c.ml.enabled ? `${c.ml.model} · mode=${c.ml.mode} · sensitivity=${c.ml.sensitivity} · inference ${c.ml.inferenceLatencyMs}ms` : 'disabled (A0 baseline)'}`);
  lines.push(`! trust engine: ${c.trust.enabled ? 'origin 0.20 path 0.20 flap 0.15 prefix 0.15 peer 0.10 ml 0.20' : 'disabled'}`);
  lines.push(`! end`);
  return lines.join('\n');
}

export function RouteMapPreview({ config }: { config: SimConfig }) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const { toast } = useToast();
  const text = useMemo(() => buildRouteMapConfig(config, config.global.defenderAs), [config]);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
      toast({ title: 'Copied to clipboard', description: 'FRR route-map configuration copied.' });
    } catch {
      toast({ title: 'Copy failed', description: 'Clipboard unavailable in this context.' });
    }
  };

  const download = () => {
    const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `bgp-defender-AS${config.global.defenderAs}-route-map.conf`;
    a.click();
    URL.revokeObjectURL(url);
    toast({ title: 'Config downloaded', description: `bgp-defender-AS${config.global.defenderAs}-route-map.conf` });
  };

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950/60">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-3 py-2 text-left hover:bg-slate-900/40 transition-colors rounded-t-lg"
        aria-expanded={open}
      >
        <div className="flex items-center gap-2">
          {open ? <ChevronDown className="h-3.5 w-3.5 text-slate-500" /> : <ChevronRight className="h-3.5 w-3.5 text-slate-500" />}
          <FileTerminal className="h-4 w-4 text-teal-400" />
          <span className="text-xs font-semibold text-slate-200">Live Route-Map Preview</span>
          <span className="text-[10px] font-mono text-slate-600 hidden sm:inline">FRR-style · follows your sliders</span>
        </div>
        <div className="flex items-center gap-2 text-[10px] font-mono text-slate-500">
          <span className="hidden md:inline">AS{config.global.defenderAs}</span>
          <span className={config.policy.enabled ? 'text-emerald-400' : 'text-red-400'}>
            policy {config.policy.enabled ? 'on' : 'off'}
          </span>
        </div>
      </button>

      {open && (
        <div className="border-t border-slate-800/60">
          <div className="flex items-center justify-between px-3 py-1.5 bg-slate-900/30">
            <span className="text-[9.5px] font-mono text-slate-500">
              reflects: LP {config.policy.lpNormal}/{config.policy.lpSuspicious}/{config.policy.lpLeak}/{config.policy.lpHijack} · τ {config.policy.thresholds.normal}/{config.policy.thresholds.suspicious}/{config.policy.thresholds.leak} · {config.policy.quarantineCommunity}
            </span>
            <div className="flex items-center gap-1.5">
              <Button
                size="sm"
                variant="outline"
                onClick={copy}
                className="h-6 px-2 text-[10px] font-mono border-slate-700 text-slate-300 hover:bg-slate-800"
              >
                {copied ? <Check className="h-3 w-3 mr-1 text-emerald-400" /> : <Copy className="h-3 w-3 mr-1" />}
                {copied ? 'copied' : 'copy'}
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={download}
                className="h-6 px-2 text-[10px] font-mono border-slate-700 text-slate-300 hover:bg-slate-800"
              >
                <Download className="h-3 w-3 mr-1" /> .conf
              </Button>
            </div>
          </div>
          <pre className="max-h-72 overflow-auto scrollbar-thin px-3 py-2.5 text-[10px] font-mono text-slate-400 leading-relaxed whitespace-pre">{text}</pre>
        </div>
      )}
    </div>
  );
}
