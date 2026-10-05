import { SimNode, SimEdge } from './types';

/** Gao-Rexford business relationships (ported from repo src/ai/feature_extractor.py) */
export const AS_RELATIONSHIPS: Record<string, string> = {
  '65001-65002': 'peer-to-peer',
  '65002-65001': 'peer-to-peer',
  '65003-65001': 'customer-to-provider',
  '65001-65003': 'provider-to-customer',
  '65004-65001': 'customer-to-provider',
  '65001-65004': 'provider-to-customer',
  '65005-65002': 'customer-to-provider',
  '65002-65005': 'provider-to-customer',
  '65006-65002': 'customer-to-provider',
  '65002-65006': 'provider-to-customer',
  '65007-65003': 'customer-to-provider',
  '65003-65007': 'provider-to-customer',
  '65008-65003': 'customer-to-provider',
  '65003-65008': 'provider-to-customer',
  '65009-65004': 'customer-to-provider',
  '65004-65009': 'provider-to-customer',
  '65010-65006': 'customer-to-provider',
  '65006-65010': 'provider-to-customer',
  '65003-65002': 'customer-to-provider',
  '65002-65003': 'provider-to-customer',
  '65004-65003': 'peer-to-peer',
  '65003-65004': 'peer-to-peer',
  // Historical incidents
  '15169-12389': 'customer-to-provider',
  '12389-15169': 'provider-to-customer',
  '12389-65002': 'peer-to-peer',
  '65002-12389': 'peer-to-peer',
  '396531-701': 'customer-to-provider',
  '701-396531': 'provider-to-customer',
  '701-65002': 'peer-to-peer',
  '65002-701': 'peer-to-peer',
  '13335-396531': 'peer-to-peer',
  '396531-13335': 'peer-to-peer',
  '36561-65002': 'customer-to-provider',
  '65002-36561': 'provider-to-customer',
  '17557-65002': 'customer-to-provider',
  '65002-17557': 'provider-to-customer',
  '17557-65001': 'customer-to-provider',
  '65001-17557': 'provider-to-customer',
  '36561-65001': 'customer-to-provider',
  '65001-36561': 'provider-to-customer',
  '15169-65001': 'customer-to-provider',
  '65001-15169': 'provider-to-customer',
  '13335-65001': 'customer-to-provider',
  '65001-13335': 'provider-to-customer',
};

/** Per-prefix baseline routes (repo PREFIX_BASELINES + historical incident prefixes) */
export const PREFIX_BASELINES: Record<
  string,
  { originAs: number; asPath: string; maskLen: number; label: string }
> = {
  '192.0.2.0/24': { originAs: 65007, asPath: '65003 65007', maskLen: 24, label: 'Enterprise DC-A' },
  '192.0.2.0/25': { originAs: 65007, asPath: '65003 65007', maskLen: 25, label: 'Enterprise DC-A /25' },
  '198.51.100.0/24': { originAs: 65008, asPath: '65003 65008', maskLen: 24, label: 'Enterprise DC-B' },
  '203.0.113.0/24': { originAs: 65009, asPath: '65001 65004 65009', maskLen: 24, label: 'Cloud Services' },
  '208.65.153.0/24': { originAs: 36561, asPath: '65001 36561', maskLen: 24, label: 'YouTube (historical)' },
  '8.8.8.0/24': { originAs: 15169, asPath: '65001 15169', maskLen: 24, label: 'Google DNS (historical)' },
  '104.16.0.0/16': { originAs: 13335, asPath: '65001 13335', maskLen: 16, label: 'Cloudflare (historical)' },
};

