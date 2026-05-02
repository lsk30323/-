import { sql } from 'drizzle-orm';
import { sqliteTable, integer, text, index } from 'drizzle-orm/sqlite-core';

export const TOPICS = [
  'coroutines-stateflow',
  'foreground-service',
  'jwt-auth',
  'room-db',
  'mongodb-schema',
  'jetpack-compose',
] as const;
export type Topic = (typeof TOPICS)[number];

export const DIFFICULTIES = ['입문', '중급', '면접급'] as const;
export type Difficulty = (typeof DIFFICULTIES)[number];

export type HintStage = {
  stage: 1 | 2 | 3 | 4;
  kind: 'decision' | 'tradeoff' | 'comprehension' | 'extension';
  question: string;
  options?: string[];
  rationale: string;
};

export type ReferenceSolution = {
  language: 'kotlin';
  code: string;
  explanation: string;
  complexity: { time: string; space: string };
};

export const problems = sqliteTable(
  'problems',
  {
    id: integer('id').primaryKey({ autoIncrement: true }),
    topic: text('topic', { enum: TOPICS }).notNull(),
    difficulty: text('difficulty', { enum: DIFFICULTIES }).notNull(),
    title: text('title').notNull(),
    description: text('description').notNull(),
    hints: text('hints', { mode: 'json' }).$type<HintStage[]>().notNull(),
    referenceSolution: text('reference_solution', { mode: 'json' })
      .$type<ReferenceSolution>()
      .notNull(),
    tags: text('tags', { mode: 'json' })
      .$type<string[]>()
      .notNull()
      .default(sql`'[]'`),
    createdAt: integer('created_at', { mode: 'timestamp' })
      .notNull()
      .default(sql`(unixepoch())`),
  },
  (t) => [index('problems_topic_idx').on(t.topic, t.difficulty)],
);

export const sessions = sqliteTable('sessions', {
  id: integer('id').primaryKey({ autoIncrement: true }),
  mode: text('mode', { enum: ['practice', 'interview'] }).notNull(),
  topic: text('topic', { enum: TOPICS }),
  difficulty: text('difficulty', { enum: DIFFICULTIES }),
  timeLimitMinutes: integer('time_limit_minutes'),
  problemId: integer('problem_id').references(() => problems.id, { onDelete: 'set null' }),
  createdAt: integer('created_at', { mode: 'timestamp' })
    .notNull()
    .default(sql`(unixepoch())`),
  endedAt: integer('ended_at', { mode: 'timestamp' }),
});

export type ExecutionResult = {
  stdout: string;
  stderr: string;
  status: string;
};

export const attempts = sqliteTable(
  'attempts',
  {
    id: integer('id').primaryKey({ autoIncrement: true }),
    problemId: integer('problem_id')
      .notNull()
      .references(() => problems.id, { onDelete: 'cascade' }),
    sessionId: integer('session_id').references(() => sessions.id, {
      onDelete: 'set null',
    }),
    code: text('code').notNull(),
    timeTakenSeconds: integer('time_taken_seconds').notNull(),
    hintsViewed: text('hints_viewed', { mode: 'json' })
      .$type<number[]>()
      .notNull()
      .default(sql`'[]'`),
    selfRating: integer('self_rating'),
    selfNote: text('self_note'),
    executionResult: text('execution_result', { mode: 'json' }).$type<ExecutionResult | null>(),
    completed: integer('completed', { mode: 'boolean' }).notNull().default(false),
    createdAt: integer('created_at', { mode: 'timestamp' })
      .notNull()
      .default(sql`(unixepoch())`),
  },
  (t) => [
    index('attempts_problem_idx').on(t.problemId),
    index('attempts_session_idx').on(t.sessionId),
  ],
);

export type Problem = typeof problems.$inferSelect;
export type NewProblem = typeof problems.$inferInsert;
export type Session = typeof sessions.$inferSelect;
export type NewSession = typeof sessions.$inferInsert;
export type Attempt = typeof attempts.$inferSelect;
export type NewAttempt = typeof attempts.$inferInsert;
