import {
  ATTACK_SCENARIOS,
  AttackScenarioDef,
  ClassId,
  CustomAttackSpec,
  DEFAULT_CONFIG,
  FEATURE_NAMES,
  FeatureVector,
  MLResult,
  RibLogEntry,
  RunResult,
  RouteSnapshot,
  RouteState,
  RouteStatus,
  ShadowEntry,
  SimConfig,
  SimEdge,
  SimEvent,
  SimNode,
  SimState,
  TrustPoint,
  TrustResult,
} from './types';
import {
  buildEdges,
  checkValleyFreeViolation,
  levenshtein,
  NODES,
  PREFIX_BASELINES,
} from './topology';
import { classify, heuristicDetects, rpkiDetects } from './classifier';

/** Prefixes that exist in the registry but are not announced at baseline (attack-only) */
const DORMANT_PREFIXES = new Set(['192.0.2.0/25', '208.65.153.0/24', '8.8.8.0/24', '104.16.0.0/16']);

interface WindowEvent {
  t: number;
  asPath: string;
  originAs: number;
  active: boolean;
}

interface ActiveAttack {
  scenario: AttackScenarioDef;
  injectedAt: number;
  durationSec: number;
  flapping: boolean;
  flapIntervalSec: number;
  nextFlapAt: number;
  flapAnnounced: boolean;
  bestPathCompetition: boolean;
  currentAnomalousVisible: boolean;
  run: RunResult;
  withdrawn: boolean;
}

interface RibPending {
  lp: number;
  community: string | null;
  dueTick: number;
  attempts: number;
  prefix: string;
}

interface PrefixRuntime {
  prefix: string;
  route: RouteState;
  dormant: boolean;
  window: WindowEvent[];
  features: FeatureVector;
  ml: MLResult | null;
  trust: TrustResult | null;
  status: RouteStatus;
  policyAction: string;
  reasons: string[];
  underOverride: boolean;
  recoveryStreak: number;
  lastPolicyChange: number;
  shadowEntry: ShadowEntry | null;
  ribPending: RibPending | null;
  ribVerifiedLp: number | null;
}

function clone<T>(o: T): T {
  return JSON.parse(JSON.stringify(o)) as T;
}

function deepMerge<T>(base: T, patch: unknown): T {
  if (patch === null || patch === undefined) return base;
  if (typeof base !== 'object' || base === null || Array.isArray(base)) return patch as T;
  if (typeof patch !== 'object' || Array.isArray(patch)) return patch as T;
  const out: Record<string, unknown> = { ...(base as Record<string, unknown>) };
  for (const [k, v] of Object.entries(patch as Record<string, unknown>)) {
    const bv = (base as Record<string, unknown>)[k];
    out[k] = bv !== undefined && typeof bv === 'object' && bv !== null && !Array.isArray(bv)
      ? deepMerge(bv, v)
      : v;
  }
  return out as T;
}

/**
 * Safety-net watchdog: detects a stalled controller loop (running but no ticks
 * for a while — e.g. after a hot module swap or an unexpected timer loss) and
 * reschedules it automatically. Runs for the engine's entire lifetime.
 */
export function startWatchdog(getEngine: () => BGPSimEngine | null): ReturnType<typeof setInterval> {
  let lastTick = -1;
  let lastAdvance = Date.now();
  return setInterval(() => {
    const e = getEngine();
    if (!e) return;
    if (!e.running) {
      lastTick = -1;
      return;
    }
    if (e.tick !== lastTick) {
      lastTick = e.tick;
      lastAdvance = Date.now();
      return;
    }
    // running but clock frozen for > 12s (many tick intervals) — self-heal
    if (Date.now() - lastAdvance > 12_000) {
      console.warn('[bgp-sim] watchdog: controller loop stalled while running — rescheduling');
      e.rescheduleLoop();
      lastAdvance = Date.now();
    }
  }, 4_000);
}

export class BGPSimEngine {
  config: SimConfig = clone(DEFAULT_CONFIG);
  simTime = 0;
  tick = 0;
  running = false;
  /** config variant label tracked server-side (preset A0-A4 / custom) */
  variantLabel = 'A4 · Full System';
  private eventSeq = 1;
  private runSeq = 0;
  private runInternalSeq = 0;
  /** engine boot id — used to disambiguate persisted runs across engine restarts */
  private readonly bootId = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  private routes = new Map<string, PrefixRuntime>();
  private events: SimEvent[] = [];
  private trustHistory: TrustPoint[] = [];
  private history: RunResult[] = [];
  private ribLog: RibLogEntry[] = [];
  private ribLogSeq = 1;
  private activeAttack: ActiveAttack | null = null;
  private nodeStatus = new Map<number, SimNode['status']>();
  private timer: ReturnType<typeof setInterval> | null = null;
  private onChange: (state: SimState) => void = () => {};
  private rng = Math.random;
  /** dedupe set: runs already persisted to the run archive */
  private persistedRuns = new Set<string>();

  constructor() {
    this.resetRoutes();
  }

  setOnChange(cb: (state: SimState) => void) {
    this.onChange = cb;
  }

  private log(level: SimEvent['level'], source: string, message: string) {
    const ev: SimEvent = {
      id: this.eventSeq++,
      t: Math.round(this.simTime * 10) / 10,
      level,
      source,
      message,
    };
    this.events.push(ev);
    if (this.events.length > 400) this.events.splice(0, this.events.length - 400);
  }

  private resetRoutes() {
    this.routes.clear();
    for (const [prefix, base] of Object.entries(PREFIX_BASELINES)) {
      const dormant = DORMANT_PREFIXES.has(prefix);
      this.routes.set(prefix, {
        prefix,
        route: {
          prefix,
          asPath: base.asPath,
          originAs: base.originAs,
          locPref: 100,
          community: null,
          active: !dormant,
          lastUpdateEpoch: 0,
          baselineOriginAs: base.originAs,
          baselinePath: base.asPath,
        },
        dormant,
        window: dormant
          ? []
          : [{ t: 0, asPath: base.asPath, originAs: base.originAs, active: true }],
        features: new Array(10).fill(0),
        ml: null,
        trust: null,
        status: dormant ? 'withdrawn' : 'normal',
        policyAction: 'Baseline (LP 100)',
        reasons: [],
        underOverride: false,
        recoveryStreak: 0,
        lastPolicyChange: 0,
        shadowEntry: null,
        ribPending: null,
        ribVerifiedLp: null,
      });
    }
  }

