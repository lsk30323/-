'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

export type CountdownOptions = {
  autoStart?: boolean;
  onExpire?: () => void;
};

export type CountdownState = {
  /** 남은 시간 (초). 0까지 감소 후 isExpired=true로 잠금. */
  timeRemaining: number;
  /** true면 0초에 도달하여 onExpire 콜백이 한 번 실행된 상태. */
  isExpired: boolean;
  /** 현재 tick interval이 살아있는지 — pause/resume 토글 가능. */
  isRunning: boolean;
  pause: () => void;
  resume: () => void;
};

/**
 * Drift-free 카운트다운 훅.
 *
 * 단순 setInterval 카운터는 React StrictMode dev에서 effect 이중 호출 시 2배
 * 빨라지고, 백그라운드 탭에서 throttle되어 부정확해집니다.
 * 본 훅은 `Date.now()` baseline + endAt 절대 시각 기준으로 매 tick마다 잔여
 * 시간을 재계산 — 어떤 환경에서든 wall clock 기준으로 정확.
 *
 * 250ms 간격으로 tick (1초 해상도로는 부족, 100ms는 과함). pause하면 잔여
 * 시간을 remainRef에 저장, resume 시 새 endAt 계산.
 *
 * onExpire는 ref로 저장 — 호출자가 매 렌더마다 새 함수를 만들어도 effect deps에
 * 추가하지 않아 불필요한 재시작을 막습니다.
 */
export function useCountdown(
  initialSec: number,
  opts: CountdownOptions = {},
): CountdownState {
  const { autoStart = true, onExpire } = opts;

  const endAtRef = useRef<number | null>(null);
  const remainRef = useRef<number>(initialSec * 1000);
  const onExpireRef = useRef<CountdownOptions['onExpire']>(onExpire);

  const [timeRemaining, setTime] = useState<number>(initialSec);
  const [isRunning, setRunning] = useState<boolean>(autoStart);
  const [isExpired, setExpired] = useState<boolean>(false);

  /* 최신 onExpire 콜백을 ref에 동기화 — 매 렌더 후 1회. effect deps에 onExpire를
     넣지 않아 콜백 identity 변경이 카운트다운을 재시작시키지 않습니다. */
  useEffect(() => {
    onExpireRef.current = onExpire;
  });

  useEffect(() => {
    if (!isRunning || isExpired) return;
    if (endAtRef.current === null) {
      endAtRef.current = Date.now() + remainRef.current;
    }

    const tick = () => {
      const ms = Math.max(0, (endAtRef.current ?? 0) - Date.now());
      setTime(Math.ceil(ms / 1000));
      if (ms <= 0) {
        setExpired(true);
        setRunning(false);
        endAtRef.current = null;
        remainRef.current = 0;
        onExpireRef.current?.();
      }
    };

    tick();
    const id = window.setInterval(tick, 250);
    return () => window.clearInterval(id);
  }, [isRunning, isExpired]);

  const pause = useCallback(() => {
    if (!isRunning || isExpired) return;
    remainRef.current = Math.max(0, (endAtRef.current ?? Date.now()) - Date.now());
    endAtRef.current = null;
    setRunning(false);
  }, [isRunning, isExpired]);

  const resume = useCallback(() => {
    if (isRunning || isExpired) return;
    endAtRef.current = Date.now() + remainRef.current;
    setRunning(true);
  }, [isRunning, isExpired]);

  return { timeRemaining, isExpired, isRunning, pause, resume };
}