export const NODES: SimNode[] = [
  { asn: 65001, label: 'AS65001', role: 'tier1', tier: 'Tier-1 Backbone', x: 300, y: 70, status: 'up', isDefender: true },
  { asn: 65002, label: 'AS65002', role: 'tier1', tier: 'Tier-1 Transit', x: 640, y: 70, status: 'up', isDefender: false },
  { asn: 65003, label: 'AS65003', role: 'regional', tier: 'Regional Hub', x: 130, y: 225, status: 'up', isDefender: true },
  { asn: 65004, label: 'AS65004', role: 'regional', tier: 'Regional Hub', x: 420, y: 225, status: 'up', isDefender: false },
  { asn: 65005, label: 'AS65005', tier: 'Regional Hub', role: 'regional', x: 720, y: 225, status: 'up', isDefender: false },
  { asn: 65006, label: 'AS65006', role: 'regional', tier: 'Transit Provider', x: 910, y: 225, status: 'up', isDefender: false },
  { asn: 65007, label: 'AS65007', role: 'stub', tier: 'Origin Stub', x: 60, y: 380, status: 'up', isDefender: false },
  { asn: 65008, label: 'AS65008', role: 'stub', tier: 'Multi-Homed Stub', x: 260, y: 380, status: 'up', isDefender: false },
  { asn: 65009, label: 'AS65009', role: 'stub', tier: 'Customer Stub', x: 500, y: 380, status: 'up', isDefender: false },
  { asn: 65010, label: 'AS65010', role: 'rogue', tier: 'Rogue Adversary', x: 1020, y: 380, status: 'up', isDefender: false },
];

const EDGE_DEFS: [number, number, SimEdge['rel']][] = [
  [65001, 65002, 'peer-to-peer'],
  [65003, 65001, 'customer-to-provider'],
  [65004, 65001, 'customer-to-provider'],
  [65005, 65002, 'customer-to-provider'],
  [65006, 65002, 'customer-to-provider'],
  [65007, 65003, 'customer-to-provider'],
  [65008, 65003, 'customer-to-provider'],
  [65009, 65004, 'customer-to-provider'],
  [65010, 65006, 'customer-to-provider'],
  [65003, 65002, 'customer-to-provider'],
  [65003, 65004, 'peer-to-peer'],
];

export function buildEdges(): SimEdge[] {
  return EDGE_DEFS.map(([from, to, rel]) => ({ from, to, rel, status: 'normal' }));
}

/** Valley-free check (ported from repo check_valley_free_violation) */
export function checkValleyFreeViolation(asPathStr: string): number {
  const tokens = asPathStr
    .split(' ')
    .filter((x) => x.trim() !== '' && /^\d+$/.test(x))
    .map(Number);
  if (tokens.length <= 1) return 0;
  if (new Set(tokens).size < tokens.length) return 1; // AS loop
  let state: 'UPWARD' | 'PEER' | 'DOWNWARD' = 'UPWARD';
  for (let i = 0; i < tokens.length - 1; i++) {
    const rel = AS_RELATIONSHIPS[`${tokens[i]}-${tokens[i + 1]}`] ?? 'unknown';
    if (rel === 'customer-to-provider') {
      if (state === 'PEER' || state === 'DOWNWARD') return 1;
      state = 'UPWARD';
    } else if (rel === 'peer-to-peer') {
      if (state === 'PEER' || state === 'DOWNWARD') return 1;
      state = 'PEER';
    } else if (rel === 'provider-to-customer') {
      state = 'DOWNWARD';
    } else {
      if (tokens.length >= 4 && i >= 2) return 1;
    }
  }
  return 0;
}

export function levenshtein(a: string[], b: string[]): number {
  const m = a.length;
  const n = b.length;
  const dp: number[][] = Array.from({ length: m + 1 }, () => new Array(n + 1).fill(0));
  for (let i = 0; i <= m; i++) dp[i][0] = i;
  for (let j = 0; j <= n; j++) dp[0][j] = j;
  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      if (a[i - 1] === b[j - 1]) dp[i][j] = dp[i - 1][j - 1];
      else dp[i][j] = 1 + Math.min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1]);
    }
  }
  return dp[m][n];
}