  reset() {
    this.stop();
    this.simTime = 0;
    this.tick = 0;
    this.activeAttack = null;
    this.history = [];
    this.events = [];
    this.trustHistory = [];
    this.ribLog = [];
    this.nodeStatus.clear();
    this.resetRoutes();
    this.log('info', 'system', 'Simulation reset to clean 10-AS baseline state.');
    this.emit();
  }

  start() {
    if (this.running) return;
    this.running = true;
    this.log('info', 'system', `Autonomous controller loop engaged — telemetry polling every ${this.config.global.tickIntervalMs}ms.`);
    this.scheduleTick();
    this.emit();
  }

  pause() {
    if (!this.running) return;
    this.running = false;
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
    this.log('warn', 'system', 'Controller loop paused by operator.');
    this.emit();
  }

  stop() {
    this.running = false;
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
  }

  /** watchdog entry point: force-reschedule the tick loop (keeps running flag) */
  rescheduleLoop() {
    if (!this.running) return;
    this.scheduleTick();
    this.emit();
  }

  private scheduleTick() {
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
    if (!this.running) return;
    this.timer = setInterval(() => this.tickOnce(), this.config.global.tickIntervalMs);
  }

  setConfig(patch: unknown) {
    this.config = deepMerge(this.config, patch);
    this.variantLabel = 'custom';
    if (this.running) this.scheduleTick(); // apply tick interval live
    this.log('info', 'config', 'Simulation configuration updated live by operator.');
    this.emit();
  }

  applyPreset(variant: string): boolean {
    const v = variant.toUpperCase();
    const c = clone(DEFAULT_CONFIG);
    const ok = this.applyPresetConfig(v, c);
    if (!ok) return false;
    this.config = c;
    this.variantLabel = `${v} preset`;
    this.log('info', 'config', `Ablation preset ${v} applied — subsystem flags reconfigured.`);
    this.emit();
    return true;
  }

  /** restore full-system defaults (used by the "reset defaults" control) */
  resetConfig() {
    this.config = clone(DEFAULT_CONFIG);
    this.variantLabel = 'A4 · Full System';
    this.log('info', 'config', 'Configuration restored to full-system defaults (A4).');
    this.emit();
  }

  private applyPresetConfig(v: string, c: SimConfig): boolean {
    if (v === 'A0') {
      c.ml.enabled = false;
      c.trust.enabled = false;
      c.shadow.enabled = false;
      c.policy.enabled = false;
      c.rollback.enabled = false;
      c.ribVerification.enabled = false;
    } else if (v === 'A1') {
      c.ml.enabled = true;
      c.ml.mode = 'heuristic';
      c.trust.enabled = false;
      c.shadow.enabled = false;
      c.policy.enabled = true;
      c.rollback.enabled = true;
      c.ribVerification.enabled = true;
    } else if (v === 'A2') {
      c.ml.enabled = true;
      c.ml.mode = 'ml';
      c.trust.enabled = false;
      c.shadow.enabled = false;
      c.policy.enabled = true;
      c.rollback.enabled = true;
      c.ribVerification.enabled = true;
    } else if (v === 'A3') {
      c.ml.enabled = true;
      c.ml.mode = 'ml';
      c.trust.enabled = true;
      c.shadow.enabled = false;
      c.policy.enabled = true;
      c.rollback.enabled = true;
      c.ribVerification.enabled = true;
    } else if (v === 'A4') {
      // full system = defaults
    } else {
      return false;
    }
    return true;
  }

  // ------------------------------------------------------------------ attacks

  injectScenario(scenarioId: string, durationSec?: number): boolean {
    const scenario = ATTACK_SCENARIOS.find((s) => s.id === scenarioId);
    if (!scenario) return false;
    this.internalInject(scenario, durationSec ?? scenario.defaultDurationSec, scenario.flapIntervalSec !== null, scenario.flapIntervalSec ?? 0);
    return true;
  }

  injectCustom(spec: CustomAttackSpec): { ok: boolean; error?: string } {
    const prefix = spec.prefix.trim();
    if (!/^\d{1,3}(\.\d{1,3}){3}\/\d{1,2}$/.test(prefix)) {
      return { ok: false, error: 'Prefix must look like 203.0.113.0/24' };
    }
    const mask = parseInt(prefix.split('/')[1], 10);
    if (mask < 8 || mask > 32) return { ok: false, error: 'Mask length must be 8-32' };
    const origin = Math.floor(spec.originAs);
    if (!(origin >= 1 && origin <= 4294967295)) return { ok: false, error: 'Origin AS must be 1-4294967295' };
    const tokens = spec.asPath.trim().split(/\s+/).filter(Boolean).map(Number);
    if (tokens.some((t) => !Number.isFinite(t) || t <= 0)) {
      return { ok: false, error: 'AS-Path must be space-separated AS numbers' };
    }
    const base = PREFIX_BASELINES[prefix];
    const attackerNode =
      NODES.some((n) => n.asn === origin) ? origin : tokens.includes(65002) ? 65002 : 65010;
    const scenario: AttackScenarioDef = {
      id: 'CX',
      name: 'Custom Attack',
      shortName: 'CX: Custom',
      description: `Operator-defined anomaly on ${prefix} from AS${origin}.`,
      prefix,
      injectedPath: spec.asPath.trim(),
      injectedOrigin: origin,
      maskLen: mask,
      groundTruthClass: origin !== (base?.originAs ?? origin) ? 3 : 2,
      historical: false,
      flapIntervalSec: spec.flapping ? spec.flapIntervalSec : null,
      defaultDurationSec: spec.durationSec,
      bestPathCompetition: !!base && mask <= base.maskLen,
      attackerNode,
    };
    this.internalInject(scenario, spec.durationSec, spec.flapping, spec.flapIntervalSec);
    return { ok: true };
  }

