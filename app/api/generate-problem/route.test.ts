import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { APIError, RateLimitError } from '@anthropic-ai/sdk';

/* vi.hoisted로 mock factory 안에서 접근 가능한 spy를 끌어올립니다. */
const mocks = vi.hoisted(() => ({
  create: vi.fn(),
  isConfigured: vi.fn(() => true),
}));

vi.mock('@/lib/anthropic', () => ({
  anthropic: { messages: { create: mocks.create } },
  isAnthropicConfigured: mocks.isConfigured,
}));

vi.mock('server-only', () => ({}));

const { POST } = await import('./route');

const validProblem = {
  title: '걸음 수 시계열 집계기',
  description: '사용자의 걸음 수 흐름을 받아 일별 합계 StateFlow를 노출하는 ViewModel을 작성하세요.',
  difficulty: '중급',
  topic: 'coroutines-stateflow',
  hints: [
    {
      stage: 1,
      kind: 'decision',
      question: '메인 스레드에서 collect해도 되는가? (예/아니오)',
      options: ['예', '아니오'],
      rationale: '아니오 — collect는 lifecycle aware 방식으로 viewModelScope에서 수행해야 합니다.',
    },
    {
      stage: 2,
      kind: 'tradeoff',
      question: 'Flow vs StateFlow를 lifecycle, replay, 결합도 측면에서 비교하라.',
      rationale: 'StateFlow는 hot, 항상 최신 값 보유하나 변경 감지에 distinctUntilChanged 내장.',
    },
    {
      stage: 3,
      kind: 'comprehension',
      question: '왜 SharingStarted.WhileSubscribed(5_000)인가?',
      rationale: '회전 사이 캐시 유지 — 5초는 일반적인 leeway.',
    },
    {
      stage: 4,
      kind: 'extension',
      question: 'collectAsStateWithLifecycle은 어떤 문제를 해결하나?',
      rationale:
        'lifecycle-aware collection. 백그라운드에서 collect를 일시 정지해 누수와 불필요 작업을 방지합니다.',
    },
  ],
  reference_solution: {
    language: 'kotlin',
    code: 'class StepVM(...) { val daily: StateFlow<Long> = ... }',
    explanation: '걸음 시계열을 scan으로 누적 후 stateIn으로 hot 변환.',
    complexity: { time: 'O(n)', space: 'O(1)' },
  },
  tags: ['stateflow', 'lifecycle'],
};

function makeToolUseResponse(input: unknown) {
  return {
    id: 'msg_test',
    type: 'message',
    role: 'assistant',
    model: 'claude-sonnet-4-6',
    stop_reason: 'tool_use',
    stop_sequence: null,
    content: [
      {
        type: 'tool_use',
        id: 'toolu_test',
        name: 'emit_problem',
        input,
      },
    ],
    usage: { input_tokens: 100, output_tokens: 200 },
  };
}

function makeRequest(body: unknown): Request {
  return new Request('http://localhost/api/generate-problem', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: typeof body === 'string' ? body : JSON.stringify(body),
  });
}

