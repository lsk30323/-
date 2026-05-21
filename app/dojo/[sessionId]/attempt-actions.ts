'use server';

import { and, eq } from 'drizzle-orm';
import { revalidatePath } from 'next/cache';
import { db } from '@/db';
import { attempts, sessions } from '@/db/schema';

export type SaveCodeResult =
  | { ok: true }
  | {
      ok: false;
      error: 'session_not_found' | 'no_problem_yet' | 'persist_failed';
    };

/**
 * 진행 중(in-progress) attempt의 code 컬럼을 갱신.
 *
 * - 첫 호출: hint-actions와 동일한 upsert 패턴으로 attempt 행 생성.
 * - 이후 호출: 기존 in-progress attempt의 code만 업데이트.
 * - hintsViewed는 건드리지 않음 (별도 액션 recordHintView가 관리).
 * - revalidatePath는 호출하지 않음 — 12초마다 autosave가 일어나는데 매번
 *   페이지 캐시를 무효화하면 트래픽·렌더 부하가 큼. 사용자는 페이지에 머무는
 *   동안이므로 클라이언트 state가 truth source.
 */
export async function saveAttemptCode(
  sessionId: number,
  code: string,
): Promise<SaveCodeResult> {
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
      await db
        .update(attempts)
        .set({ code })
        .where(eq(attempts.id, existing.id));
    } else {
      await db.insert(attempts).values({
        problemId: session.problemId,
        sessionId,
        code,
        timeTakenSeconds: 0,
        hintsViewed: [],
        completed: false,
      });
    }
    return { ok: true };
  } catch (err) {
    console.error('[saveAttemptCode] DB error:', err);
    return { ok: false, error: 'persist_failed' };
  }
}

export type FinalizeResult =
  | { ok: true; attemptId: number }
  | {
      ok: false;
      error: 'session_not_found' | 'no_problem_yet' | 'already_finalized' | 'persist_failed';
    };

/**
 * 사용자 명시 제출 또는 타이머 만료 시 attempt를 봉인.
 *
 * - completed=true + code/timeTakenSeconds 확정.
 * - sessions.endedAt 도 함께 기록 (세션이 끝난 시각).
 * - revalidatePath로 페이지 재렌더 — Slice 11의 리뷰 화면 분기로 전환.
 * - 이미 완료된 attempt가 있으면 already_finalized 에러 (중복 제출 방지).
 */
export async function finalizeAttempt(
  sessionId: number,
  code: string,
  timeTakenSeconds: number,
): Promise<FinalizeResult> {
  const [session] = await db
    .select()
    .from(sessions)
    .where(eq(sessions.id, sessionId))
    .limit(1);
  if (!session) return { ok: false, error: 'session_not_found' };
  if (session.problemId === null) return { ok: false, error: 'no_problem_yet' };

  try {
    const [completedAlready] = await db
      .select()
      .from(attempts)
      .where(and(eq(attempts.sessionId, sessionId), eq(attempts.completed, true)))
      .limit(1);
    if (completedAlready) {
      return { ok: false, error: 'already_finalized' };
    }

    const [inProgress] = await db
      .select()
      .from(attempts)
      .where(and(eq(attempts.sessionId, sessionId), eq(attempts.completed, false)))
      .limit(1);

    let attemptId: number;
    if (inProgress) {
      const [updated] = await db
        .update(attempts)
        .set({ code, timeTakenSeconds, completed: true })
        .where(eq(attempts.id, inProgress.id))
        .returning();
      if (!updated) return { ok: false, error: 'persist_failed' };
      attemptId = updated.id;
    } else {
      const [inserted] = await db
        .insert(attempts)
        .values({
          problemId: session.problemId,
          sessionId,
          code,
          timeTakenSeconds,
          hintsViewed: [],
          completed: true,
        })
        .returning();
      if (!inserted) return { ok: false, error: 'persist_failed' };
      attemptId = inserted.id;
    }

    await db
      .update(sessions)
      .set({ endedAt: new Date() })
      .where(eq(sessions.id, sessionId));

    revalidatePath(`/dojo/${sessionId}`);
    return { ok: true, attemptId };
  } catch (err) {
    console.error('[finalizeAttempt] DB error:', err);
    return { ok: false, error: 'persist_failed' };
  }
}