  private internalInject(scenario: AttackScenarioDef, durationSec: number, flapping: boolean, flapIntervalSec: number) {
    // clean any previous attack first
    if (this.activeAttack) this.withdrawAttack(true);
    const rt = this.routes.get(scenario.prefix);
    if (!rt) {
      // create runtime for unknown prefix
      this.routes.set(scenario.prefix, {
        prefix: scenario.prefix,
        route: {
          prefix: scenario.prefix,
          asPath: scenario.injectedPath,
          originAs: scenario.injectedOrigin,
          locPref: 100,
          community: null,
          active: false,
          lastUpdateEpoch: 0,
          baselineOriginAs: scenario.injectedOrigin,
          baselinePath: scenario.injectedPath,
        },
        dormant: true,
        window: [],
        features: new Array(10).fill(0),
        ml: null,
        trust: null,
        status: 'withdrawn',
        policyAction: 'Baseline (LP 100)',
        reasons: [],
        underOverride: false,
        recoveryStreak: 0,
        lastPolicyChange: 0,
        shadowEntry: null,
        ribPending: null,
        ribVerifiedLp: null,
      });
    }
    this.runInternalSeq += 1;
    const run: RunResult = {
      runId: this.runInternalSeq,
      scenarioId: scenario.id,
      scenarioName: scenario.name,
      injectedAt: this.simTime,
      detectedAt: null,
      mitigatedAt: null,
      rolledBackAt: null,
      mttd: null,
      mttm: null,
      msr: false,
      ribVerified: false,
      appliedPolicy: '',
      appliedLocPref: null,
      groundTruth: scenario.groundTruthClass,
      detectedClass: null,
      phase: 'injected',
      comparison: {
        standardBgp: { detected: false, mttd: null, mitigated: false },
        rpki: { detected: false, mttd: null, mitigated: false },
        heuristic: { detected: false, mttd: null, mitigated: false },
        aiControl: { detected: false, mttd: null, mitigated: false },
      },
    };
    this.activeAttack = {
      scenario,
      injectedAt: this.simTime,
      durationSec,
      flapping,
      flapIntervalSec: Math.max(1, flapIntervalSec),
      nextFlapAt: this.simTime + Math.max(1, flapIntervalSec),
      flapAnnounced: true,
      bestPathCompetition: scenario.bestPathCompetition,
      currentAnomalousVisible: true,
      run,
      withdrawn: false,
    };
    // apply anomalous route
    const r = this.routes.get(scenario.prefix)!;
    r.route.asPath = scenario.injectedPath;
    r.route.originAs = scenario.injectedOrigin;
    r.route.locPref = 100;
    r.route.community = null;
    r.route.active = true;
    r.route.lastUpdateEpoch = this.simTime;
    r.window.push({ t: this.simTime, asPath: scenario.injectedPath, originAs: scenario.injectedOrigin, active: true });
    r.underOverride = false;
    r.shadowEntry = null;
    r.ribPending = null;
    r.ribVerifiedLp = null;
    this.nodeStatus.set(scenario.attackerNode, scenario.flapIntervalSec !== null ? 'flapping' : 'attacker');
    this.log(
      'danger',
      'attack',
      `${scenario.shortName} injected: ${scenario.prefix} announced by AS${scenario.injectedOrigin} via path "${scenario.injectedPath}".`
    );
    if (!this.running) this.start();
    this.emit();
  }

  withdrawAttack(silent = false) {
    const atk = this.activeAttack;
    if (!atk) return;
    const rt = this.routes.get(atk.scenario.prefix);
    if (rt) {
      if (rt.dormant) {
        rt.route.active = false;
        rt.window.push({ t: this.simTime, asPath: rt.route.asPath, originAs: rt.route.originAs, active: false });
        rt.status = 'withdrawn';
        rt.ml = null;
        rt.trust = null;
        rt.shadowEntry = null;
        rt.ribPending = null;
        rt.underOverride = false;
        rt.policyAction = 'Withdrawn (no RIB entry)';
      } else {
        const base = PREFIX_BASELINES[atk.scenario.prefix];
        rt.route.asPath = base.asPath;
        rt.route.originAs = base.originAs;
        rt.route.lastUpdateEpoch = this.simTime;
        // fresh observation epoch: controller window restarts on route restoration
        rt.window = [{ t: this.simTime - 60, asPath: base.asPath, originAs: base.originAs, active: true }];
        if (rt.underOverride) {
          rt.status = 'recovering';
        } else {
          rt.status = 'normal';
          rt.route.locPref = this.config.policy.lpNormal;
          rt.route.community = null;
        }
      }
    }
    if (this.nodeStatus.get(atk.scenario.attackerNode) !== 'up') {
      this.nodeStatus.set(atk.scenario.attackerNode, 'up');
    }
    if (!silent) {
      this.log('success', 'attack', `Attack withdrawn — rogue announcement for ${atk.scenario.prefix} removed from the testbed.`);
    }
    atk.withdrawn = true;
    atk.flapping = false;
    atk.bestPathCompetition = false;
    const shouldAwaitRollback =
      !rt?.dormant && !!rt?.underOverride && this.config.rollback.enabled && atk.run.mitigatedAt !== null;
    if (!shouldAwaitRollback) {
      // finalize run immediately (dormant prefix, no override, or rollback disabled)
      if (atk.run.phase !== 'rolledback' && atk.run.phase !== 'failed') {
        atk.run.phase = atk.run.mitigatedAt !== null ? 'mitigated' : atk.run.detectedAt !== null ? 'detected' : 'failed';
        atk.run.msr = atk.run.mitigatedAt !== null && atk.run.ribVerified;
        this.finalizeRun(atk.run);
      }
      this.activeAttack = null;
    } else {
      this.log('info', 'rollback', `[${atk.scenario.prefix}] Override still active — awaiting autonomous rollback before closing run #${atk.run.runId}.`);
    }
    this.emit();
  }

