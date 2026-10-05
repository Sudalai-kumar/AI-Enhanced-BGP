/**
 * Shared types for the AI-Enhanced BGP Simulation (contract between mini-service and frontend).
 * Source of truth: mini-services/bgp-sim/src/types.ts (copied to src/lib/bgp-sim/types.ts)
 */

export type ClassId = 0 | 1 | 2 | 3;
export const CLASS_NAMES: Record<ClassId, string> = {
  0: 'Normal',
  1: 'Suspicious',
  2: 'Route Leak',
  3: 'Prefix Hijack',
};

export const FEATURE_NAMES = [
  'as_path_len',
  'as_path_edit_distance',
  'origin_as_change',
  'prefix_mask_len',
  'announcements_per_minute',
  'flap_count_5min',
  'loc_pref_current',
  'route_age_seconds',
  'valley_free_violation',
  'neighbor_diversity',
] as const;

export type FeatureVector = number[]; // length 10, order = FEATURE_NAMES

export interface SimConfig {
  global: {
    defenderAs: number; // 65001 (core) | 65003 (edge)
    tickIntervalMs: number; // real ms per tick
    simSecondsPerTick: number; // sim seconds per tick
    telemetryNoise: boolean; // inject benign noise / FPR stress
    noiseFpr: number; // probability of transient false alarm per tick per prefix (0-0.2)
  };
  telemetry: { enabled: boolean; jitterSec: number };
  ml: {
    enabled: boolean; // master detection toggle (A0: off)
    mode: 'ml' | 'heuristic'; // detector type (A1: heuristic, A2+: ml)
    model: 'random_forest' | 'logistic_regression';
    sensitivity: number; // 0.5 - 2.0
    inferenceLatencyMs: number; // informational
  };
  trust: {
    enabled: boolean;
    weights: {
      origin: number;
      path: number;
      flap: number;
      prefix: number;
      peer: number;
      ml: number;
    };
  };
  shadow: {
    enabled: boolean;
    shadowDurationSec: number;
    requiredConsecutiveTicks: number;
    minDwellSec: number;
    immediateQuarantine: boolean; // hijacks bypass shadow staging
  };
  policy: {
    enabled: boolean;
    thresholds: { normal: number; suspicious: number; leak: number };
    lpNormal: number;
    lpSuspicious: number;
    lpLeak: number;
    lpHijack: number;
    quarantineCommunity: string;
    hysteresisDelta: number;
  };
  rollback: { enabled: boolean; requiredNormalTicks: number };
  ribVerification: { enabled: boolean; failureRate: number; latencyTicks: number };
  comparison: {
    enabled: boolean;
    standardBgp: boolean;
    rpki: boolean;
    heuristic: boolean;
  };
}

export interface RouteState {
  prefix: string;
  asPath: string;
  originAs: number;
  locPref: number;
  community: string | null;
  active: boolean; // announced or withdrawn
  lastUpdateEpoch: number; // sim seconds
  baselineOriginAs: number;
  baselinePath: string;
}

export interface MLResult {
  classId: ClassId;
  className: string;
  confidence: number;
  probabilities: number[]; // [normal, suspicious, leak, hijack]
  model: string;
}

export interface TrustResult {
  score: number;
  indicators: { origin: number; path: number; flap: number; prefix: number; peer: number; ml: number };
}

export interface ShadowEntry {
  prefix: string;
  targetLocPref: number;
  targetCommunity: string | null;
  candidateClass: ClassId;
  startTime: number;
  streak: number;
}

export type RouteStatus = 'normal' | 'suspicious' | 'leak' | 'hijack' | 'recovering' | 'withdrawn';

export interface RouteSnapshot {
  route: RouteState;
  features: FeatureVector;
  ml: MLResult | null;
  trust: TrustResult | null;
  status: RouteStatus;
  policyAction: string;
  reasons: string[];
  underOverride: boolean;
  recoveryStreak: number;
  mitigation: { lp: number; community: string | null } | null;
}

export interface SimNode {
  asn: number;
  label: string;
  role: 'tier1' | 'regional' | 'stub' | 'rogue';
  tier: string;
  x: number;
  y: number;
  status: 'up' | 'attacker' | 'flapping' | 'defending';
  isDefender: boolean;
}

