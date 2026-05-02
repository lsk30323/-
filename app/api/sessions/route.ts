import { db } from '@/db';
import { sessions } from '@/db/schema';
import { createSessionBody } from '@/lib/validation';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function POST(req: Request) {
  let raw: unknown;
  try {
    raw = await req.json();
  } catch {
    return Response.json({ error: 'invalid_json' }, { status: 400 });
  }
  const parsed = createSessionBody.safeParse(raw);
  if (!parsed.success) {
    return Response.json(
      { error: 'invalid_body', issues: parsed.error.issues },
      { status: 400 },
    );
  }
  const { mode, topic, difficulty, timeLimitMinutes } = parsed.data;

  try {
    const [row] = await db
      .insert(sessions)
      .values({
        mode,
        topic: topic ?? null,
        difficulty: difficulty ?? null,
        timeLimitMinutes: mode === 'interview' ? (timeLimitMinutes ?? null) : null,
      })
      .returning();

    if (!row) {
      return Response.json({ error: 'insert_failed' }, { status: 500 });
    }

    return Response.json(
      {
        sessionId: row.id,
        session: row,
      },
      { status: 201 },
    );
  } catch (err) {
    console.error('[/api/sessions] insert error:', err);
    return Response.json({ error: 'internal' }, { status: 500 });
  }
}
