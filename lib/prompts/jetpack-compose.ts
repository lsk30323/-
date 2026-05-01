import type { Difficulty } from '@/db/schema';
import { buildUserPromptHeader, type TopicPromptModule } from './_shared';

const topicSystemPrompt = `토픽: **Jetpack Compose**

핵심 개념:
- State hoisting: stateful → stateless composable 분리, \`onValueChange\` 콜백.
- \`remember\` vs \`rememberSaveable\` (configuration change 보존).
- Recomposition scope: smallest scope가 invalidated. unstable 매개변수는 skipping 무효화.
- Side effects API: \`LaunchedEffect(key)\`, \`DisposableEffect\`, \`SideEffect\`,
  \`rememberCoroutineScope\`, \`rememberUpdatedState\`, \`derivedStateOf\`, \`snapshotFlow\`.
- \`collectAsStateWithLifecycle\` — Flow 수신 lifecycle aware.
- \`CompositionLocal\`로 implicit 의존성 주입 (\`LocalContext\`, custom).
- Modifier 순서 — \`.padding(8.dp).background(Red)\` ≠ \`.background(Red).padding(8.dp)\`.
- Lazy 리스트(\`LazyColumn\`/\`LazyRow\`) + \`key\` 매개변수로 안정성 + \`itemsIndexed\`.
- 성능: \`@Stable\`/\`@Immutable\` 어노테이션, \`Modifier.Node\` API, \`derivedStateOf\` 활용.
- 접근성: \`semantics\`, \`contentDescription\`, TalkBack.
- 테스트: \`createComposeRule\`, \`onNodeWithText\`, \`performClick\`.

도메인 훅: 만보기 UI — 일별 걸음 수 progress ring (\`Canvas\` + animation),
주간 막대 차트, 목표 도달 ConfettiAnimation, BottomSheet로 세션 상세.

흔한 함정 / 평가 포인트:
- \`State\`를 ViewModel에 두지 않고 composable에 두면 회전 시 손실 — \`rememberSaveable\`/VM 사용.
- 자주 변하는 람다를 매개변수로 넘기면 recomposition 폭증 — \`remember { { ... } }\` 또는
  \`rememberUpdatedState\`로 안정화.
- Flow를 직접 \`collect\` (안티패턴) → \`collectAsStateWithLifecycle\`로 lifecycle aware.
- Mutable list/Map 직접 \`mutableStateOf\`에 넣으면 변경 감지 X → \`mutableStateListOf\`/Map.
- 무거운 계산을 composable 본문에 두면 매 recomposition마다 실행 → \`derivedStateOf\` / \`remember(key)\`.

출제 시 고려:
- 입문: 단일 Stateful composable + state hoisting 리팩토링 + Preview.
- 중급: VM의 StateFlow 수신 + LaunchedEffect로 side effect + Modifier 순서 이슈.
- 면접급: 성능 진단(recomposition count), 안정성 어노테이션, custom Layout, accessibility.
`;

function buildUserPrompt(difficulty: Difficulty): string {
  return `${buildUserPromptHeader('jetpack-compose', difficulty)}

추가 지시:
- 도메인 컴포넌트는 만보기 UI 맥락(progress ring, 일별 걸음 카드, 주간 차트 등) 사용.
- reference_solution은 단일 composable 함수 또는 함수 2~3개로 구성하고, Preview 1개 포함.
- 면접급 stage 2(tradeoff)는 state holder 위치(VM vs hoisted state vs composable-local)를
  configuration change·테스트 용이성·재사용성 측면으로 비교하세요.
- 접근성(\`contentDescription\` 또는 \`semantics\`)을 reference 코드에 1곳 이상 표시하세요.`;
}

export const jetpackComposePrompt: TopicPromptModule = {
  topic: 'jetpack-compose',
  topicSystemPrompt,
  buildUserPrompt,
};
