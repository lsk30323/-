'use client';

import dynamic from 'next/dynamic';
import { useCallback, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import type { Problem, Session } from '@/db/schema';
import { useCountdown } from '@/lib/hooks/useCountdown';
import {
  useDebouncedAutosave,
  type AutosaveStatus,
} from '@/lib/hooks/useDebouncedAutosave';
import { useInterviewLock } from '@/lib/hooks/useInterviewLock';
import { InterviewTimer } from '@/components/interview/InterviewTimer';
import { HintLadder } from '@/components/hint/HintLadder';
import { UI } from '@/lib/ko';
import {
  finalizeAttempt,
  saveAttemptCode,
} from '@/app/dojo/[sessionId]/attempt-actions';

/* Monaco는 client-only (ssr:false). EditorPanel과 동일 패턴이지만 인터뷰는
   Run 버튼·출력 패널이 없는 minimal 변형 — 코드 작성과 타이머에 집중. */
const MonacoInner = dynamic(() => import('@/components/editor/monaco-inner'), {
  ssr: false,
  loading: () => (
    <div className="flex h-full w-full items-center justify-center bg-bg">
      <div className="space-y-2">
        <div className="h-3 w-32 animate-pulse rounded bg-surface" />
        <div className="h-3 w-48 animate-pulse rounded bg-surface" />
      </div>
    </div>
  ),
});

const STATUS_LABEL: Record<AutosaveStatus, string> = {
  idle: UI.interview.autosaveIdle,
  dirty: UI.interview.autosaveDirty,
  saving: UI.interview.autosaveSaving,
  saved: UI.interview.autosaveSaved,
  error: UI.interview.autosaveError,
};

const STATUS_TONE: Record<AutosaveStatus, string> = {
  idle: 'text-subtle',
  dirty: 'text-accent',
  saving: 'text-accent-hi',
  saved: 'text-success',
  error: 'text-danger',
};

export function InterviewSession({
  session,
  problem,
  totalSeconds,
  initialCode,
  initialHintsViewed,
}: {
  session: Session;
  problem: Problem;
  totalSeconds: number;
  initialCode: string;
  initialHintsViewed: number[];
}) {
  const router = useRouter();
  const [code, setCode] = useState(initialCode);
  const [hasFinalized, setHasFinalized] = useState(false);
  const [isFinalizing, setIsFinalizing] = useState(false);
  const [submitMessage, setSubmitMessage] = useState<string | null>(null);
  /* useState lazy init은 첫 렌더에서만 호출되어 React 19 purity 룰에 안전.
     세션 시작 시각 = 컴포넌트 mount 시각. */
  const [startedAt] = useState<number>(() => Date.now());
  /* 동기 race guard — 더블 클릭 / 만료+제출 동시 발생 시 단일 finalize 보장 */
  const finalizingRef = useRef<boolean>(false);

  /* 12초마다 in-progress attempt에 code 저장. flushOnUnmount=true로 페이지 이탈 시
     마지막 변경을 한 번 더 시도. */
  const { status, lastSavedAt, flush } = useDebouncedAutosave(
    code,
    async (v) => {
      const r = await saveAttemptCode(session.id, v);
      if (!r.ok) throw new Error(r.error);
    },
    { delayMs: 12_000, flushOnUnmount: true },
  );

  /* 페이지 이탈 차단 — 제출 전까지만. 제출 후엔 자유롭게 navigate. */
  useInterviewLock({ enabled: !hasFinalized });

  const performFinalize = useCallback(
    async (reason: 'manual' | 'expired') => {
      if (finalizingRef.current || hasFinalized) return;
      finalizingRef.current = true;
      setIsFinalizing(true);
      const elapsed = Math.max(
        0,
        Math.floor((Date.now() - startedAt) / 1000),
      );
      const res = await finalizeAttempt(session.id, code, elapsed);
      if (res.ok) {
        setHasFinalized(true);
        setSubmitMessage(
          reason === 'expired' ? UI.interview.autoSubmittedOnExpire : null,
        );
        /* server action의 revalidatePath가 페이지 데이터를 갱신하지만,
           hasFinalized state가 이미 true라 InterviewSession은 "제출됨" 화면을
           직접 렌더. router.refresh()는 cosmetic — 서버 컴포넌트 데이터도 최신화. */
        router.refresh();
      } else {
        finalizingRef.current = false;
        setIsFinalizing(false);
        setSubmitMessage(UI.interview.autosaveError);
      }
    },
    [code, hasFinalized, router, session.id, startedAt],
  );

  /* 카운트다운 만료 시 자동 제출. onExpire는 ref로 캡처되므로 stale closure
     걱정 없음. */
  const { timeRemaining, isExpired } = useCountdown(totalSeconds, {
    onExpire: () => {
      void performFinalize('expired');
    },
  });

  const handleManualSubmit = () => {
    /* flush로 마지막 변경 즉시 저장 (선택적 — finalize가 어차피 code를 직접 씀) */
    flush();
    void performFinalize('manual');
  };

  if (hasFinalized) {
    return (
      <SubmittedView
        message={submitMessage}
        sessionId={session.id}
        problemTitle={problem.title}
      />
    );
  }

  return (
    <main className="mx-auto max-w-7xl px-6 py-6">
      {/* Lock notice — 페이지 이탈 안내 */}
      <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-subtle">
        {UI.interview.lockNotice}
      </p>

      {/* Top bar: timer + autosave + submit */}
      <header className="mt-3 flex flex-wrap items-center justify-between gap-3 rounded-card bg-surface px-4 py-3 ring-1 ring-subtle/40">
        <div className="flex items-center gap-3">
          <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-subtle">
            {UI.session.breadcrumb} #{session.id} · {problem.title}
          </span>
        </div>
        <div className="flex items-center gap-4">
          <AutosaveBadge status={status} lastSavedAt={lastSavedAt} />
          <InterviewTimer
            timeRemaining={timeRemaining}
            total={totalSeconds}
            isExpired={isExpired}
          />
          <button
            type="button"
            onClick={handleManualSubmit}
            disabled={isFinalizing}
            className="rounded-card bg-accent px-5 py-2 font-medium text-bg transition hover:bg-accent-hi disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isFinalizing ? UI.interview.submitting : UI.interview.submitNow}
          </button>
        </div>
      </header>

      {/* Side-by-side problem + editor */}
      <div className="mt-5 grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className="space-y-6 lg:overflow-y-auto lg:max-h-[calc(100vh-13rem)] lg:pr-2">
          <ProblemView problem={problem} />
          <HintLadder
            hints={problem.hints}
            sessionId={session.id}
            initialRevealed={initialHintsViewed}
          />
        </div>
        <div className="h-[640px] rounded-card bg-surface ring-1 ring-subtle/40 lg:h-[calc(100vh-13rem)] lg:min-h-[480px] lg:sticky lg:top-6">
          <MonacoInner
            value={code}
            onChange={setCode}
            ariaLabel={UI.editor.panelLabel}
          />
        </div>
      </div>
    </main>
  );
}

function AutosaveBadge({
  status,
  lastSavedAt,
}: {
  status: AutosaveStatus;
  lastSavedAt: number | null;
}) {
  const label = STATUS_LABEL[status];
  const tone = STATUS_TONE[status];
  const dotPulse = status === 'saving' || status === 'dirty';

  return (
    <span
      className={`inline-flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.2em] ${tone}`}
      title={
        lastSavedAt
          ? `${UI.interview.autosaveLastAt}: ${new Date(lastSavedAt).toLocaleTimeString('ko-KR')}`
          : undefined
      }
      aria-live="polite"
    >
      <span
        aria-hidden
        className={`h-1.5 w-1.5 rounded-full bg-current ${dotPulse ? 'animate-pulse' : ''}`}
      />
      {label}
    </span>
  );
}

function ProblemView({ problem }: { problem: Problem }) {
  return (
    <article>
      <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-accent">
        {UI.session.problemHeading}
      </p>
      <h1 className="mt-2 font-display text-4xl leading-[1.15] text-fg">
        {problem.title}
      </h1>
      <section className="mt-6">
        <h2 className="sr-only">{UI.session.descriptionHeading}</h2>
        <div className="whitespace-pre-wrap text-base leading-relaxed text-fg/90">
          {problem.description}
        </div>
      </section>
      {problem.tags.length > 0 && (
        <section className="mt-6">
          <h2 className="font-mono text-xs uppercase tracking-[0.2em] text-subtle">
            {UI.session.tagsHeading}
          </h2>
          <ul className="mt-3 flex flex-wrap gap-2">
            {problem.tags.map((tag) => (
              <li
                key={tag}
                className="rounded-md border border-subtle/50 bg-surface-2 px-2.5 py-1 font-mono text-xs text-muted"
              >
                {tag}
              </li>
            ))}
          </ul>
        </section>
      )}
    </article>
  );
}

function SubmittedView({
  message,
  sessionId,
  problemTitle,
}: {
  message: string | null;
  sessionId: number;
  problemTitle: string;
}) {
  const router = useRouter();
  return (
    <main className="mx-auto max-w-2xl px-6 py-24 text-center">
      <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-accent">
        {UI.session.breadcrumb} #{sessionId}
      </p>
      <h1 className="mt-3 font-display text-5xl text-fg">
        {UI.interview.autosaveSaved} ✓
      </h1>
      <p className="mt-3 text-muted">{problemTitle}</p>
      {message && (
        <p className="mt-6 inline-block rounded-md border border-accent/50 bg-accent/10 px-4 py-2 text-sm text-accent-hi">
          {message}
        </p>
      )}
      <p className="mt-10 text-sm text-subtle">
        리뷰 화면은 Slice 11에서 구현됩니다.
      </p>
      <button
        type="button"
        onClick={() => router.push('/')}
        className="mt-8 rounded-md border border-subtle/50 bg-surface px-5 py-2 text-muted transition hover:border-accent hover:text-accent"
      >
        {UI.dojo.backToLanding}
      </button>
    </main>
  );
}
