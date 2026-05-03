'use client';

import { useCallback, useEffect, useRef, useState, useTransition } from 'react';
import type { HintStage } from '@/db/schema';
import { UI } from '@/lib/ko';
import {
  recordHintView,
  type HintStageNumber,
  type RecordHintResult,
} from '@/app/dojo/[sessionId]/hint-actions';

const KIND_LABELS: Record<HintStage['kind'], string> = {
  decision: UI.hint.kindDecision,
  tradeoff: UI.hint.kindTradeoff,
  comprehension: UI.hint.kindComprehension,
  extension: UI.hint.kindExtension,
};

const STAGE_TITLES: Record<HintStageNumber, string> = {
  1: UI.hint.stage1,
  2: UI.hint.stage2,
  3: UI.hint.stage3,
  4: UI.hint.stage4,
};

const ERROR_MESSAGES: Record<
  Extract<RecordHintResult, { ok: false }>['error'],
  string
> = {
  session_not_found: UI.hint.sessionMissingError,
  no_problem_yet: UI.hint.sessionMissingError,
  invalid_stage: UI.hint.persistError,
  persist_failed: UI.hint.persistError,
};

/**
 * 4단계 힌트 사다리 (소크라테스식).
 *
 * 규칙:
 * - 1→2→3→4 순차 unlock. 다음 단계는 이전 단계가 reveal된 후에만 활성.
 * - reveal 클릭 시 confirm dialog (한 번 보면 시도 기록에 남는다는 워밍 톤).
 * - 사용자가 dialog confirm → optimistic으로 UI 즉시 reveal +
 *   recordHintView 서버 액션 호출. 실패 시 reveal 롤백 + 에러 표시.
 *
 * 본 컴포넌트는 client component. 서버에서 attempts.hintsViewed를 prefetch해
 * initialRevealed로 넘기면, 새로고침 후에도 reveal 상태가 유지됩니다.
 */
export function HintLadder({
  hints,
  sessionId,
  initialRevealed = [],
}: {
  hints: HintStage[];
  sessionId: number;
  initialRevealed?: number[];
}) {
  const [revealed, setRevealed] = useState<Set<HintStageNumber>>(
    () => new Set(initialRevealed.filter(isStageNumber)),
  );
  const [pendingStage, setPendingStage] = useState<HintStageNumber | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();
  const dialogRef = useRef<HTMLDialogElement>(null);

  /* dialog show/close 동기화 — pendingStage가 set되면 모달 open */
  useEffect(() => {
    const d = dialogRef.current;
    if (!d) return;
    if (pendingStage !== null && !d.open) d.showModal();
    else if (pendingStage === null && d.open) d.close();
  }, [pendingStage]);

  const handleRequestReveal = useCallback((stage: HintStageNumber) => {
    setError(null);
    setPendingStage(stage);
  }, []);

  const handleCancel = useCallback(() => {
    setPendingStage(null);
  }, []);

  const handleConfirm = useCallback(() => {
    const stage = pendingStage;
    if (stage === null) return;
    setPendingStage(null);

    /* optimistic reveal — 즉시 UI 갱신 후 백그라운드로 영속화 */
    setRevealed((prev) => new Set(prev).add(stage));

    startTransition(async () => {
      const res = await recordHintView(sessionId, stage);
      if (!res.ok) {
        /* 실패 시 롤백 (단, 이미 다른 단계가 추가되어 있으면 그건 보존) */
        setRevealed((prev) => {
          const next = new Set(prev);
          next.delete(stage);
          return next;
        });
        setError(ERROR_MESSAGES[res.error] ?? UI.hint.persistError);
      }
    });
  }, [pendingStage, sessionId]);

  return (
    <section
      aria-labelledby="hint-ladder-heading"
      className="rounded-card bg-surface p-6 ring-1 ring-subtle/40"
    >
      <header>
        <h2
          id="hint-ladder-heading"
          className="font-display text-2xl text-fg"
        >
          {UI.hint.sectionHeading}
        </h2>
        <p className="mt-2 text-sm text-muted">{UI.hint.sectionSubheading}</p>
      </header>

      {error && (
        <p
          role="alert"
          className="mt-4 rounded-md border border-danger/60 bg-danger/10 p-3 text-sm text-danger"
        >
          {error}
        </p>
      )}

      <ol className="mt-6 space-y-3">
        {hints.map((hint, idx) => {
          const stage = (idx + 1) as HintStageNumber;
          const isRevealed = revealed.has(stage);
          const isUnlocked = stage === 1 || revealed.has((stage - 1) as HintStageNumber);
          return (
            <HintItem
              key={stage}
              stage={stage}
              hint={hint}
              isRevealed={isRevealed}
              isUnlocked={isUnlocked}
              onRequestReveal={handleRequestReveal}
            />
          );
        })}
      </ol>

      <ConfirmDialog
        ref={dialogRef}
        stage={pendingStage}
        isPending={isPending}
        onConfirm={handleConfirm}
        onCancel={handleCancel}
      />
    </section>
  );
}

