import { NextRequest, NextResponse } from 'next/server';
import { db } from '@/lib/db';

export async function GET() {
  try {
    const runs = await db.simRunRecord.findMany({
      orderBy: { createdAt: 'desc' },
      take: 100,
    });
    return NextResponse.json({
      runs: runs.map((r) => ({ ...r, comparison: JSON.parse(r.comparison) })),
    });
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const runs = Array.isArray(body?.runs) ? body.runs : [body];
    const created = [];
    for (const r of runs) {
      if (typeof r?.scenarioId !== 'string') continue;
      created.push(
        await db.simRunRecord.create({
          data: {
            runId: Number(r.runId ?? 0),
            scenarioId: String(r.scenarioId),
            scenarioName: String(r.scenarioName ?? ''),
            variantLabel: r.variantLabel ? String(r.variantLabel) : null,
            mttd: r.mttd !== null && r.mttd !== undefined ? Number(r.mttd) : null,
            mttm: r.mttm !== null && r.mttm !== undefined ? Number(r.mttm) : null,
            msr: Boolean(r.msr),
            ribVerified: Boolean(r.ribVerified),
            appliedPolicy: String(r.appliedPolicy ?? ''),
            phase: String(r.phase ?? 'injected'),
            groundTruth: Number(r.groundTruth ?? 0),
            detectedClass: r.detectedClass !== null && r.detectedClass !== undefined ? Number(r.detectedClass) : null,
            comparison: JSON.stringify(r.comparison ?? {}),
          },
        })
      );
    }
    return NextResponse.json({ ok: true, count: created.length });
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}