  // ------------------------------------------------------------------ features

  private extractFeatures(rt: PrefixRuntime): FeatureVector {
    const route = rt.route;
    const base = PREFIX_BASELINES[rt.prefix];
    const baseOrigin = base?.originAs ?? rt.route.baselineOriginAs;
    const basePath = (base?.asPath ?? rt.route.baselinePath).split(' ');
    const pathTokens = route.asPath.split(' ').filter(Boolean);
    const now = this.simTime;

    let editDistance = 0;
    if (pathTokens.join(' ') !== basePath.join(' ')) {
      const tailMatch =
        pathTokens.length > 0 &&
        basePath.length > 0 &&
        pathTokens[pathTokens.length - 1] === basePath[basePath.length - 1] &&
        (pathTokens.slice(-basePath.length).join(' ') === basePath.join(' ') ||
          basePath.slice(-pathTokens.length).join(' ') === pathTokens.join(' '));
      if (!tailMatch) editDistance = levenshtein(pathTokens, basePath);
    }

    const originAsChange = route.originAs !== baseOrigin ? 1 : 0;
    const maskLen = parseInt(rt.prefix.split('/')[1] ?? '24', 10) || 24;

    // announcements per minute (60 sim sec window)
    const win60 = rt.window.filter((e) => e.t >= now - 60);
    let transitions60 = 0;
    for (let i = 1; i < win60.length; i++) {
      if (win60[i].asPath !== win60[i - 1].asPath || win60[i].originAs !== win60[i - 1].originAs || win60[i].active !== win60[i - 1].active) {
        transitions60++;
      }
    }
    const elapsed = Math.max(1, Math.min(60, now - (rt.window[0]?.t ?? now)));
    const announcementsPerMinute = (transitions60 / elapsed) * 60;

    // flap count (300 sim sec window)
    const win300 = rt.window.filter((e) => e.t >= now - 300);
    let flaps = 0;
    for (let i = 1; i < win300.length; i++) {
      if (win300[i].asPath !== win300[i - 1].asPath || win300[i].originAs !== win300[i - 1].originAs || win300[i].active !== win300[i - 1].active) {
        flaps++;
      }
    }

    const routeAge = route.active ? Math.max(0, now - route.lastUpdateEpoch) : 0;
    const valley = checkValleyFreeViolation(route.asPath);
    const neighborDiversity = this.activeAttack && this.activeAttack.scenario.prefix === rt.prefix ? 0.4 : 1.0;

    return [
      pathTokens.length,
      editDistance,
      originAsChange,
      maskLen,
      Math.round(announcementsPerMinute * 10) / 10,
      flaps,
      route.locPref,
      Math.round(routeAge * 10) / 10,
      valley,
      neighborDiversity,
    ];
  }

  private computeTrust(f: FeatureVector, mlProbNormal: number): TrustResult {
    const w = this.config.trust.weights;
    const tOrigin = f[2] > 0.5 ? 0 : 1;
    const tPath = f[8] > 0.5 ? 0 : Math.max(0, 1 - f[1] * 0.2);
    const tFlap = Math.max(0, 1 - f[5] / 5);
    const tPrefix = f[3] > 24 ? 0.4 : 1;
    const tPeer = f[9];
    const tMl = mlProbNormal;
    const score = w.origin * tOrigin + w.path * tPath + w.flap * tFlap + w.prefix * tPrefix + w.peer * tPeer + w.ml * tMl;
    return {
      score: Math.round(Math.min(1, Math.max(0, score)) * 1000) / 1000,
      indicators: {
        origin: tOrigin,
        path: tPath,
        flap: tFlap,
        prefix: tPrefix,
        peer: tPeer,
        ml: tMl,
      },
    };
  }

  private classifyRoute(rt: PrefixRuntime, f: FeatureVector): MLResult {
    const { enabled, mode, model, sensitivity } = this.config.ml;
    if (!enabled) {
      return {
        classId: 0,
        className: 'Normal',
        confidence: 1,
        probabilities: [1, 0, 0, 0],
        model: 'none (detector disabled)',
      };
    }
    if (mode === 'heuristic') {
      if (f[2] > 0.5) return { classId: 3, className: 'Prefix Hijack', confidence: 0.9, probabilities: [0.05, 0.05, 0.1, 0.8], model: 'heuristic-rules' };
      if (f[8] > 0.5) return { classId: 2, className: 'Route Leak', confidence: 0.85, probabilities: [0.08, 0.12, 0.75, 0.05], model: 'heuristic-rules' };
      if (f[5] >= 3 || f[4] >= 6) return { classId: 1, className: 'Suspicious', confidence: 0.8, probabilities: [0.15, 0.75, 0.05, 0.05], model: 'heuristic-rules' };
      if (f[3] > 24) return { classId: 1, className: 'Suspicious', confidence: 0.7, probabilities: [0.2, 0.7, 0.05, 0.05], model: 'heuristic rules' };
      return { classId: 0, className: 'Normal', confidence: 0.92, probabilities: [0.92, 0.05, 0.02, 0.01], model: 'heuristic-rules' };
    }
    return classify(f, this.config);
  }

  private buildReasons(f: FeatureVector, ml: MLResult): string[] {
    const reasons: string[] = [];
    if (f[2] > 0.5) reasons.push(`Origin AS changed (baseline AS${'…'} → observed AS${'…'}): origin_as_change=1`);
    if (f[8] > 0.5) reasons.push('Gao-Rexford valley-free violation in AS-path');
    if (f[3] > 24) reasons.push(`Sub-prefix deaggregation detected (/${f[3]} more specific than /24 allocation)`);
    if (f[5] >= 3) reasons.push(`High route churn: ${f[5]} flaps in 5-minute window`);
    if (f[1] >= 2 && f[8] <= 0.5) reasons.push(`Significant AS-path edit distance (${f[1]} edits vs baseline)`);
    if (f[4] >= 6) reasons.push(`Elevated announcement rate (${f[4]}/min)`);
    if (ml.classId !== 0 && reasons.length === 0) reasons.push(`ML ${ml.model} classified as ${ml.className} (${Math.round(ml.confidence * 100)}%)`);
    if (reasons.length === 0) reasons.push('All behavioral indicators and topology relationships normal');
    return reasons;
  }

