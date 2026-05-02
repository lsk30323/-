import { z } from 'zod';
import type Anthropic from '@anthropic-ai/sdk';
import { TOPICS, DIFFICULTIES } from '@/db/schema';

/* ───── API request schemas ───── */

/**
 * POST /api/generate-problem 바디.
 * mode='json'은 단일 응답 (Slice 5). 'stream'은 후속 슬라이스에서 SSE 추가.
 */
export const generateProblemBody = z.object({
  topic: z.enum(TOPICS),
  difficulty: z.enum(DIFFICULTIES),
  mode: z.enum(['json', 'stream']).default('json'),
});
export type GenerateProblemBody = z.infer<typeof generateProblemBody>;

/* ───── 모델이 emit하는 problem 객체 (defensive 검증) ───── */

const hintStage = z.object({
  stage: z.union([z.literal(1), z.literal(2), z.literal(3), z.literal(4)]),
  kind: z.enum(['decision', 'tradeoff', 'comprehension', 'extension']),
  question: z.string().min(1),
  options: z.array(z.string()).optional(),
  rationale: z.string().min(1),
});

const referenceSolution = z.object({
  language: z.literal('kotlin'),
  code: z.string().min(1),
  explanation: z.string().min(1),
  complexity: z.object({
    time: z.string(),
    space: z.string(),
  }),
});

/**
 * 모델 응답 검증 — Anthropic이 schema-conforming JSON을 거의 항상 주지만
 * 프로덕션 안정성을 위해 zod로 한 번 더 검증한 뒤 DB에 저장합니다.
 */
export const emittedProblem = z.object({
  title: z.string().min(1),
  description: z.string().min(1),
  difficulty: z.enum(DIFFICULTIES),
  topic: z.enum(TOPICS),
  hints: z.array(hintStage).length(4),
  reference_solution: referenceSolution,
  tags: z.array(z.string()).default([]),
});
export type EmittedProblem = z.infer<typeof emittedProblem>;

/* ───── Anthropic Tool Use 정의 ───── */

/**
 * `tool_choice: { type: 'tool', name: 'emit_problem' }`로 강제 호출하는 도구.
 * input_schema는 JSON Schema (zod와 별도 — Anthropic은 JSON Schema만 받음).
 */
export const emitProblemTool: Anthropic.Tool = {
  name: 'emit_problem',
  description: 'Emit one Android/Kotlin coding interview problem in the strict schema.',
  input_schema: {
    type: 'object',
    properties: {
      title: { type: 'string' },
      description: { type: 'string' },
      difficulty: { type: 'string', enum: [...DIFFICULTIES] },
      topic: { type: 'string', enum: [...TOPICS] },
      hints: {
        type: 'array',
        minItems: 4,
        maxItems: 4,
        items: {
          type: 'object',
          properties: {
            stage: { type: 'integer', enum: [1, 2, 3, 4] },
            kind: {
              type: 'string',
              enum: ['decision', 'tradeoff', 'comprehension', 'extension'],
            },
            question: { type: 'string' },
            options: { type: 'array', items: { type: 'string' } },
            rationale: { type: 'string' },
          },
          required: ['stage', 'kind', 'question', 'rationale'],
          additionalProperties: false,
        },
      },
      reference_solution: {
        type: 'object',
        properties: {
          language: { type: 'string', enum: ['kotlin'] },
          code: { type: 'string' },
          explanation: { type: 'string' },
          complexity: {
            type: 'object',
            properties: {
              time: { type: 'string' },
              space: { type: 'string' },
            },
            required: ['time', 'space'],
            additionalProperties: false,
          },
        },
        required: ['language', 'code', 'explanation', 'complexity'],
        additionalProperties: false,
      },
      tags: { type: 'array', items: { type: 'string' } },
    },
    required: ['title', 'description', 'difficulty', 'topic', 'hints', 'reference_solution'],
    additionalProperties: false,
  },
};