export interface SimEdge {
  from: number;
  to: number;
  rel: 'peer-to-peer' | 'customer-to-provider' | 'provider-to-customer';
  status: 'normal' | 'anomalous' | 'quarantined';
}

export interface AttackScenarioDef {
  id: string;
  name: string;
  shortName: string;
  description: string;
  prefix: string;
  injectedPath: string;
  injectedOrigin: number;
  maskLen: number;
  groundTruthClass: ClassId;
  historical: boolean;
  flapIntervalSec: number | null; // for flapping scenario
  defaultDurationSec: number; // auto withdraw
  bestPathCompetition: boolean; // exact-prefix attacks compete with existing best-path
  attackerNode: number; // topology node to highlight
}

export interface CustomAttackSpec {
  prefix: string;
  originAs: number;
  asPath: string;
  maskLen: number;
  durationSec: number;
  flapping: boolean;
  flapIntervalSec: number;
}

export type RunPhase = 'idle' | 'injected' | 'detected' | 'mitigated' | 'rolledback' | 'failed';

export interface RunResult {
  runId: number;
  scenarioId: string;
  scenarioName: string;
  injectedAt: number;
  detectedAt: number | null;
  mitigatedAt: number | null;
  rolledBackAt: number | null;
  mttd: number | null;
  mttm: number | null;
  msr: boolean;
  ribVerified: boolean;
  appliedPolicy: string;
  appliedLocPref: number | null;
  groundTruth: ClassId;
  detectedClass: ClassId | null;
  phase: RunPhase;
  comparison: {
    standardBgp: { detected: boolean; mttd: number | null; mitigated: boolean };
    rpki: { detected: boolean; mttd: number | null; mitigated: boolean };
    heuristic: { detected: boolean; mttd: number | null; mitigated: boolean };
    aiControl: { detected: boolean; mttd: number | null; mitigated: boolean };
  };
}

export interface TrustPoint {
  t: number;
  trust: number;
  prefix: string;
}

export interface SimEvent {
  id: number;
  t: number; // sim seconds
  level: 'info' | 'warn' | 'danger' | 'success';
  source: string;
  message: string;
}

/** Structured RIB two-layer verification audit entry */
export interface RibLogEntry {
  id: number;
  t: number; // sim seconds
  prefix: string;
  lp: number;
  community: string | null;
  attempts: number;
  outcome: 'verified' | 'failed';
  action: string; // policy action name at commit time
}

export interface SimState {
  simTime: number;
  running: boolean;
  tick: number;
  config: SimConfig;
  variantLabel: string; // server-tracked config variant (preset / custom)
  nodes: SimNode[];
  edges: SimEdge[];
  routes: Record<string, RouteSnapshot>;
  shadowQueue: ShadowEntry[];
  activeRun: RunResult | null;
  history: RunResult[];
  trustHistory: TrustPoint[];
  events: SimEvent[];
  ribLog: RibLogEntry[];
  metrics: {
    totalRuns: number;
    avgMttd: number | null;
    avgMttm: number | null;
    msrPercent: number;
    detectionRate: number;
  };
}