  // ------------------------------------------------------------------ policy

  private mapTrustToPolicy(trust: number | null, classId: ClassId, currentLp: number): { lp: number; community: string | null; action: string } {
    const p = this.config.policy;
    const t = trust ?? (classId === 0 ? 1 : classId === 1 ? 0.7 : classId === 2 ? 0.5 : 0.2);
    if (classId === 3 || t < p.thresholds.leak) {
      return { lp: p.lpHijack, community: p.quarantineCommunity, action: `Quarantine (LocalPref ${p.lpHijack} + ${p.quarantineCommunity})` };
    }
    if (classId === 2 || t < p.thresholds.suspicious) {
      return { lp: p.lpLeak, community: null, action: `Hard Deprioritization (LocalPref ${p.lpLeak})` };
    }
    // hysteresis: rising vs falling thresholds
    if (currentLp === p.lpNormal) {
      if (t < p.thresholds.normal - p.hysteresisDelta) {
        return { lp: p.lpSuspicious, community: null, action: `Soft Deprioritization (LocalPref ${p.lpSuspicious})` };
      }
      return { lp: p.lpNormal, community: null, action: `Default Baseline (LocalPref ${p.lpNormal})` };
    }
    if (t >= p.thresholds.normal && classId === 0) {
      return { lp: p.lpNormal, community: null, action: `Default Baseline (LocalPref ${p.lpNormal})` };
    }
    return { lp: p.lpSuspicious, community: null, action: `Soft Deprioritization (LocalPref ${p.lpSuspicious})` };
  }

  // ------------------------------------------------------------------ tick

  tickOnce() {
    this.tick += 1;
    this.simTime += this.config.global.simSecondsPerTick;
    const atk = this.activeAttack;

    // attack lifecycle: auto-withdraw / flapping / best-path competition
    if (atk && !atk.withdrawn) {
      if (!atk.flapping && this.simTime - atk.injectedAt > atk.durationSec) {
        this.withdrawAttack();
        return;
      }
      if (atk.flapping) {
        // stop flapping after duration, then normal withdraw
        if (this.simTime - atk.injectedAt > atk.durationSec) {
          this.withdrawAttack();
          return;
        }
        if (this.simTime >= atk.nextFlapAt) {
          const rt = this.routes.get(atk.scenario.prefix)!;
          atk.flapAnnounced = !atk.flapAnnounced;
          rt.route.active = atk.flapAnnounced;
          if (atk.flapAnnounced) {
            rt.route.lastUpdateEpoch = this.simTime;
            rt.window.push({ t: this.simTime, asPath: rt.route.asPath, originAs: rt.route.originAs, active: true });
          } else {
            rt.window.push({ t: this.simTime, asPath: rt.route.asPath, originAs: rt.route.originAs, active: false });
          }
          atk.nextFlapAt = this.simTime + atk.flapIntervalSec;
        }
      } else if (atk.bestPathCompetition) {
        // exact-prefix hijack: anomalous route competes with incumbent best-path
        const visible = this.rng() < 0.55;
        if (visible !== atk.currentAnomalousVisible) {
          const rt = this.routes.get(atk.scenario.prefix)!;
          atk.currentAnomalousVisible = visible;
          const base = PREFIX_BASELINES[atk.scenario.prefix];
          if (visible) {
            rt.route.asPath = atk.scenario.injectedPath;
            rt.route.originAs = atk.scenario.injectedOrigin;
          } else {
            rt.route.asPath = base.asPath;
            rt.route.originAs = base.originAs;
          }
          rt.route.lastUpdateEpoch = this.simTime;
          rt.window.push({ t: this.simTime, asPath: rt.route.asPath, originAs: rt.route.originAs, active: true });
        }
      }
    }

    // per-prefix pipeline
    for (const rt of this.routes.values()) {
      const isAttackPrefix = this.activeAttack?.scenario.prefix === rt.prefix;
      if (rt.route.active === false && rt.dormant && !isAttackPrefix) {
        rt.status = 'withdrawn';
        continue;
      }
      // NOTE: mid-flap withdrawn routes still flow through the pipeline —
      // churn features (announce rate, flaps) are computed from the sliding window.

      // 1. telemetry + feature extraction
      let f = this.extractFeatures(rt);

      // 2. telemetry noise / FPR stress (transient false alarms)
      let noiseInjected = false;
      if (this.config.global.telemetryNoise && !this.activeAttack?.run.mitigatedAt) {
        if (this.rng() < this.config.global.noiseFpr && f[2] === 0 && f[8] === 0) {
          f = [...f];
          f[4] = Math.max(f[4], 7 + Math.floor(this.rng() * 4)); // transient announcement burst
          noiseInjected = true;
        }
      }

      rt.features = f;

      // 3. ML classification
      const ml = this.classifyRoute(rt, f);
      rt.ml = ml;

      // 4. trust scoring
      let trust: TrustResult | null = null;
      if (this.config.trust.enabled) {
        trust = this.computeTrust(f, ml.probabilities[0]);
        rt.trust = trust;
      } else {
        rt.trust = null;
      }
      const effTrust = trust?.score ?? null;

      // trust history for charts
      if (this.tick % 1 === 0) {
        this.trustHistory.push({ t: this.simTime, trust: effTrust ?? 1, prefix: rt.prefix });
        if (this.trustHistory.length > 600) this.trustHistory.splice(0, this.trustHistory.length - 600);
      }

      // 5. status
      const isAnomalous = ml.classId !== 0 || (effTrust !== null && effTrust < this.config.policy.thresholds.suspicious);
      if (rt.underOverride) {
        rt.status = effTrust !== null && effTrust >= this.config.policy.thresholds.normal && ml.classId === 0 ? 'recovering' : (ml.classId as number) === 3 ? 'hijack' : ml.classId === 2 ? 'leak' : 'suspicious';
      } else {
        rt.status = ml.classId === 3 ? 'hijack' : ml.classId === 2 ? 'leak' : ml.classId === 1 ? 'suspicious' : effTrust !== null && effTrust < this.config.policy.thresholds.normal - this.config.policy.hysteresisDelta ? 'suspicious' : 'normal';
      }

      // 6. detection bookkeeping
      if (this.activeAttack && this.activeAttack.scenario.prefix === rt.prefix) {
        const run = this.activeAttack.run;
        if (run.detectedAt === null && isAnomalous && !noiseInjected) {
          run.detectedAt = this.simTime;
          run.mttd = Math.round((this.simTime - run.injectedAt) * 10) / 10;
          run.detectedClass = ml.classId;
          run.phase = 'detected';
          run.comparison.aiControl = { detected: true, mttd: run.mttd, mitigated: false };
          this.log(
            'warn',
            'detection',
            `Anomaly detected on ${rt.prefix}: ${ml.className} (trust ${effTrust?.toFixed(2) ?? 'n/a'}) — MTTD ${run.mttd}s.`
          );
          // parallel defenses evaluate at detection time
          this.updateComparisonDefenses(run, f);
        }
        if (run.comparison.aiControl.detected && !run.comparison.aiControl.mitigated && run.mitigatedAt !== null) {
          run.comparison.aiControl.mitigated = true;
        }
      }

      // 7. policy decision + shadow validation
      rt.reasons = this.buildReasons(f, ml);
      this.policyStep(rt, ml, effTrust, noiseInjected);
    }

    // RIB verification settle
    this.ribVerifyStep();

    // run timeout
    if (this.activeAttack) {
      const run = this.activeAttack.run;
      if (this.simTime - this.activeAttack.injectedAt > 240 && run.phase !== 'rolledback' && run.phase !== 'failed') {
        run.phase = 'failed';
        this.log('danger', 'metrics', `Run #${run.runId} timed out without full mitigation — recorded as failure.`);
        run.msr = run.mitigatedAt !== null && run.ribVerified;
        this.finalizeRun(run);
        this.activeAttack = null;
      }
    }

    this.updateNodeStatuses();
    this.emit();
  }

