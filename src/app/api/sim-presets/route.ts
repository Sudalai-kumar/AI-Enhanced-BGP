import { NextRequest, NextResponse } from 'next/server';
import { db } from '@/lib/db';
import { Prisma } from '@prisma/client';

export async function GET() {
  try {
    const presets = await db.simConfigPreset.findMany({
      orderBy: { updatedAt: 'desc' },
      take: 50,
    });
    return NextResponse.json({
      presets: presets.map((p) => ({
        id: p.id,
        name: p.name,
        variant: p.variant,
        config: JSON.parse(p.config),
        updatedAt: p.updatedAt,
      })),
    });
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const name = String(body?.name ?? '').trim();
    if (!name) {
      return NextResponse.json({ error: 'Preset name is required' }, { status: 400 });
    }
    if (typeof body?.config !== 'object' || body.config === null) {
      return NextResponse.json({ error: 'config object is required' }, { status: 400 });
    }
    const preset = await db.simConfigPreset.upsert({
      where: { name },
      update: {
        config: JSON.stringify(body.config),
        variant: body?.variant ? String(body.variant) : 'custom',
      },
      create: {
        name,
        variant: body?.variant ? String(body.variant) : 'custom',
        config: JSON.stringify(body.config),
      },
    });
    return NextResponse.json({ ok: true, id: preset.id, name: preset.name });
  } catch (e) {
    if (e instanceof Prisma.PrismaClientKnownRequestError) {
      return NextResponse.json({ error: e.message }, { status: 400 });
    }
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}

export async function DELETE(req: NextRequest) {
  try {
    const id = req.nextUrl.searchParams.get('id');
    if (!id) {
      return NextResponse.json({ error: 'id query param required' }, { status: 400 });
    }
    await db.simConfigPreset.delete({ where: { id } });
    return NextResponse.json({ ok: true });
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}
