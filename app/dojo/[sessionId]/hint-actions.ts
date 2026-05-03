'use server';

import { and, eq } from 'drizzle-orm';
import { revalidatePath } from 'next/cache';
import { db } from '@/db';
import { attempts, sessions } from '@/db/schema';

export type HintStageNumber = 1 | 2 | 3 | 4;

export type RecordHintResult =
  | { ok: true; hintsViewed: number[] }
  | {
      ok: false;
      error:
        | 'session_not_found'
        | 'no_problem_yet'
        | 'invalid_stage'
        | 'persist_failed';
    };

/**
 * 사용자가 힌트 N단계를 reveal한 사실을 영속화.
 *
 * 모델: 세션 1개당 in-progress(=completed=false) attempt 행 1개를 유지.
 * - 첫 reveal: 빈 code/0 timeTaken 으로 attempt insert (hintsViewed=[stage])
 * - 이후 reveal: 해당 attempt의 hintsViewed JSON 배열에 stage 추가 (set 처리, 정렬)
 *
 * Slice 11에서 "제출"이 일어나면 같은 attempt 행을 update하여 code/timeTakenSeconds
 * 채우고 completed=true로 마무리합니다.
 */
export async function recordHintView(
  sessionId: number,
  stage: HintStageNumber,
): Promise<RecordHintResult> {
  if (![1, 2, 3, 4].includes(stage)) {
    return { ok: false, error: 'invalid_stage' };
  }

  const [session] = await db
    .select()
    .from(sessions)
    .where(eq(sessions.id, sessionId))
    .limit(1);
  if (!session) return { ok: false, error: 'session_not_found' };
  if (session.problemId === null) return { ok: false, error: 'no_problem_yet' };

  try {
    const [existing] = await db
      .select()
      .from(attempts)
      .where(and(eq(attempts.sessionId, sessionId), eq(attempts.completed, false)))
      .limit(1);

    if (existing) {
      const merged = Array.from(new Set([...existing.hintsViewed, stage])).sort(
        (a, b) => a - b,
      );
      const [updated] = await db
        .update(attempts)
        .set({ hintsViewed: merged })
        .where(eq(attempts.id, existing.id))
        .returning();
      revalidatePath(`/dojo/${sessionId}`);
      return { ok: true, hintsViewed: updated?.hintsViewed ?? merged };
    }

    const [inserted] = await db
      .insert(attempts)
      .values({
        problemId: session.problemId,
        sessionId,
        code: '',
        timeTakenSeconds: 0,
        hintsViewed: [stage],
        completed: false,
      })
      .returning();
    if (!inserted) return { ok: false, error: 'persist_failed' };

    revalidatePath(`/dojo/${sessionId}`);
    return { ok: true, hintsViewed: inserted.hintsViewed };
  } catch (err) {
    console.error('[recordHintView] DB error:', err);
    return { ok: false, error: 'persist_failed' };
  }
}
