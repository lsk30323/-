/**
 * Anthropic 모델 ID — 라우트에서 직접 문자열 쓰지 말고 이 상수를 import.
 *
 * - MODEL_SONNET: 기본. 1M context, $3/$15 per MTok. 입문/중급 난이도 문제 생성.
 * - MODEL_OPUS:   면접급 난이도 폴백 (2026-04-16 출시).
 * - MODEL_HAIKU:  빠른 힌트 재생성·간단한 리라이팅용.
 *
 * ❌ `claude-sonnet-4-7`은 존재하지 않음. 절대 사용 금지.
 */
export const MODEL_SONNET = 'claude-sonnet-4-6' as const;
export const MODEL_OPUS = 'claude-opus-4-7' as const;
export const MODEL_HAIKU = 'claude-haiku-4-5' as const;

export type ModelId = typeof MODEL_SONNET | typeof MODEL_OPUS | typeof MODEL_HAIKU;

import type { Difficulty } from '@/db/schema';

/**
 * 난이도 → 모델 매핑.
 * 면접급은 더 깊이 있는 reasoning이 필요하므로 Opus 4.7 사용.
 */
export function modelForDifficulty(difficulty: Difficulty): ModelId {
  return difficulty === '면접급' ? MODEL_OPUS : MODEL_SONNET;
}