beforeEach(() => {
  mocks.create.mockReset();
  mocks.isConfigured.mockReset();
  mocks.isConfigured.mockReturnValue(true);
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('POST /api/generate-problem (json mode)', () => {
  it('400 on invalid JSON body', async () => {
    const res = await POST(makeRequest('not json{'));
    expect(res.status).toBe(400);
    const json = await res.json();
    expect(json.error).toBe('invalid_json');
  });

  it('400 on missing required fields', async () => {
    const res = await POST(makeRequest({ topic: 'coroutines-stateflow' }));
    expect(res.status).toBe(400);
    const json = await res.json();
    expect(json.error).toBe('invalid_body');
  });

  it('400 on unknown topic', async () => {
    const res = await POST(
      makeRequest({ topic: 'unknown-topic', difficulty: '중급', mode: 'json' }),
    );
    expect(res.status).toBe(400);
  });

  it('501 on stream mode (deferred to later slice)', async () => {
    const res = await POST(
      makeRequest({ topic: 'room-db', difficulty: '입문', mode: 'stream' }),
    );
    expect(res.status).toBe(501);
  });

  it('503 when ANTHROPIC_API_KEY is unset', async () => {
    mocks.isConfigured.mockReturnValue(false);
    const res = await POST(makeRequest({ topic: 'jwt-auth', difficulty: '중급' }));
    expect(res.status).toBe(503);
    const json = await res.json();
    expect(json.error).toBe('anthropic_unconfigured');
    expect(json.message).toContain('ANTHROPIC_API_KEY');
    expect(mocks.create).not.toHaveBeenCalled();
  });

  it('200 returns validated problem on successful tool_use', async () => {
    mocks.create.mockResolvedValue(makeToolUseResponse(validProblem));
    const res = await POST(
      makeRequest({ topic: 'coroutines-stateflow', difficulty: '중급', mode: 'json' }),
    );
    expect(res.status).toBe(200);
    const json = await res.json();
    expect(json.problem.title).toBe('걸음 수 시계열 집계기');
    expect(json.problem.hints).toHaveLength(4);
    expect(json.meta.model).toBe('claude-sonnet-4-6');
    expect(json.meta.topic).toBe('coroutines-stateflow');
  });

  it('routes 면접급 to Opus', async () => {
    mocks.create.mockResolvedValue(
      makeToolUseResponse({ ...validProblem, difficulty: '면접급' }),
    );
    const res = await POST(
      makeRequest({ topic: 'coroutines-stateflow', difficulty: '면접급', mode: 'json' }),
    );
    expect(res.status).toBe(200);
    expect(mocks.create).toHaveBeenCalledOnce();
    const callArg = mocks.create.mock.calls[0]![0];
    expect(callArg.model).toBe('claude-opus-4-7');
  });

  it('routes 중급 to Sonnet', async () => {
    mocks.create.mockResolvedValue(makeToolUseResponse(validProblem));
    await POST(makeRequest({ topic: 'room-db', difficulty: '중급', mode: 'json' }));
    expect(mocks.create.mock.calls[0]![0].model).toBe('claude-sonnet-4-6');
  });

  it('forces emit_problem tool with disable_parallel_tool_use', async () => {
    mocks.create.mockResolvedValue(makeToolUseResponse(validProblem));
    await POST(makeRequest({ topic: 'jetpack-compose', difficulty: '입문' }));
    const call = mocks.create.mock.calls[0]![0];
    expect(call.tool_choice).toEqual({
      type: 'tool',
      name: 'emit_problem',
      disable_parallel_tool_use: true,
    });
    expect(call.tools).toHaveLength(1);
    expect(call.tools[0].name).toBe('emit_problem');
  });

  it('502 when model returns no tool_use block', async () => {
    mocks.create.mockResolvedValue({
      content: [{ type: 'text', text: 'Sorry, I cannot...' }],
      stop_reason: 'end_turn',
      usage: { input_tokens: 10, output_tokens: 5 },
    });
    const res = await POST(
      makeRequest({ topic: 'jwt-auth', difficulty: '중급' }),
    );
    expect(res.status).toBe(502);
    const json = await res.json();
    expect(json.error).toBe('no_tool_use');
  });

  it('502 when tool input fails zod validation', async () => {
    mocks.create.mockResolvedValue(
      makeToolUseResponse({ ...validProblem, hints: validProblem.hints.slice(0, 2) }),
    );
    const res = await POST(
      makeRequest({ topic: 'mongodb-schema', difficulty: '중급' }),
    );
    expect(res.status).toBe(502);
    const json = await res.json();
    expect(json.error).toBe('invalid_tool_output');
  });

  it('429 on RateLimitError', async () => {
    const err = new RateLimitError(429, undefined, 'rate limited', new Headers());
    mocks.create.mockRejectedValue(err);
    const res = await POST(makeRequest({ topic: 'room-db', difficulty: '입문' }));
    expect(res.status).toBe(429);
    const json = await res.json();
    expect(json.error).toBe('rate_limit');
  });

  it('propagates APIError status', async () => {
    const err = new APIError(500, undefined, 'upstream blew up', new Headers());
    mocks.create.mockRejectedValue(err);
    const res = await POST(makeRequest({ topic: 'jetpack-compose', difficulty: '중급' }));
    expect(res.status).toBe(500);
    const json = await res.json();
    expect(json.error).toBe('api_error');
  });

  it('500 on unknown error', async () => {
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    mocks.create.mockRejectedValue(new Error('something exploded'));
    const res = await POST(makeRequest({ topic: 'foreground-service', difficulty: '중급' }));
    expect(res.status).toBe(500);
    const json = await res.json();
    expect(json.error).toBe('internal');
    expect(consoleSpy).toHaveBeenCalled();
  });
});
