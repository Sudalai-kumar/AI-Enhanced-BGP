import { NextRequest, NextResponse } from 'next/server';
import ZAI from 'z-ai-web-dev-sdk';

export const runtime = 'nodejs';
export const maxDuration = 60;

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

const SYSTEM_PROMPT = `You are the AI Copilot of an "AI-Enhanced BGP Autonomous Control Plane" network operations simulator.

Domain background (you are an expert on this system):
- A 10-AS multi-tier testbed: AS65001/AS65002 (Tier-1), AS65003 (Edge Defender, regional), AS65004-65006 (Regional), AS65007-65009 (Stubs), AS65010 (Rogue attacker).
- Pipeline: Telemetry collector -> 10-feature behavioral extractor -> ML classifier (Random Forest / Logistic Regression, classes: Normal, Suspicious, Route Leak, Prefix Hijack) -> 6-factor Trust Engine (weights: origin 0.20, path 0.20, flap 0.15, prefix 0.15, peer 0.10, ML 0.20) -> Shadow Validator (streak + dwell + hysteresis, immediate quarantine fast-path for hijacks) -> Policy Actor (LocalPref tiers: >=0.85 LP100, 0.55-0.80 LP80, 0.25-0.55 LP50, <0.25 LP0 + no-export community quarantine) -> Two-layer RIB Verification -> Multi-criteria Autonomous Rollback (consecutive normal ticks restore LP100).
- Attack scenarios: S1 direct /24 hijack, S2 sub-prefix /25 hijack, S3 route flapping burst, S4 YouTube-2008 replay (AS17557), S5 Google-2017 route leak (valley-free violation, valid origin), S6 Cloudflare-2019 leak (valid origin AS13335 via AS701).
- Ablation variants: A0 standard BGP (no defense), A1 +heuristics, A2 +ML only, A3 +trust, A4 full system (shadow + rollback).
- Metrics: MTTD (mean time to detect, sim seconds), MTTM (mean time to mitigate), MSR (mitigation success rate), RIB verification pass rate.
- Comparison defenses run in parallel: Standard BGP (blind), RPKI ROV (origin-validity only, blind to sub-prefix hijacks of unregistered space), Heuristics (fixed rules).

Your job:
- Analyze the live simulation state the operator shares with you and answer questions about network posture, detections, mitigations, trust scores, and metrics.
- Give concrete, actionable operational insight: which routes are risky, why a policy tier was chosen, what config changes would improve MTTD/MTTM/MSR, what an ablation comparison implies.
- When metrics are empty or no attack is active, say so plainly and suggest next actions (e.g. run the auto-benchmark sweep, inject S1-S6).
- Use precise BGP terminology (AS-path, LocalPref, valley-free, ROV, RIB/FIB, route-map, communities).
- Be concise and structured: short paragraphs, bullet points, bold key numbers. Use monospace inline for ASNs/prefixes/LP values. Never invent data that is not in the shared state; if something is missing, note it.
- Keep answers under ~250 words unless the operator asks for depth.`;

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const messages: ChatMessage[] = Array.isArray(body?.messages) ? body.messages : [];
    const simContext: string = typeof body?.simContext === 'string' ? body.simContext : '';

    if (messages.length === 0 || messages[messages.length - 1].role !== 'user') {
      return NextResponse.json({ error: 'No user message provided' }, { status: 400 });
    }
    // hard cap conversation length sent to the model
    const trimmed = messages.slice(-14).map((m) => ({
      role: m.role,
      content: String(m.content).slice(0, 6000),
    }));

    const zai = await ZAI.create();
    const completion = await zai.chat.completions.create({
      messages: [
        { role: 'assistant', content: SYSTEM_PROMPT },
        ...(simContext
          ? [{ role: 'assistant', content: `LIVE SIMULATION STATE (machine-generated, authoritative):\n${simContext.slice(0, 8000)}` }]
          : []),
        ...trimmed,
      ],
      thinking: { type: 'disabled' },
    });

    const reply = completion.choices[0]?.message?.content ?? '';
    if (!reply.trim()) {
      return NextResponse.json({ error: 'Empty response from model' }, { status: 502 });
    }
    return NextResponse.json({ reply });
  } catch (e) {
    console.error('[ai-assistant] error:', e);
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}
