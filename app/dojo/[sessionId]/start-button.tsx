'use client';

import { useState, useTransition } from 'react';
import { UI } from '@/lib/ko';
import { generateProblemForSession, type GenerateResult } from './actions';

const ERROR_MESSAGES: Record<
  Extract<GenerateResult, { ok: false }>['error'],
  string
> = {
  session_not_found: UI.session.errorSessionNotFound,
  session_incomplete: UI.session.errorSessionIncomplete,
  anthropic_unconfigured: UI.errors.unconfigured,
  no_tool_use: UI.session.errorGeneric,
  invalid_tool_output: UI.session.errorGeneric,
  insert_failed: UI.session.errorGeneric,
  generation_failed: UI.session.errorGeneric,
};

export function StartButton({ sessionId }: { sessionId: number }) {
  const [isPending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);

  const handleClick = () => {
    setError(null);
    startTransition(async () => {
      const result = await generateProblemForSession(sessionId);
      if (!result.ok) {
        setError(ERROR_MESSAGES[result.error] ?? UI.session.errorGeneric);
      }
      // 성공 시: 액션 안의 revalidatePath가 페이지 데이터를 갱신 →
      // 서버 컴포넌트가 problemId를 다시 읽어 ProblemView 분기로 전환됨.
    });
  };

  if (isPending) {
    return <GeneratingSkeleton />;
  }

  return (
    <div className="mt-8">
      <button
        type="button"
        onClick={handleClick}
        className="inline-flex items-center rounded-card bg-accent px-6 py-3 font-medium text-bg transition hover:bg-accent-hi focus:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-bg"
      >
        {UI.session.startGenerate}
      </button>
      {error && (
        <p
          role="alert"
          className="mt-4 rounded-md border border-danger/60 bg-danger/10 p-3 text-sm text-danger"
        >
          {error}
        </p>
      )}
    </div>
  );
}

function GeneratingSkeleton() {
  return (
    <div
      className="mt-8 space-y-4"
      role="status"
      aria-live="polite"
      aria-label={UI.session.generating}
    >
      <p className="font-mono text-xs uppercase tracking-[0.2em] text-accent animate-pulse">
        {UI.session.generating}
      </p>
      <div className="h-10 w-3/4 animate-pulse rounded-md bg-surface" aria-hidden />
      <div className="h-4 w-full animate-pulse rounded-md bg-surface" aria-hidden />
      <div className="h-4 w-5/6 animate-pulse rounded-md bg-surface" aria-hidden />
      <div className="h-4 w-2/3 animate-pulse rounded-md bg-surface" aria-hidden />
      <div className="mt-6 h-4 w-1/2 animate-pulse rounded-md bg-surface" aria-hidden />
      <div className="h-32 w-full animate-pulse rounded-md bg-surface" aria-hidden />
    </div>
  );
}
