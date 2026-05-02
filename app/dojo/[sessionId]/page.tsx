import { eq } from 'drizzle-orm';
import Link from 'next/link';
import { notFound } from 'next/navigation';
import { db } from '@/db';
import { problems, sessions, type Problem, type Session } from '@/db/schema';
import { UI } from '@/lib/ko';
import { StartButton } from './start-button';

export const dynamic = 'force-dynamic';

type Params = Promise<{ sessionId: string }>;

export default async function SessionPage({ params }: { params: Params }) {
  const { sessionId: idStr } = await params;
  const id = Number(idStr);
  if (!Number.isFinite(id) || id <= 0) notFound();

  const [session] = await db.select().from(sessions).where(eq(sessions.id, id)).limit(1);
  if (!session) notFound();

  let problem: Problem | null = null;
  if (session.problemId !== null) {
    const [p] = await db
      .select()
      .from(problems)
      .where(eq(problems.id, session.problemId))
      .limit(1);
    problem = p ?? null;
  }

  return (
    <main className="mx-auto max-w-3xl px-6 py-12">
      <Link
        href="/"
        className="font-mono text-xs uppercase tracking-[0.2em] text-subtle hover:text-accent"
      >
        {UI.dojo.backToLanding}
      </Link>

      <SessionMeta session={session} />

      {problem ? <ProblemView problem={problem} /> : <ReadyToStart sessionId={id} />}
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
    <article className="mt-10">
      <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-accent">
        {UI.session.problemHeading}
      </p>
      <h1 className="mt-2 font-display text-5xl leading-[1.1] text-fg">{problem.title}</h1>

      <section className="mt-8">
        <h2 className="sr-only">{UI.session.descriptionHeading}</h2>
        <div className="whitespace-pre-wrap text-base leading-relaxed text-fg/90">
          {problem.description}
        </div>
      </section>

      {problem.tags.length > 0 && (
        <section className="mt-8">
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
