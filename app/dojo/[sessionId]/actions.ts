'use server';

import { eq } from 'drizzle-orm';
import { revalidatePath } from 'next/cache';
import { db } from '@/db';
import { problems, sessions } from '@/db/schema';
import { anthropic, isAnthropicConfigured } from '@/lib/anthropic';
import { modelForDifficulty } from '@/lib/models';
import { getPromptFor } from '@/lib/prompts';
import { emitProblemTool, emittedProblem } from '@/lib/validation';

const MAX_TOKENS = 4096;

/** 직렬화 가능한 union — client component가 그대로 받아 분기 */
export type GenerateResult =
  | { ok: true }
  | {
      ok: false;
      error:
        | 'session_not_found'
        | 'session_incomplete'
        | 'anthropic_unconfigured'
        | 'no_tool_use'
        | 'invalid_tool_output'
        | 'insert_failed'
        | 'generation_failed';
    };

/**
 * /dojo/[sessionId]에서 호출되는 서버 액션.
 *
 * 1) 세션 조회·검증
 * 2) 이미 problemId가 붙어 있으면 즉시 ok (멱등성)
 * 3) Anthropic Tool Use forcing으로 문제 생성
 * 4) problems 테이블에 insert + sessions.problemId update
 * 5) revalidatePath → 페이지가 새 데이터로 재렌더
 *
 * 라우트 핸들러 /api/generate-problem과 코드가 다소 중복되지만, server action에서
 * 자기 호스트로 fetch하는 것은 불필요한 HTTP 왕복이라 의도적으로 직접 SDK를 호출.
 */
export async function generateProblemForSession(sessionId: number): Promise<GenerateResult> {
  /* 1. 세션 조회 */
  const found = await db.select().from(sessions).where(eq(sessions.id, sessionId)).limit(1);
  const session = found[0];
  if (!session) return { ok: false, error: 'session_not_found' };
  if (!session.topic || !session.difficulty) {
    return { ok: false, error: 'session_incomplete' };
  }

  /* 2. 이미 생성됨 → 멱등 */
  if (session.problemId) return { ok: true };

  if (!isAnthropicConfigured()) {
    return { ok: false, error: 'anthropic_unconfigured' };
  }

  /* 3. Anthropic 호출 */
  const { system, user } = getPromptFor(session.topic, session.difficulty);
  const model = modelForDifficulty(session.difficulty);

  let toolInput: unknown;
  try {
    const msg = await anthropic.messages.create({
      model,
      max_tokens: MAX_TOKENS,
      system,
      tools: [emitProblemTool],
      tool_choice: {
        type: 'tool',
        name: emitProblemTool.name,
        disable_parallel_tool_use: true,
      },
      messages: [{ role: 'user', content: user }],
    });
    const tu = msg.content.find((b) => b.type === 'tool_use');
    if (!tu || tu.type !== 'tool_use' || tu.name !== emitProblemTool.name) {
      return { ok: false, error: 'no_tool_use' };
    }
    toolInput = tu.input;
  } catch (err) {
    console.error('[generateProblemForSession] anthropic error:', err);
    return { ok: false, error: 'generation_failed' };
  }

  /* 4. zod 검증 + DB 저장 */
  const validated = emittedProblem.safeParse(toolInput);
  if (!validated.success) {
    console.error('[generateProblemForSession] invalid tool output:', validated.error.issues);
    return { ok: false, error: 'invalid_tool_output' };
  }
  const p = validated.data;

  try {
    const [inserted] = await db
      .insert(problems)
      .values({
        topic: p.topic,
        difficulty: p.difficulty,
        title: p.title,
        description: p.description,
        hints: p.hints,
        referenceSolution: p.reference_solution,
        tags: p.tags,
      })
      .returning();
    if (!inserted) return { ok: false, error: 'insert_failed' };

    await db
      .update(sessions)
      .set({ problemId: inserted.id })
      .where(eq(sessions.id, sessionId));
  } catch (err) {
    console.error('[generateProblemForSession] DB insert/update error:', err);
    return { ok: false, error: 'insert_failed' };
  }

  /* 5. 페이지 캐시 무효화 → 다음 GET이 새 problem을 읽음 */
  revalidatePath(`/dojo/${sessionId}`);
  return { ok: true };
}