  private updateComparisonDefenses(run: RunResult, f: FeatureVector) {
    if (!this.config.comparison.enabled) return;
    const c = run.comparison;
    if (this.config.comparison.standardBgp) {
      c.standardBgp = { detected: false, mttd: null, mitigated: false };
    }
    if (this.config.comparison.rpki && rpkiDetects(f)) {
      c.rpki = { detected: true, mttd: Math.round((this.simTime - run.injectedAt) * 10) / 10 || 2, mitigated: true };
      this.log('info', 'rpki', `RPKI ROV would reject this announcement (invalid origin) at ${c.rpki.mttd}s.`);
    }
    if (this.config.comparison.heuristic && heuristicDetects(f)) {
      const ok = this.rng() < 0.92;
      c.heuristic = { detected: true, mttd: 5, mitigated: ok };
      this.log('info', 'heuristic', `Rule-based detector fires (fixed 5s policy) — ${ok ? 'mitigated' : 'policy application failed'}.`);
    }
  }

  private policyStep(rt: PrefixRuntime, ml: MLResult, trust: number | null, noiseInjected: boolean) {
    const p = this.config.policy;
    if (!p.enabled) {
      rt.policyAction = 'Policy engine disabled (no mitigation)';
      return;
    }
    const target = this.mapTrustToPolicy(trust, ml.classId, rt.route.locPref);
    rt.policyAction = target.action;

    const isNormalTarget = target.lp === p.lpNormal;

    if (isNormalTarget) {
      // clear shadow candidate
      if (rt.shadowEntry) {
        rt.shadowEntry = null;
        this.log('info', 'shadow', `[${rt.prefix}] Streak broken by Normal observation — shadow candidate discarded.`);
      }
      // rollback logic
      if (rt.underOverride && this.config.rollback.enabled) {
        const healthy =
          ml.classId === 0 &&
          (trust === null || trust >= p.thresholds.normal) &&
          rt.features[5] <= 2 &&
          rt.route.active;
        if (healthy) {
          rt.recoveryStreak += 1;
          if (rt.recoveryStreak >= this.config.rollback.requiredNormalTicks) {
            rt.route.locPref = p.lpNormal;
            rt.route.community = null;
            rt.underOverride = false;
            rt.ribVerifiedLp = null;
            rt.status = 'normal';
            this.log('success', 'rollback', `[${rt.prefix}] Autonomous rollback complete — LocalPref restored to ${p.lpNormal} after ${rt.recoveryStreak} sustained healthy ticks.`);
            if (this.activeAttack && this.activeAttack.scenario.prefix === rt.prefix) {
              const run = this.activeAttack.run;
              run.rolledBackAt = this.simTime;
              run.phase = 'rolledback';
              if (run.mitigatedAt !== null) run.msr = run.ribVerified;
              this.finalizeRun(run);
              this.activeAttack = null;
            }
          } else {
            this.log('info', 'rollback', `[${rt.prefix}] Multi-criteria recovery streak ${rt.recoveryStreak}/${this.config.rollback.requiredNormalTicks}.`);
          }
        } else {
          if (rt.recoveryStreak > 0) {
            this.log('warn', 'rollback', `[${rt.prefix}] Network instability observed during recovery — streak reset.`);
          }
          rt.recoveryStreak = 0;
        }
      } else if (rt.route.locPref !== p.lpNormal && !rt.underOverride) {
        // restore default if not under override (e.g. attack withdrawn)
        rt.route.locPref = p.lpNormal;
        rt.route.community = null;
      }
      return;
    }

    // non-normal target: shadow validation
    if (!this.config.shadow.enabled) {
      this.applyPolicy(rt, target.lp, target.community, target.action, 'immediate');
      return;
    }
    const sh = this.config.shadow;
    const now = this.simTime;
    // dwell time
    if (now - rt.lastPolicyChange < sh.minDwellSec && target.lp !== p.lpHijack) {
      if (rt.shadowEntry === null && this.tick % 2 === 0) {
        // log occasionally to show dwell enforcement
        this.log('info', 'shadow', `[${rt.prefix}] Dwell time active (${(now - rt.lastPolicyChange).toFixed(0)}s/${sh.minDwellSec}s) — policy locked.`);
      }
    }
    // immediate quarantine for hijack class
    if (target.lp === p.lpHijack && sh.immediateQuarantine) {
      rt.shadowEntry = null;
      this.applyPolicy(rt, target.lp, target.community, target.action, 'immediate-quarantine');
      return;
    }
    // shadow queue
    if (!rt.shadowEntry) {
      rt.shadowEntry = {
        prefix: rt.prefix,
        targetLocPref: target.lp,
        targetCommunity: target.community,
        candidateClass: ml.classId,
        startTime: now,
        streak: 1,
      };
      if (!noiseInjected) {
        this.log('info', 'shadow', `[${rt.prefix}] Candidate ${target.action} staged in shadow queue (streak 1/${sh.requiredConsecutiveTicks}).`);
      }
      return;
    }
    const entry = rt.shadowEntry;
    if (entry.targetLocPref === target.lp) {
      entry.streak += 1;
      const elapsed = now - entry.startTime;
      if (entry.streak >= sh.requiredConsecutiveTicks && elapsed >= sh.shadowDurationSec) {
        rt.shadowEntry = null;
        this.applyPolicy(rt, target.lp, target.community, target.action, 'shadow-passed');
      } else if (!noiseInjected && this.tick % 2 === 0) {
        this.log('info', 'shadow', `[${rt.prefix}] In shadow validation (streak ${entry.streak}/${sh.requiredConsecutiveTicks}, ${elapsed.toFixed(0)}s/${sh.shadowDurationSec}s).`);
      }
    } else {
      rt.shadowEntry = {
        prefix: rt.prefix,
        targetLocPref: target.lp,
        targetCommunity: target.community,
        candidateClass: ml.classId,
        startTime: now,
        streak: 1,
      };
      this.log('warn', 'shadow', `[${rt.prefix}] Policy tier changed — shadow streak reset.`);
    }
  }

