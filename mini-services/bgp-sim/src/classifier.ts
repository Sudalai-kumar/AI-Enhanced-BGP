import { ClassId, MLResult, SimConfig } from './types';

/**
 * Simulated ML classifiers mirroring the repo's trained models:
 * - Random Forest: calibrated, 85.06% accuracy, decisive tree-vote behavior
 * - Logistic Regression: 79.31% accuracy, smoother linear behavior, faster but weaker
 *
 * Both map the 10-feature behavioral vector to 4-class probabilities
 * [Normal, Suspicious, Route Leak, Prefix Hijack].
 */

function softmax(scores: number[], temperature = 1): number[] {
  const t = Math.max(0.05, temperature);
  const max = Math.max(...scores);
  const exps = scores.map((s) => Math.exp((s - max) / t));
  const sum = exps.reduce((a, b) => a + b, 0) || 1;
  return exps.map((e) => e / sum);
}

function sigmoid(x: number): number {
  return 1 / (1 + Math.exp(-x));
}

/** Hard step (tree split behavior) for RF; k controls steepness */
function treeVote(x: number, threshold: number, k = 12): number {
  return sigmoid((x - threshold) * k);
}

function normalize(f: number[]) {
  return {
    editNorm: Math.min(1, f[1] / 4),
    flapNorm: Math.min(1, f[5] / 6),
    announceNorm: Math.min(1, f[4] / 12),
    ageNorm: Math.min(1, f[7] / 60),
    pathLenNorm: Math.min(1, Math.max(0, f[0] - 3) / 3),
  };
}

export function classifyRandomForest(f: number[], sensitivity: number): MLResult {
  const [
    asPathLen,
    asPathEditDistance,
    originAsChange,
    prefixMaskLen,
    ,
    flapCount5min,
    ,
    ,
    valleyFree,
    neighborDiversity,
  ] = f;
  const { editNorm, flapNorm, announceNorm, ageNorm, pathLenNorm } = normalize(f);

  const s = Math.max(0.25, Math.min(3, sensitivity));

  // tree-ensemble votes (hard thresholds with margin)
  const originFlag = treeVote(originAsChange, 0.5);
  const subPrefixFlag = treeVote(prefixMaskLen, 24.4);
  const valleyFlag = treeVote(valleyFree, 0.5);
  const flapFlag = treeVote(flapCount5min, 2.6);
  const announceFlag = treeVote(f[4], 6);
  const peerWithdraw = treeVote(1 - neighborDiversity, 0.55);

  // class evidence scores in ~[0, 1.1]
  const hijackScore =
    originFlag * (0.75 + 0.2 * subPrefixFlag + 0.05 * editNorm) + 0.05 * peerWithdraw;
  const leakScore =
    valleyFlag * (0.7 + 0.15 * editNorm + 0.15 * pathLenNorm) + 0.08 * editNorm * (1 - valleyFlag);
  const flapScore = 0.6 * flapFlag + 0.4 * announceFlag;
  const suspScore =
    0.5 * Math.max(announceFlag, flapFlag * 0.8, (1 - ageNorm) * 0.4, editNorm * 0.5) +
    0.5 * (0.35 * announceNorm + 0.25 * flapNorm + 0.2 * (1 - ageNorm)) * 0.85;

  const h = hijackScore * s;
  const l = leakScore * s;
  const fp = flapScore * s;
  const su = suspScore * s;
  const totalEvidence = Math.max(h, l, fp, su);
  const normalScore = totalEvidence < 0.3 ? 1.8 : Math.max(0.05, 1.2 - 1.0 * totalEvidence);

  const probs = softmax([normalScore, su, l, h], 0.55);
  return buildResult('random_forest', probs, asPathLen, asPathEditDistance);
}

export function classifyLogisticRegression(f: number[], sensitivity: number): MLResult {
  const { editNorm, flapNorm, announceNorm, ageNorm, pathLenNorm } = normalize(f);
  const s = Math.max(0.25, Math.min(3, sensitivity));

  const zHijack = (2.2 * f[2] + 0.5 * (f[3] > 24 ? 1 : 0) + 0.35 * editNorm - 1.3) * s;
  const zLeak = (1.8 * f[8] + 0.4 * editNorm + 0.3 * pathLenNorm - 1.0) * s;
  const zFlap = (0.7 * flapNorm + 0.5 * announceNorm - 0.8) * s;
  const zSusp = (0.4 * announceNorm + 0.3 * flapNorm + 0.2 * (1 - ageNorm) - 0.6) * s;
  const zNormal = Math.max(-1, 1.0 - 0.8 * Math.max(zHijack, zLeak, zFlap));

  const probs = softmax([zNormal, zSusp, zLeak, zHijack], 0.8);
  return buildResult('logistic_regression', probs, f[0], f[1]);
}

function buildResult(model: string, probs: number[], pathLen: number, editDist: number): MLResult {
  // tiny live jitter so probabilities breathe between ticks
  const jitter = (i: number) => (i === 0 ? 1 : 0) * (Math.random() - 0.5) * 0.02;
  const adjusted = probs.map((p, i) => Math.max(0, p + jitter(i)));
  const sum = adjusted.reduce((a, b) => a + b, 0) || 1;
  const final = adjusted.map((p) => Math.round((p / sum) * 1000) / 1000);

  let classId: ClassId = 0;
  let maxP = -1;
  final.forEach((p, i) => {
    if (p > maxP) {
      maxP = p;
      classId = i as ClassId;
    }
  });
  const names = ['Normal', 'Suspicious', 'Route Leak', 'Prefix Hijack'];
  return {
    classId,
    className: names[classId],
    confidence: maxP,
    probabilities: final,
    model,
  };
}

/** Heuristic detector (comparison defense): deterministic rules, ~5s, 92% success */
export function heuristicDetects(f: number[]): boolean {
  const originChanged = f[2] > 0.5;
  const valley = f[8] > 0.5;
  const subPrefix = f[3] > 24;
  const flapping = f[5] >= 3 || f[4] >= 6;
  return originChanged || valley || subPrefix || flapping;
}

/** RPKI ROV (comparison defense): catches invalid-origin EXACT-prefix announcements (S1, S4); blind to sub-prefix deaggregation, flapping, leaks */
export function rpkiDetects(f: number[]): boolean {
  return f[2] > 0.5 && f[3] <= 24; // origin changed AND not more-specific than /24
}

export function classify(f: number[], config: SimConfig): MLResult {
  const { model, sensitivity } = config.ml;
  if (model === 'logistic_regression') return classifyLogisticRegression(f, sensitivity);
  return classifyRandomForest(f, sensitivity);
}
