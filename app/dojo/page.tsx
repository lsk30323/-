import Link from 'next/link';
import { TOPICS, DIFFICULTIES, type Difficulty, type Topic } from '@/db/schema';
import { UI } from '@/lib/ko';

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

function asString(v: string | string[] | undefined): string | undefined {
  return Array.isArray(v) ? v[0] : v;
}

function isTopic(v: string | undefined): v is Topic {
  return v !== undefined && (TOPICS as readonly string[]).includes(v);
}

function isDifficulty(v: string | undefined): v is Difficulty {
  return v !== undefined && (DIFFICULTIES as readonly string[]).includes(v);
}

export default async function DojoPage({
  searchParams,
}: {
  searchParams: SearchParams;
}) {
  const sp = await searchParams;
  const topic = asString(sp.topic);
  const difficulty = asString(sp.difficulty);

  const valid = isTopic(topic) && isDifficulty(difficulty);

  return (
    <main className="mx-auto max-w-3xl px-6 py-16">
      <Link
        href="/"
        className="font-mono text-xs uppercase tracking-[0.2em] text-subtle hover:text-accent"
      >
        {UI.dojo.backToLanding}
      </Link>

      <h1 className="mt-6 font-display text-5xl text-fg">
        {UI.dojo.placeholderTitle}
      </h1>
      <p className="mt-3 max-w-prose text-muted">{UI.dojo.placeholderBody}</p>

      <section className="mt-10 rounded-card bg-surface p-6 ring-1 ring-subtle">
        {valid ? (
          <dl className="grid gap-4 text-sm sm:grid-cols-2">
            <div>
              <dt className="font-mono text-xs uppercase tracking-[0.2em] text-subtle">
                {UI.dojo.selectedTopic}
              </dt>
              <dd className="mt-1 font-display text-2xl text-accent">
                {UI.topics[topic].name}
              </dd>
              <p className="mt-1 text-muted">{UI.topics[topic].tagline}</p>
            </div>
            <div>
              <dt className="font-mono text-xs uppercase tracking-[0.2em] text-subtle">
                {UI.dojo.selectedDifficulty}
              </dt>
              <dd className="mt-1 font-display text-2xl text-fg">
                {UI.difficulties[difficulty].label}
              </dd>
              <p className="mt-1 text-muted">{UI.difficulties[difficulty].description}</p>
            </div>
          </dl>
        ) : (
          <p className="text-danger">{UI.dojo.invalidSelection}</p>
        )}
      </section>
    </main>
  );
}
