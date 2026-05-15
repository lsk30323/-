'use client';

import { useMemo } from 'react';
import { UI } from '@/lib/ko';

export type TimerPhase = 'calm' | 'alert' | 'urgent' | 'final';

const PHASE_LABEL: Record<TimerPhase, string> = {
  calm: UI.interview.phaseCalm,
  alert: UI.interview.phaseAlert,
  urgent: UI.interview.phaseUrgent,
  final: UI.interview.phaseFinal,
};

/**
 * 카운트다운 시각화. tabular-nums로 자리수가 줄어도 흔들림 없음.
 *
 * Phase 결정 규칙 (남은 비율 r = timeRemaining / total):
 *   final  — timeRemaining <= 30초 (절대값 기준, 마지막 30초)
 *   urgent — r < 0.10 (마지막 10% 안쪽)
 *   alert  — r < 0.30 (마지막 30% 안쪽)
 *   calm   — 그 외
 *
 * 색상: calm=muted → alert=accent → urgent=accent-hi(pulse) → final=danger(pulse).
 * 본 컴포넌트는 비주얼 전용 — 실제 타이밍은 useCountdown 훅이 담당, 결과를
 * prop으로 전달받습니다 (Slice 10b의 InterviewSession에서 wire).
 */
export function InterviewTimer({
  timeRemaining,
  total,
  isExpired,
}: {
  /** 남은 시간 (초). */
  timeRemaining: number;
  /** 초기 시간 (초). phase 계산 분모. */
  total: number;
  /** true면 만료 상태. */
  isExpired: boolean;
}) {
  const phase: TimerPhase = useMemo(() => {
    if (timeRemaining <= 0) return 'final';
    if (timeRemaining <= 30) return 'final';
    const ratio = total > 0 ? timeRemaining / total : 0;
    if (ratio < 0.1) return 'urgent';
    if (ratio < 0.3) return 'alert';
    return 'calm';
  }, [timeRemaining, total]);

  const toneClass =
    phase === 'final'
      ? 'text-danger animate-pulse'
      : phase === 'urgent'
        ? 'text-accent-hi animate-pulse'
        : phase === 'alert'
          ? 'text-accent'
          : 'text-fg';

  const phaseLabel = isExpired ? UI.interview.expired : PHASE_LABEL[phase];
  const progressPct = total > 0 ? (1 - Math.max(0, timeRemaining) / total) * 100 : 0;

  return (
    <div
      role="timer"
      aria-live="polite"
      aria-atomic="true"
      aria-label={`${UI.interview.timerLabel} ${formatTime(timeRemaining)}`}
      className="relative flex items-baseline gap-4 overflow-hidden rounded-card bg-surface px-5 py-3 ring-1 ring-subtle/40"
    >
      <span
        className={`font-mono text-2xl font-semibold tabular-nums tracking-tight ${toneClass}`}
      >
        {formatTime(timeRemaining)}
      </span>
      <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-subtle">
        {phaseLabel}
      </span>

      {/* progress bar — 배경 위에 얇은 accent 줄, 만료 시 danger */}
      <span
        aria-hidden
        className={`absolute bottom-0 left-0 h-[2px] transition-[width] duration-300 ease-out ${
          isExpired || phase === 'final' ? 'bg-danger' : 'bg-accent'
        }`}
        style={{ width: `${progressPct.toFixed(2)}%` }}
      />
    </div>
  );
}

/** MM:SS 포맷터. timeRemaining < 0은 0으로 클램프. */
function formatTime(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  const mm = String(Math.floor(s / 60)).padStart(2, '0');
  const ss = String(s % 60).padStart(2, '0');
  return `${mm}:${ss}`;
}