  private applyPolicy(rt: PrefixRuntime, lp: number, community: string | null, action: string, via: string) {
    const p = this.config.policy;
    if (rt.route.locPref === lp && rt.route.community === community) return; // no-op
    rt.route.locPref = lp;
    rt.route.community = community;
    rt.lastPolicyChange = this.simTime;
    if (lp !== p.lpNormal) {
      rt.underOverride = true;
      rt.recoveryStreak = 0;
    }
    if (this.config.ribVerification.enabled) {
      rt.ribPending = {
        lp,
        community,
        dueTick: this.tick + Math.max(1, this.config.ribVerification.latencyTicks),
        attempts: 1,
        prefix: rt.prefix,
      };
      rt.ribVerifiedLp = null;
      this.log('warn', 'policy', `[${rt.prefix}] ${action} applied via ${via} — atomic route-map commit pending RIB verification.`);
    } else {
      rt.ribVerifiedLp = lp;
      this.log('warn', 'policy', `[${rt.prefix}] ${action} applied via ${via} (RIB verification disabled).`);
      this.recordMitigation(rt, lp, community, action, true);
    }
  }

  private ribVerifyStep() {
    for (const rt of this.routes.values()) {
      const pend = rt.ribPending;
      if (!pend) continue;
      if (this.tick < pend.dueTick) continue;
      const ok = this.rng() >= this.config.ribVerification.failureRate;
      const action =
        pend.lp === this.config.policy.lpHijack
          ? `Quarantine (LocalPref ${pend.lp} + ${pend.community ?? 'no-export'})`
          : `Deprioritization (LocalPref ${pend.lp})`;
      if (ok) {
        rt.ribPending = null;
        rt.ribVerifiedLp = pend.lp;
        this.pushRibLog({ t: this.simTime, prefix: rt.prefix, lp: pend.lp, community: pend.community, attempts: pend.attempts, outcome: 'verified', action });
        this.log('success', 'policy', `[${rt.prefix}] RIB best-path verified: LocalPref=${pend.lp}${pend.community ? `, community=${pend.community}` : ''} committed to FIB.`);
        this.recordMitigation(rt, pend.lp, pend.community, action, true);
      } else {
        pend.attempts += 1;
        pend.dueTick = this.tick + 1;
        this.pushRibLog({ t: this.simTime, prefix: rt.prefix, lp: pend.lp, community: pend.community, attempts: pend.attempts, outcome: 'failed', action });
        this.log('danger', 'policy', `[${rt.prefix}] RIB best-path verification FAILED (attempt ${pend.attempts}) — re-applying route-map.`);
      }
    }
  }

  /** append to the structured RIB audit log (bounded) */
  private pushRibLog(e: Omit<RibLogEntry, 'id'>) {
    this.ribLog.push({ id: this.ribLogSeq++, ...e });
    if (this.ribLog.length > 80) this.ribLog.splice(0, this.ribLog.length - 80);
  }

  private recordMitigation(rt: PrefixRuntime, lp: number, community: string | null, action: string, verified: boolean) {
    if (!this.activeAttack || this.activeAttack.scenario.prefix !== rt.prefix) return;
    const run = this.activeAttack.run;
    if (run.mitigatedAt === null && lp !== this.config.policy.lpNormal) {
      run.mitigatedAt = this.simTime;
      run.mttm = Math.round((this.simTime - run.injectedAt) * 10) / 10;
      run.appliedPolicy = action;
      run.appliedLocPref = lp;
      run.phase = 'mitigated';
      run.ribVerified = verified;
      run.comparison.aiControl = { detected: true, mttd: run.mttd ?? 0, mitigated: true };
      this.log('success', 'metrics', `Anomaly mitigated (MTTM) in ${run.mttm}s — ${action}.`);
    }
  }

