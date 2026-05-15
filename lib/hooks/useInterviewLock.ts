'use client';

import { useEffect } from 'react';

/**
 * 인터뷰 모드 진행 중 페이지 이탈 방지.
 *
 * Next 16 App Router는 in-app navigation을 프로그래밍 방식으로 차단할 공식 API가
 * 없습니다 (legacy `useRouter().events`는 제거됨). 본 훅은 두 가지 layer만 책임:
 *   1) browser-level navigation (탭 닫기 / 새로고침 / URL 변경) → beforeunload
 *      이벤트로 표준 confirmation prompt 노출.
 *   2) history API back/forward → popstate를 감청해 같은 자리에 pushState로
 *      되돌려놓아 효과적으로 차단 (사용자가 명시적으로 '나가기' 버튼을 누르면
 *      enabled를 false로 토글 후 router.push를 호출해야 함).
 *
 * 글로벌 네비게이션 자체는 호출자가 "nav를 렌더링하지 않는 인터뷰 셸"을 사용해
 * 시각적으로 숨기는 방식으로 처리합니다 — 본 훅과 협력.
 */
export function useInterviewLock({ enabled }: { enabled: boolean }): void {
  useEffect(() => {
    if (!enabled) return;

    /* (1) beforeunload — 표준 브라우저 confirm. 메시지 문자열은 모던 브라우저가
       무시하고 default 메시지를 보여줌. returnValue 세팅이 트리거 조건. */
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      // 일부 구형 브라우저 호환을 위해 둘 다 설정.
      e.returnValue = '';
      return '';
    };

    /* (2) popstate — 뒤로가기/앞으로가기 차단. 한 번 더 pushState로 같은 URL을
       쌓아 사용자가 떠나는 인상을 받지 못하도록 함. */
    const onPopState = () => {
      window.history.pushState(null, '', window.location.href);
    };

    window.addEventListener('beforeunload', onBeforeUnload);
    window.addEventListener('popstate', onPopState);
    /* 초기 진입 시 한 칸 쌓아두기 — popstate 발화 후 즉시 다시 쌓을 수 있게 */
    window.history.pushState(null, '', window.location.href);

    return () => {
      window.removeEventListener('beforeunload', onBeforeUnload);
      window.removeEventListener('popstate', onPopState);
    };
  }, [enabled]);
}
