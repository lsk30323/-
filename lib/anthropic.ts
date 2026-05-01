import 'server-only';
import Anthropic from '@anthropic-ai/sdk';

declare global {
  var __anthropic: Anthropic | undefined;
}

/**
 * 싱글톤 Anthropic 클라이언트.
 * - 새 클라이언트를 직접 생성하지 말고 항상 이 export를 사용.
 * - dev hot-reload 중복 생성 방지를 위해 globalThis에 캐시.
 *
 * SDK 생성자에 `apiKey: undefined`를 넘겨도 throw하지 않고, 첫 API 호출
 * 시점에 SDK가 한국어가 아닌 에러를 던집니다. 라우트 핸들러는 anthropic
 * 호출을 try/catch로 감싸 한국어 에러 메시지로 변환하세요.
 */
export const anthropic: Anthropic =
  globalThis.__anthropic ?? new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });

if (process.env.NODE_ENV !== 'production') {
  globalThis.__anthropic = anthropic;
}

/**
 * 라우트에서 키 미설정 케이스를 503 + 한국어 메시지로 변환할 때 사용.
 */
export function isAnthropicConfigured(): boolean {
  return Boolean(process.env.ANTHROPIC_API_KEY);
}