export const ATTACK_SCENARIOS: AttackScenarioDef[] = [
  {
    id: 'S1',
    name: 'Direct Prefix Hijack',
    shortName: 'S1: Direct Hijack',
    description: 'Rogue AS65010 originates exact /24 prefix 192.0.2.0/24 allocated to stub AS65007. Competes with the legitimate direct path in best-path selection.',
    prefix: '192.0.2.0/24',
    injectedPath: '65001 65002 65006 65010',
    injectedOrigin: 65010,
    maskLen: 24,
    groundTruthClass: 3,
    historical: false,
    flapIntervalSec: null,
    defaultDurationSec: 120,
    bestPathCompetition: true,
    attackerNode: 65010,
  },
  {
    id: 'S2',
    name: 'Sub-Prefix Hijack (/25)',
    shortName: 'S2: Sub-Prefix /25',
    description: 'Rogue AS65010 originates more specific /25 sub-prefix 192.0.2.0/25. Longest-prefix match instantly captures traffic — immediate best-path.',
    prefix: '192.0.2.0/25',
    injectedPath: '65001 65002 65006 65010',
    injectedOrigin: 65010,
    maskLen: 25,
    groundTruthClass: 3,
    historical: false,
    flapIntervalSec: null,
    defaultDurationSec: 120,
    bestPathCompetition: false,
    attackerNode: 65010,
  },
  {
    id: 'S3',
    name: 'Burst Route Flapping',
    shortName: 'S3: Flapping Burst',
    description: 'Origin AS65007 rapidly oscillates announcement/withdrawal of 192.0.2.0/24, flooding control-plane churn. Damped via soft deprioritization.',
    prefix: '192.0.2.0/24',
    injectedPath: '65003 65007',
    injectedOrigin: 65007,
    maskLen: 24,
    groundTruthClass: 1,
    historical: false,
    flapIntervalSec: 5,
    defaultDurationSec: 150,
    bestPathCompetition: false,
    attackerNode: 65007,
  },
  {
    id: 'S4',
    name: 'YouTube 2008 Hijack Replay',
    shortName: 'S4: YouTube 2008',
    description: 'Historical Pakistan Telecom (AS17557) sub-prefix hijack of YouTube 208.65.153.0/24 (AS36561). Rogue replay on fresh prefix — immediate best-path.',
    prefix: '208.65.153.0/24',
    injectedPath: '65001 65002 17557',
    injectedOrigin: 17557,
    maskLen: 24,
    groundTruthClass: 3,
    historical: true,
    flapIntervalSec: null,
    defaultDurationSec: 120,
    bestPathCompetition: false,
    attackerNode: 65010,
  },
  {
    id: 'S5',
    name: 'Google 2017 Route Leak',
    shortName: 'S5: Google Leak',
    description: 'Rostelecom (AS12389) leaked Google 8.8.8.0/24 routes across peer boundaries — valley-free violation with cryptographically valid origin (AS15169).',
    prefix: '8.8.8.0/24',
    injectedPath: '65001 65002 12389 12389 15169',
    injectedOrigin: 15169,
    maskLen: 24,
    groundTruthClass: 2,
    historical: true,
    flapIntervalSec: null,
    defaultDurationSec: 120,
    bestPathCompetition: false,
    attackerNode: 65002,
  },
  {
    id: 'S6',
    name: 'Cloudflare 2019 Route Leak',
    shortName: 'S6: Cloudflare Leak',
    description: 'Allegheny (AS396531) leaked Cloudflare 104.16.0.0/16 to Verizon (AS701) — customer-to-peer transit leak with valid origin (AS13335).',
    prefix: '104.16.0.0/16',
    injectedPath: '65001 65002 701 396531 13335',
    injectedOrigin: 13335,
    maskLen: 16,
    groundTruthClass: 2,
    historical: true,
    flapIntervalSec: null,
    defaultDurationSec: 120,
    bestPathCompetition: false,
    attackerNode: 65002,
  },
];

export const DEFAULT_CONFIG: SimConfig = {
  global: {
    defenderAs: 65003,
    tickIntervalMs: 800,
    simSecondsPerTick: 5,
    telemetryNoise: true,
    noiseFpr: 0.02,
  },
  telemetry: { enabled: true, jitterSec: 0.2 },
  ml: {
    enabled: true,
    mode: 'ml' as 'ml' | 'heuristic',
    model: 'random_forest' as 'random_forest' | 'logistic_regression',
    sensitivity: 1.0,
    inferenceLatencyMs: 16.5,
  },
  trust: {
    enabled: true,
    weights: { origin: 0.2, path: 0.2, flap: 0.15, prefix: 0.15, peer: 0.1, ml: 0.2 },
  },
  shadow: {
    enabled: true,
    shadowDurationSec: 15,
    requiredConsecutiveTicks: 2,
    minDwellSec: 30,
    immediateQuarantine: true,
  },
  policy: {
    enabled: true,
    thresholds: { normal: 0.85, suspicious: 0.55, leak: 0.25 },
    lpNormal: 100,
    lpSuspicious: 80,
    lpLeak: 50,
    lpHijack: 0,
    quarantineCommunity: 'no-export',
    hysteresisDelta: 0.05,
  },
  rollback: { enabled: true, requiredNormalTicks: 3 },
  ribVerification: { enabled: true, failureRate: 0.05, latencyTicks: 1 },
  comparison: { enabled: true, standardBgp: true, rpki: true, heuristic: true },
};