function HintItem({
  stage,
  hint,
  isRevealed,
  isUnlocked,
  onRequestReveal,
}: {
  stage: HintStageNumber;
  hint: HintStage;
  isRevealed: boolean;
  isUnlocked: boolean;
  onRequestReveal: (stage: HintStageNumber) => void;
}) {
  const kindLabel = KIND_LABELS[hint.kind];
  const stageTitle = STAGE_TITLES[stage];

  return (
    <li
      className={`rounded-card border p-5 transition-colors ${
        isRevealed
          ? 'border-accent/40 bg-surface-2'
          : isUnlocked
            ? 'border-subtle/50 bg-surface-2/60 hover:border-accent/50'
            : 'border-subtle/30 bg-surface/40 opacity-60'
      }`}
    >
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-baseline gap-3">
          <span
            aria-hidden
            className="font-display text-3xl text-accent tabular-nums"
          >
            {stage}
          </span>
          <div>
            <h3 className="font-display text-lg text-fg">{stageTitle}</h3>
            <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-subtle">
              {kindLabel}
            </p>
          </div>
        </div>

        {isRevealed ? (
          <span className="rounded-md border border-accent/40 bg-accent/10 px-2 py-1 font-mono text-[10px] uppercase tracking-wider text-accent-hi">
            {UI.hint.revealed}
          </span>
        ) : isUnlocked ? (
          <button
            type="button"
            onClick={() => onRequestReveal(stage)}
            className="rounded-md border border-accent/60 bg-accent/10 px-3 py-1.5 font-mono text-xs text-accent-hi transition hover:bg-accent hover:text-bg focus:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-surface"
            aria-label={`${stageTitle} ${UI.hint.reveal}`}
          >
            {UI.hint.reveal}
          </button>
        ) : (
          <span
            title={UI.hint.lockedReason}
            className="rounded-md border border-subtle/40 px-2 py-1 font-mono text-[10px] uppercase tracking-wider text-subtle"
          >
            {UI.hint.locked}
          </span>
        )}
      </header>

      {isRevealed && (
        <div className="mt-5 space-y-4">
          <p className="text-base leading-relaxed text-fg">{hint.question}</p>

          {hint.options && hint.options.length > 0 && (
            <div>
              <h4 className="font-mono text-[10px] uppercase tracking-[0.2em] text-subtle">
                {UI.hint.optionsHeading}
              </h4>
              <ul className="mt-2 space-y-1.5">
                {hint.options.map((opt, i) => (
                  <li
                    key={i}
                    className="rounded border border-subtle/40 bg-surface px-3 py-1.5 text-sm text-fg"
                  >
                    {opt}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div>
            <h4 className="font-mono text-[10px] uppercase tracking-[0.2em] text-subtle">
              {UI.hint.rationaleHeading}
            </h4>
            <p className="mt-1.5 text-sm leading-relaxed text-muted">{hint.rationale}</p>
          </div>
        </div>
      )}
    </li>
  );
}

function ConfirmDialog({
  ref,
  stage,
  isPending,
  onConfirm,
  onCancel,
}: {
  ref: React.RefObject<HTMLDialogElement | null>;
  stage: HintStageNumber | null;
  isPending: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <dialog
      ref={ref}
      onClose={onCancel}
      onCancel={onCancel}
      className="m-auto rounded-card bg-surface p-0 ring-1 ring-accent/40 backdrop:bg-bg/70 backdrop:backdrop-blur-sm"
      aria-labelledby="confirm-title"
      aria-describedby="confirm-body"
    >
      <div className="max-w-md p-6">
        <h2 id="confirm-title" className="font-display text-2xl text-fg">
          {UI.hint.confirmTitle}
        </h2>
        {stage !== null && (
          <p className="mt-2 font-mono text-[10px] uppercase tracking-[0.2em] text-accent">
            {STAGE_TITLES[stage]}
          </p>
        )}
        <p
          id="confirm-body"
          className="mt-3 text-sm leading-relaxed text-muted"
        >
          {UI.hint.confirmBody}
        </p>
        <div className="mt-6 flex flex-wrap items-center justify-end gap-3">
          <button
            type="button"
            onClick={onCancel}
            disabled={isPending}
            className="rounded-md border border-subtle/50 bg-surface-2 px-4 py-2 font-medium text-muted transition hover:border-accent hover:text-accent disabled:cursor-not-allowed disabled:opacity-60"
          >
            {UI.hint.confirmNo}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={isPending}
            className="rounded-md bg-accent px-4 py-2 font-medium text-bg transition hover:bg-accent-hi disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isPending ? UI.hint.revealing : UI.hint.confirmYes}
          </button>
        </div>
      </div>
    </dialog>
  );
}

function isStageNumber(n: number): n is HintStageNumber {
  return n === 1 || n === 2 || n === 3 || n === 4;
}
