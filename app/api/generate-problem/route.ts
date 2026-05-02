import { APIError, RateLimitError } from '@anthropic-ai/sdk';
import { anthropic, isAnthropicConfigured } from '@/lib/anthropic';
import { modelForDifficulty } from '@/lib/models';
import { getPromptFor } from '@/lib/prompts';
import {
  emitProblemTool,
  emittedProblem,
  generateProblemBody,
} from '@/lib/validation';

export const runtime = 'nodejs';
export const maxDuration = 60;
export const dynamic = 'force-dynamic';

const MAX_TOKENS = 4096;

export async function POST(req: Request) {
  /* 1. 바디 검증 */
  let raw: unknown;
  try {
    raw = await req.json();
  } catch {
    return Response.json({ error: 'invalid_json' }, { status: 400 });
  }
  const parsed = generateProblemBody.safeParse(raw);
  if (!parsed.success) {
    return Response.json(
      { error: 'invalid_body', issues: parsed.error.issues },
      { status: 400 },
    );
  }
  const { topic, difficulty, mode } = parsed.data;

  /* 2. 스트리밍은 후속 슬라이스 — 지금은 json만 */
  if (mode === 'stream') {
    return Response.json(
      { error: 'stream_mode_not_implemented_yet' },
      { status: 501 },
    );
  }

  /* 3. 키 미설정 → 503 + 한국어 메시지 (graceful) */
  if (!isAnthropicConfigured()) {
    return Response.json(
      {
        error: 'anthropic_unconfigured',
        message:
          'ANTHROPIC_API_KEY가 설정되지 않았습니다. .env.local 또는 배포 환경 변수에 키를 추가하세요.',
      },
      { status: 503 },
    );
  }

  /* 4. 프롬프트 합성 + 모델 선택 */
  const { system, user } = getPromptFor(topic, difficulty);
  const model = modelForDifficulty(difficulty);

  /* 5. Anthropic Tool Use forcing 호출 */
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

    const toolUse = msg.content.find((b) => b.type === 'tool_use');
    if (!toolUse || toolUse.type !== 'tool_use' || toolUse.name !== emitProblemTool.name) {
      return Response.json(
        { error: 'no_tool_use', stop_reason: msg.stop_reason },
        { status: 502 },
      );
    }

    /* 6. 모델 출력 zod 검증 (defensive) */
    const validated = emittedProblem.safeParse(toolUse.input);
    if (!validated.success) {
      return Response.json(
        {
          error: 'invalid_tool_output',
          issues: validated.error.issues,
        },
        { status: 502 },
      );
    }

    return Response.json({
      problem: validated.data,
      meta: {
        topic,
        difficulty,
        model,
        usage: msg.usage,
      },
    });
  } catch (err) {
    return handleError(err);
  }
}

function handleError(err: unknown): Response {
  if (err instanceof RateLimitError) {
    return Response.json({ error: 'rate_limit' }, { status: 429 });
  }
  if (err instanceof APIError) {
    return Response.json(
      { error: 'api_error', message: err.message, type: err.name },
      { status: err.status ?? 500 },
    );
  }
  console.error('[generate-problem] unexpected error:', err);
  return Response.json({ error: 'internal' }, { status: 500 });
}
