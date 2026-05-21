import { and, desc, eq } from 'drizzle-orm';
import Link from 'next/link';
import { notFound } from 'next/navigation';
import { db } from '@/db';
import {
  attempts,
  problems,
  sessions,
  type Attempt,
  type Problem,
  type Session,
} from '@/db/schema';
import { EditorPanel } from '@/components/editor/EditorPanel';
import { HintLadder } from '@/components/hint/HintLadder';
import { InterviewSession } from '@/components/interview/InterviewSession';
import { UI } from '@/lib/ko';
import { StartButton } from './start-button';

export const dynamic = 'force-dynamic';

type Params = Promise<{ sessionId: string }>;

const STARTER_CODE = `// 답안을 이곳에 작성하세요.
// 예: ViewModel + StateFlow를 사용하는 fun ...

`;

export default async function SessionPage({ params }: { params: Params }) {
  const { sessionId: idStr } = await params;
  const id = Number(idStr);
  if (!Number.isFinite(id) || id <= 0) notFound();

  const [session] = await db.select().from(sessions).where(eq(sessions.id, id)).limit(1);
  if (!session) notFound();

  let problem: Problem | null = null;
  let inProgress: Attempt | null = null;
  let completed: Attempt | null = null;
  if (session.problemId !== null) {
    const [p] = await db
      .select()
      .from(problems)
      .where(eq(problems.id, session.problemId))
      .limit(1);
    problem = p ?? null;

    /* in-progress attempt → hint reveal 시드 + autosave된 code 시드 */
    const [att] = await db
      .select()
      .from(attempts)
      .where(and(eq(attempts.sessionId, id), eq(attempts.completed, false)))
      .orderBy(desc(attempts.createdAt))
      .limit(1);
    inProgress = att ?? null;

    /* 이미 제출된 attempt가 있으면 인터뷰는 끝난 상태 */
    const [done] = await db
      .select()
      .from(attempts)
      .where(and(eq(attempts.sessionId, id), eq(attempts.completed, true)))
      .orderBy(desc(attempts.createdAt))
      .limit(1);
    completed = done ?? null;
  }
  const initialHintsViewed = inProgress?.hintsViewed ?? completed?.hintsViewed ?? [];

  /* 문제 미생성: max-w-3xl 좁은 레이아웃 (회수: 안내 + StartButton) */
  if (!problem) {
    return (
      <main className="mx-auto max-w-3xl px-6 py-12">
        <Link
          href="/"
          className="font-mono text-xs uppercase tracking-[0.2em] text-subtle hover:text-accent"
        >
          {UI.dojo.backToLanding}
        </Link>
        <SessionMeta session={session} />
        <ReadyToStart sessionId={id} />
      </main>
    );
  }

  /* 인터뷰 모드: 자체 셸(InterviewSession)에서 nav 숨김 + 타이머 + autosave + 락.
     완료된 attempt가 있어도 같은 컴포넌트가 "제출됨" 분기를 처리합니다. */
  if (session.mode === 'interview' && session.timeLimitMinutes) {
    const initialCode = completed?.code ?? inProgress?.code ?? STARTER_CODE;
    return (
      <InterviewSession
        session={session}
        problem={problem}
        totalSeconds={session.timeLimitMinutes * 60}
        initialCode={initialCode}
        initialHintsViewed={initialHintsViewed}
      />
    );
  }

  /* 연습 모드: 풀폭 사이드바이사이드 (lg+) — 좌:문제+힌트, 우:에디터 */
  const initialCode = inProgress?.code || STARTER_CODE;
  return (
    <main className="mx-auto max-w-7xl px-6 py-8">
      <Link
        href="/"
        className="font-mono text-xs uppercase tracking-[0.2em] text-subtle hover:text-accent"
      >
        {UI.dojo.backToLanding}
      </Link>
      <SessionMeta session={session} />
      <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className="space-y-6 lg:overflow-y-auto lg:max-h-[calc(100vh-12rem)] lg:pr-2">
          <ProblemView problem={problem} />
          <HintLadder
            hints={problem.hints}
            sessionId={id}
            initialRevealed={initialHintsViewed}
          />
        </div>
        <div className="h-[640px] lg:h-[calc(100vh-12rem)] lg:min-h-[480px] lg:sticky lg:top-6">
          <EditorPanel initialCode={initialCode} />
        </div>
      </div>
    </main>
  );
}

function SessionMeta({ session }: { session: Session }) {
  const topicName = session.topic ? UI.topics[session.topic].name : UI.session.notSet;
  const difficultyLabel = session.difficulty
    ? UI.difficulties[session.difficulty].label
    : UI.session.notSet;
  const modeLabel =
    session.mode === 'interview' ? UI.session.interviewMode : UI.session.practiceMode;
  const timeLabel =
    session.timeLimitMinutes !== null
      ? `${session.timeLimitMinutes}${UI.session.timeMinutesUnit}`
      : UI.session.notSet;

  return (
    <section
      className="mt-6 rounded-card bg-surface p-6 ring-1 ring-subtle/40"
      aria-label={UI.session.sessionInfoHeading}
    >
      <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-subtle">
        {UI.session.breadcrumb} #{session.id}
      </p>
      <dl className="mt-3 grid gap-x-8 gap-y-3 text-sm sm:grid-cols-2">
        <MetaRow label={UI.dojo.selectedTopic} value={topicName} />
        <MetaRow label={UI.dojo.selectedDifficulty} value={difficultyLabel} />
        <MetaRow label={UI.session.modeLabel} value={modeLabel} />
        <MetaRow label={UI.session.timeLimitLabel} value={timeLabel} />
      </dl>
    </section>
  );
}

function MetaRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4 sm:flex-col sm:items-start sm:justify-start">
      <dt className="font-mono text-xs uppercase tracking-wider text-subtle">{label}</dt>
      <dd className="text-fg sm:mt-1 sm:text-base">{value}</dd>
    </div>
  );
}

function ReadyToStart({ sessionId }: { sessionId: number }) {
  return (
    <section className="mt-10">
      <h1 className="font-display text-5xl text-fg">{UI.session.readyHeading}</h1>
      <p className="mt-3 max-w-prose text-muted">{UI.session.readyBody}</p>
      <StartButton sessionId={sessionId} />
    </section>
  );
}

function ProblemView({ problem }: { problem: Problem }) {
  return (
    <article>
      <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-accent">
        {UI.session.problemHeading}
      </p>
      <h1 className="mt-2 font-display text-4xl leading-[1.15] text-fg">{problem.title}</h1>

      <section className="mt-6">
        <h2 className="sr-only">{UI.session.descriptionHeading}</h2>
        <div className="whitespace-pre-wrap text-base leading-relaxed text-fg/90">
          {problem.description}
        </div>
      </section>

      {problem.tags.length > 0 && (
        <section className="mt-6">
          <h2 className="font-mono text-xs uppercase tracking-[0.2em] text-subtle">
            {UI.session.tagsHeading}
          </h2>
          <ul className="mt-3 flex flex-wrap gap-2">
            {problem.tags.map((tag) => (
              <li
                key={tag}
                className="rounded-md border border-subtle/50 bg-surface-2 px-2.5 py-1 font-mono text-xs text-muted"
              >
                {tag}
              </li>
            ))}
          </ul>
        </section>
      )}
    </article>
  );
}
