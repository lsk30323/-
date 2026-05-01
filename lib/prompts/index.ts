import type { Difficulty, Topic } from '@/db/schema';
import {
  composeSystemPrompt,
  type TopicPromptModule,
} from './_shared';
import { coroutinesStateflowPrompt } from './coroutines-stateflow';
import { foregroundServicePrompt } from './foreground-service';
import { jwtAuthPrompt } from './jwt-auth';
import { roomDbPrompt } from './room-db';
import { mongodbSchemaPrompt } from './mongodb-schema';
import { jetpackComposePrompt } from './jetpack-compose';

/**
 * Topic → prompt module 레지스트리.
 * `Record<Topic, TopicPromptModule>`이라 누락된 토픽이 있으면 TS 에러로 잡힙니다.
 */
export const TOPIC_PROMPTS: Record<Topic, TopicPromptModule> = {
  'coroutines-stateflow': coroutinesStateflowPrompt,
  'foreground-service': foregroundServicePrompt,
  'jwt-auth': jwtAuthPrompt,
  'room-db': roomDbPrompt,
  'mongodb-schema': mongodbSchemaPrompt,
  'jetpack-compose': jetpackComposePrompt,
};

export type ResolvedPrompt = {
  /** Anthropic messages.create의 `system` 필드에 그대로 사용 */
  system: string;
  /** user role messages의 첫 텍스트 블록에 그대로 사용 */
  user: string;
  /** 디버깅·로깅용 메타 */
  meta: { topic: Topic; difficulty: Difficulty };
};

/**
 * (topic, difficulty)을 받아 system + user 메시지를 합성합니다.
 * Slice 5의 `/api/generate-problem` 라우트가 이 헬퍼를 호출.
 */
export function getPromptFor(topic: Topic, difficulty: Difficulty): ResolvedPrompt {
  const mod = TOPIC_PROMPTS[topic];
  return {
    system: composeSystemPrompt(mod.topicSystemPrompt),
    user: mod.buildUserPrompt(difficulty),
    meta: { topic, difficulty },
  };
}

export { composeSystemPrompt, SYSTEM_PROMPT_BASE, TOPIC_LABELS } from './_shared';
export type { TopicPromptModule } from './_shared';
