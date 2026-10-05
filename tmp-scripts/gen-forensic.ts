// Generates a sample forensic report artifact using the same builder the app uses.
// Run: bun run tmp-scripts/gen-forensic.ts
import { buildForensicReportHtml } from '../src/lib/bgp-sim/report';

const hist = [];
let t = 15780;
let trust = 0.94;
for (let i = 0; i < 24; i++) {
  t += 5;
  // dip during the attack window then recover
  const phase = i < 4 ? 0 : i < 10 ? 1 : 2;
  trust = phase === 1 ? Math.max(0.18, trust - 0.14) : phase === 0 ? trust - 0.02 : Math.min(0.97, trust + 0.08);
  hist.push({ t, trust: Math.round(trust * 1000) / 1000 });
}

const html = buildForensicReportHtml({
  prefix: '192.0.2.0/24',
  run: {
    runId: 21,
    scenarioId: 'S2',
    scenarioName: 'S2: Sub-Prefix Hijack (/25)',
    variantLabel: 'custom',
    mttd: 5,
    mttm: 10,
    msr: true,
    ribVerified: true,
    appliedPolicy: 'Quarantine (LocalPref 0 + no-export)',
    phase: 'mitigated',
    createdAt: new Date().toISOString(),
    comparison: {
      standardBgp: { detected: false, mttd: null, mitigated: false },
      rpki: { detected: false, mttd: null, mitigated: false },
      heuristic: { detected: true, mttd: 5, mitigated: false },
      aiControl: { detected: true, mttd: 5, mitigated: true },
    },
    injectedAt: 15785,
    detectedAt: 15790,
    mitigatedAt: 15800,
    rolledBackAt: null,
    groundTruth: 3,
  },
  routeStatus: 'recovering',
  trustScore: 0.975,
  trustHistory: hist,
  events: [
    { t: 15785, level: 'warn', source: 'attack', message: 'Rogue announcement for 192.0.2.0/25 observed — sub-prefix of 192.0.2.0/24 (longest-match capture).' },
    { t: 15790, level: 'danger', source: 'detection', message: 'Anomaly detected on 192.0.2.0/25: Prefix Hijack (trust 0.32) — MTTD 5s.' },
    { t: 15795, level: 'danger', source: 'policy', message: '[192.0.2.0/25] Quarantine (LocalPref 0 + no-export) applied via immediate-quarantine path.' },
    { t: 15800, level: 'success', source: 'metrics', message: 'Anomaly mitigated (MTTM) in 10s — Quarantine (LocalPref 0 + no-export).' },
    { t: 15805, level: 'info', source: 'shadow', message: 'Candidate Soft Deprioritization (LocalPref 80) staged in shadow queue (dwell time not met).' },
    { t: 15850, level: 'success', source: 'rollback', message: 'Autonomous rollback complete — LocalPref restored to 100 after 3 sustained healthy ticks.' },
  ],
  ribEntries: [
    { t: 15795, lp: 0, community: 'no-export', attempts: 1, outcome: 'verified', action: 'Quarantine' },
    { t: 15850, lp: 100, community: null, attempts: 1, outcome: 'verified', action: 'Rollback' },
  ],
  featureVector: [3, 2, 1, 25, 6, 4, 0, 45, 0, 2],
  featureNames: [
    'as_path_len', 'as_path_edit_distance', 'origin_as_change', 'prefix_mask_len',
    'announcements_per_minute', 'flap_count_5min', 'loc_pref_current', 'route_age_seconds',
    'valley_free_violation', 'neighbor_diversity',
  ],
  simTime: 15860,
});

await Bun.write('/home/z/my-project/download/sample-forensic-report.html', html);
console.log('written', html.length, 'bytes');