  private finalizeRun(run: RunResult) {
    this.history.push(run);
    if (this.history.length > 60) this.history.splice(0, this.history.length - 60);
    this.persistRun(run);
  }

  /**
   * Fire-and-forget persistence of a completed run to the Next.js run archive
   * (POST /api/sim-runs on port 3000). Exactly one writer (the engine) — avoids
   * duplicate records when multiple browser clients are attached.
   */
  private persistRun(run: RunResult) {
    const key = `${this.bootId}:${run.runId}:${run.scenarioId}`;
    if (this.persistedRuns.has(key)) return;
    this.persistedRuns.add(key);
    const payload = {
      runId: run.runId,
      scenarioId: run.scenarioId,
      scenarioName: run.scenarioName,
      variantLabel: this.variantLabel,
      mttd: run.mttd,
      mttm: run.mttm,
      msr: run.msr,
      ribVerified: run.ribVerified,
      appliedPolicy: run.appliedPolicy,
      phase: run.phase,
      groundTruth: run.groundTruth,
      detectedClass: run.detectedClass,
      comparison: run.comparison,
      bootId: this.bootId,
    };
    fetch('http://localhost:3000/api/sim-runs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ runs: [payload] }),
    }).catch(() => {
      // archive is best-effort; drop silently (e.g. Next dev recompile window)
      this.persistedRuns.delete(key);
    });
  }

  private updateNodeStatuses() {
    // reset transient defending flags
    for (const n of NODES) {
      const cur = this.nodeStatus.get(n.asn) ?? 'up';
      if (cur === 'defending') this.nodeStatus.set(n.asn, 'up');
    }
    if (this.activeAttack) {
      const rt = this.routes.get(this.activeAttack.scenario.prefix);
      if (rt && rt.underOverride) {
        const defender = this.config.global.defenderAs;
        this.nodeStatus.set(defender, 'defending');
      }
    }
  }

  // ------------------------------------------------------------------ state

  buildState(): SimState {
    const routes: Record<string, RouteSnapshot> = {};
    for (const rt of this.routes.values()) {
      if (rt.dormant && !rt.route.active && !(this.activeAttack && this.activeAttack.scenario.prefix === rt.prefix)) {
        continue; // hide dormant prefixes
      }
      routes[rt.prefix] = {
        route: { ...rt.route },
        features: rt.features,
        ml: rt.ml,
        trust: rt.trust,
        status: rt.status,
        policyAction: rt.policyAction,
        reasons: rt.reasons,
        underOverride: rt.underOverride,
        recoveryStreak: rt.recoveryStreak,
        mitigation: rt.underOverride
          ? { lp: rt.route.locPref, community: rt.route.community }
          : null,
      };
    }

    const nodes: SimNode[] = NODES.map((n) => ({
      ...n,
      status: n.asn === this.config.global.defenderAs && this.nodeStatus.get(n.asn) === 'up' && this.activeAttack && this.routes.get(this.activeAttack.scenario.prefix)?.underOverride
        ? 'defending'
        : this.nodeStatus.get(n.asn) ?? 'up',
      isDefender: n.asn === this.config.global.defenderAs,
    }));

    const edges: SimEdge[] = buildEdges().map((e) => ({ ...e }));
    if (this.activeAttack) {
      const atk = this.activeAttack;
      const tokens = atk.scenario.injectedPath.split(' ').map(Number);
      const withDefender = [this.config.global.defenderAs, ...tokens];
      for (let i = 0; i < withDefender.length - 1; i++) {
        const a = withDefender[i];
        const b = withDefender[i + 1];
        const edge = edges.find(
          (e) => (e.from === a && e.to === b) || (e.from === b && e.to === a)
        );
        if (edge) {
          const rt = this.routes.get(atk.scenario.prefix);
          edge.status = rt?.underOverride && rt.route.locPref === this.config.policy.lpHijack ? 'quarantined' : 'anomalous';
        }
      }
    }

    const completed = this.history;
    const detectedRuns = completed.filter((r) => r.detectedAt !== null);
    const mitigatedRuns = completed.filter((r) => r.msr);
    const metrics = {
      totalRuns: completed.length,
      avgMttd: detectedRuns.length
        ? Math.round((detectedRuns.reduce((s, r) => s + (r.mttd ?? 0), 0) / detectedRuns.length) * 10) / 10
        : null,
      avgMttm: mitigatedRuns.length
        ? Math.round((mitigatedRuns.reduce((s, r) => s + (r.mttm ?? 0), 0) / mitigatedRuns.length) * 10) / 10
        : null,
      msrPercent: completed.length ? Math.round((mitigatedRuns.length / completed.length) * 100) : 0,
      detectionRate: completed.length ? Math.round((detectedRuns.length / completed.length) * 100) : 0,
    };

    return {
      simTime: Math.round(this.simTime * 10) / 10,
      running: this.running,
      tick: this.tick,
      config: clone(this.config),
      variantLabel: this.variantLabel,
      nodes,
      edges,
      routes,
      shadowQueue: Array.from(this.routes.values())
        .filter((r) => r.shadowEntry)
        .map((r) => r.shadowEntry!),
      activeRun: this.activeAttack ? clone(this.activeAttack.run) : null,
      history: clone(this.history.slice(-14)).reverse(),
      trustHistory: this.trustHistory.slice(-360),
      events: this.events.slice(-70),
      ribLog: clone(this.ribLog.slice(-40)).reverse(),
      metrics,
    };
  }

  private emit() {
    this.onChange(this.buildState());
  }

  emitManual() {
    this.emit();
  }
}
