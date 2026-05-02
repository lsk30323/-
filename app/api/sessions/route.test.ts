import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  insert: vi.fn(),
}));

vi.mock('@/db', () => ({
  db: {
    insert: mocks.insert,
  },
  schema: {},
}));

vi.mock('server-only', () => ({}));

const { POST } = await import('./route');

function setSuccessfulInsert(returningRow: Record<string, unknown>) {
  mocks.insert.mockReturnValue({
    values: vi.fn().mockReturnValue({
      returning: vi.fn().mockResolvedValue([returningRow]),
    }),
  });
}

function setFailingInsert(err: unknown) {
  mocks.insert.mockReturnValue({
    values: vi.fn().mockReturnValue({
      returning: vi.fn().mockRejectedValue(err),
    }),
  });
}

function setEmptyInsert() {
  mocks.insert.mockReturnValue({
    values: vi.fn().mockReturnValue({
      returning: vi.fn().mockResolvedValue([]),
    }),
  });
}

function makeRequest(body: unknown): Request {
  return new Request('http://localhost/api/sessions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: typeof body === 'string' ? body : JSON.stringify(body),
  });
}

beforeEach(() => {
  mocks.insert.mockReset();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('POST /api/sessions', () => {
  it('400 on invalid JSON', async () => {
    const res = await POST(makeRequest('garbage{'));
    expect(res.status).toBe(400);
    expect((await res.json()).error).toBe('invalid_json');
  });

  it('400 on missing mode', async () => {
    const res = await POST(makeRequest({}));
    expect(res.status).toBe(400);
    expect((await res.json()).error).toBe('invalid_body');
  });

  it('400 on unknown mode', async () => {
    const res = await POST(makeRequest({ mode: 'casual' }));
    expect(res.status).toBe(400);
  });

  it('400 on interview mode without timeLimitMinutes', async () => {
    const res = await POST(
      makeRequest({ mode: 'interview', topic: 'room-db', difficulty: '중급' }),
    );
    expect(res.status).toBe(400);
    const json = await res.json();
    expect(json.error).toBe('invalid_body');
  });

  it('400 on invalid timeLimitMinutes', async () => {
    const res = await POST(
      makeRequest({ mode: 'interview', timeLimitMinutes: 25 }),
    );
    expect(res.status).toBe(400);
  });

  it('201 creates practice session without time', async () => {
    setSuccessfulInsert({
      id: 7,
      mode: 'practice',
      topic: 'coroutines-stateflow',
      difficulty: '입문',
      timeLimitMinutes: null,
      createdAt: new Date(),
      endedAt: null,
    });
    const res = await POST(
      makeRequest({
        mode: 'practice',
        topic: 'coroutines-stateflow',
        difficulty: '입문',
      }),
    );
    expect(res.status).toBe(201);
    const json = await res.json();
    expect(json.sessionId).toBe(7);
    expect(json.session.mode).toBe('practice');
  });

  it('201 creates interview session with 45 min', async () => {
    setSuccessfulInsert({
      id: 9,
      mode: 'interview',
      topic: 'jwt-auth',
      difficulty: '면접급',
      timeLimitMinutes: 45,
      createdAt: new Date(),
      endedAt: null,
    });
    const res = await POST(
      makeRequest({
        mode: 'interview',
        topic: 'jwt-auth',
        difficulty: '면접급',
        timeLimitMinutes: 45,
      }),
    );
    expect(res.status).toBe(201);
    const json = await res.json();
    expect(json.sessionId).toBe(9);
    expect(json.session.timeLimitMinutes).toBe(45);
  });

  it('strips timeLimitMinutes for practice mode', async () => {
    let captured: Record<string, unknown> = {};
    mocks.insert.mockReturnValue({
      values: vi.fn().mockImplementation((v: Record<string, unknown>) => {
        captured = v;
        return {
          returning: vi.fn().mockResolvedValue([{ id: 1, ...v }]),
        };
      }),
    });
    await POST(
      makeRequest({
        mode: 'practice',
        topic: 'room-db',
        difficulty: '중급',
        timeLimitMinutes: 60,
      }),
    );
    expect(captured.timeLimitMinutes).toBeNull();
    expect(captured.mode).toBe('practice');
  });

  it('500 when insert returns no rows', async () => {
    setEmptyInsert();
    const res = await POST(
      makeRequest({ mode: 'practice', topic: 'room-db', difficulty: '입문' }),
    );
    expect(res.status).toBe(500);
    expect((await res.json()).error).toBe('insert_failed');
  });

  it('500 on DB error', async () => {
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    setFailingInsert(new Error('disk full'));
    const res = await POST(makeRequest({ mode: 'practice' }));
    expect(res.status).toBe(500);
    expect((await res.json()).error).toBe('internal');
    expect(consoleSpy).toHaveBeenCalled();
  });
});
