import type { Difficulty } from '@/db/schema';
import { buildUserPromptHeader, type TopicPromptModule } from './_shared';

const topicSystemPrompt = `토픽: **JWT 인증 (Android 클라이언트 관점)**

핵심 개념:
- Access token (단명, 메모리/일반 저장) vs Refresh token (장명, 안전 저장).
- 안전 저장: \`EncryptedSharedPreferences\` (Tink-backed) 또는 Android Keystore + Tink/JCA.
  플레인 \`SharedPreferences\` 토큰 저장은 안티패턴.
- OkHttp 통합: \`Authenticator\` 인터페이스로 401 → refresh → retry 흐름.
- Token refresh race condition: 다중 요청이 동시에 401을 받으면 refresh가 N번 호출되는
  문제 — \`Mutex\`/\`AtomicReference\` 또는 \`coroutineScope\` 기반 single-flight 패턴 필요.
- Logout / token rotation: refresh 시 새 refresh token 발급(rotation)·이전 토큰 무효화.
- Token claims 디코딩: 클라이언트는 서명 검증을 직접 하지 않고 만료(\`exp\`)만 가볍게
  체크 (만료 직전 미리 갱신). 서명 검증은 서버 책임.
- Deep link / OAuth callback: \`Intent\` data → 토큰 추출 시 만남표 검증, replay 방지.

흔한 함정 / 평가 포인트:
- 토큰을 \`Bundle\`/\`Intent\` extras로 평문 전달하면 다른 앱에 노출될 수 있음.
- Refresh가 실패하면 (예: 401·403) 사용자를 로그아웃 흐름으로 보내야 — 무한 retry 금지.
- 시간 동기화 문제로 \`exp\` 비교가 어긋남 → 서버 시간 기준으로만 판단.
- Biometric prompt와 토큰 잠금 결합 (선택적 보안 레이어).

출제 시 고려:
- 입문: Retrofit + Authorization 헤더 인터셉터 작성.
- 중급: OkHttp Authenticator로 401 retry + Mutex single-flight refresh.
- 면접급: rotation·revocation 정책, 보안 저장 비교(EncryptedSP vs Keystore + Tink),
  refresh 실패 UX, 다중 계정 토큰 관리.
`;

function buildUserPrompt(difficulty: Difficulty): string {
  return `${buildUserPromptHeader('jwt-auth', difficulty)}

추가 지시:
- 도메인 맥락: 워크온 백엔드 \`/api/walk-sessions\`처럼 인증이 필요한 endpoint를 가정하세요.
- reference_solution은 OkHttp \`Authenticator\` 또는 Retrofit \`Interceptor\` 코드 + 안전 저장
  코드(\`EncryptedSharedPreferences\` 사용 예)를 함께 보여주세요.
- 면접급 stage 2(tradeoff)는 EncryptedSharedPreferences vs Android Keystore 직접 사용을
  보안 모델/복잡도/지원 버전 측면으로 비교하세요.
- 토큰 자체는 절대 reference 코드에 하드코딩하지 말고 placeholder 사용.`;
}

export const jwtAuthPrompt: TopicPromptModule = {
  topic: 'jwt-auth',
  topicSystemPrompt,
  buildUserPrompt,
};
