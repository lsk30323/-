'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

export type AutosaveStatus = 'idle' | 'dirty' | 'saving' | 'saved' | 'error';

/**
 * value가 변경되면 delayMs 후 save를 1회 호출하는 디바운스 훅.
 *
 * - 같은 값으로의 재호출은 무시 (Object.is 비교).
 * - delayMs 안에 다시 변경되면 타이머 리셋 (마지막 변경 기준).
 * - save가 throw하면 status='error'. 정상 완료 시 'saved'.
 * - 컴포넌트 unmount 시 진행 중인 디바운스 타이머 취소 → flushOnUnmount 옵션을
 *   true로 주면 unmount 시 즉시 저장 시도 (인터뷰 모드 페이지 이탈에 유용).
 *
 * 호환 안내: 본 훅은 'use client' 컴포넌트에서만 사용. window/clearTimeout 의존.
 */
export function useDebouncedAutosave<T>(
  value: T,
  save: (v: T) => void | Promise<void>,
  options: { delayMs?: number; flushOnUnmount?: boolean } = {},
): {
  status: AutosaveStatus;
  lastSavedAt: number | null;
  /** 다음 save를 즉시 트리거 (현재 value로). 수동 저장 버튼용. */
  flush: () => void;
} {
  const { delayMs = 12_000, flushOnUnmount = true } = options;

  const [status, setStatus] = useState<AutosaveStatus>('idle');
  const [lastSavedAt, setLastSavedAt] = useState<number | null>(null);

  const valueRef = useRef<T>(value);
  const lastSavedValueRef = useRef<T | undefined>(undefined);
  const timerRef = useRef<number | null>(null);
  const saveRef = useRef(save);

  /* 매 렌더 후 최신 value/save를 ref에 동기화. effect/timeout 안에서 안전하게
     읽을 수 있도록. (in-render ref 쓰기는 React 19 strict 경고 발생) */
  useEffect(() => {
    valueRef.current = value;
    saveRef.current = save;
  });

  const runSave = useCallback(async (v: T) => {
    setStatus('saving');
    try {
      await saveRef.current(v);
      lastSavedValueRef.current = v;
      setStatus('saved');
      setLastSavedAt(Date.now());
    } catch (err) {
      console.error('[useDebouncedAutosave] save failed:', err);
      setStatus('error');
    }
  }, []);

  /* value 변경 감지 → debounce */
  useEffect(() => {
    if (Object.is(value, lastSavedValueRef.current)) return;
    setStatus('dirty');

    if (timerRef.current !== null) window.clearTimeout(timerRef.current);
    timerRef.current = window.setTimeout(() => {
      void runSave(valueRef.current);
    }, delayMs);

    return () => {
      if (timerRef.current !== null) {
        window.clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [value, delayMs, runSave]);

  /* unmount 시 flush — 인터뷰 페이지 이탈 시 마지막 코드 저장 시도 */
  useEffect(() => {
    return () => {
      if (!flushOnUnmount) return;
      if (Object.is(valueRef.current, lastSavedValueRef.current)) return;
      void runSave(valueRef.current);
    };
  }, [flushOnUnmount, runSave]);

  const flush = useCallback(() => {
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    void runSave(valueRef.current);
  }, [runSave]);

  return { status, lastSavedAt, flush };
}
