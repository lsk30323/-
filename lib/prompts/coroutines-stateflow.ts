import type { Difficulty } from '@/db/schema';
import { buildUserPromptHeader, type TopicPromptModule } from './_shared';

const topicSystemPrompt = `토픽: **Coroutines & StateFlow**

핵심 개념 (출제 시 1~3개 자연스럽게 엮을 것):
- Structured concurrency: \`coroutineScope\`, \`supervisorScope\`, \`viewModelScope\`, 취소 전파.
- Hot vs cold flow: \`Flow\` (cold) → \`StateFlow\`/\`SharedFlow\` (hot) 변환과 trade-off.
- \`SharingStarted.Eagerly\` / \`Lazily\` / \`WhileSubscribed(5_000)\` 차이와 lifecycle 영향.
- Lifecycle-aware collection: \`repeatOnLifecycle\`, \`collectAsStateWithLifecycle\`.
- 예외 처리: \`CoroutineExceptionHandler\`, \`runCatching\`, \`SupervisorJob\` 의 의미.
- 테스트: \`TestDispatcher\`, \`runTest\`, \`UnconfinedTestDispatcher\` vs \`StandardTestDispatcher\`.
- 백프레셔/취소 안정성: \`flowOn\`, \`buffer\`, \`conflate\`, \`distinctUntilChanged\`.

도메인 훅(권장): "사용자의 일일 걸음 수 시계열을 \`Flow<Long>\`로 받아 …", "센서 이벤트가 멈춰도 UI 마지막 값이 보여야 한다" 등 만보기 맥락.

흔한 함정 / 면접관 관점 평가 포인트:
- \`MutableStateFlow\`를 직접 외부에 노출하지 않는가 (read-only \`StateFlow\` 캡슐화).
- \`combine\` / \`zip\`의 backpressure 차이를 정확히 설명할 수 있는가.
- \`stateIn\`의 \`SharingStarted.WhileSubscribed(5_000)\`이 왜 5초인지 — 화면 회전 사이 캐시.
- \`launch\` 안에서 \`viewModelScope\` 캡처해 메모리 누수 만드는 안티패턴 인지.

출제 시 고려:
- 입문: 단일 ViewModel + StateFlow + Compose collect 기본형.
- 중급: 여러 source flow 결합 + lifecycle-aware + 단위 테스트.
- 면접급: 동시성 제어(Mutex / actor), 취소 안전성, 시간 의존 테스트, sharing 전략 비교.
`;

function buildUserPrompt(difficulty: Difficulty): string {
  return `${buildUserPromptHeader('coroutines-stateflow', difficulty)}

추가 지시:
- description에 도메인 훅 예시(걸음 수 시계열 등) 1개 이상 포함하세요.
- reference_solution은 ViewModel 또는 Repository 단위의 idiomatic Kotlin 코드로 작성하고,
  StateFlow/Flow 노출 방식과 collection 방식을 모두 보이세요.
- 면접급일 경우 stage 2(tradeoff) 힌트는 sharing 전략 또는 hot/cold 변환의 trade-off를
  최소 2개 비교 축으로 분석하세요.`;
}

export const coroutinesStateflowPrompt: TopicPromptModule = {
  topic: 'coroutines-stateflow',
  topicSystemPrompt,
  buildUserPrompt,
};
