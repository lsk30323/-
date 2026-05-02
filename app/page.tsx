import Link from 'next/link';
import { TOPICS, DIFFICULTIES, type Difficulty, type Topic } from '@/db/schema';
import { UI } from '@/lib/ko';

export default function HomePage() {
  return (
    <main className="mx-auto max-w-6xl px-6 pb-24 pt-16">
      {/* Hero */}
      <section>
        <p className="font-mono text-xs uppercase tracking-[0.2em] text-subtle">
          {UI.app.tagline}
        </p>
        <h1 className="mt-4 font-display text-7xl leading-[1.02] tracking-tight text-fg">
          {UI.landing.heroLine1}
          <br />
          <span className="text-accent">{UI.landing.heroLine2}</span>
        </h1>
        <p className="mt-8 max-w-2xl text-lg leading-relaxed text-fg/85">
          {UI.landing.heroSubtitle}
        </p>
        <p className="mt-3 max-w-2xl text-base leading-relaxed text-muted">
          {UI.landing.heroBody}
        </p>
      </section>

      {/* Topics grid */}
      <section className="mt-20">
        <h2 className="font-display text-3xl text-fg">{UI.landing.topicsHeading}</h2>
        <p className="mt-2 text-muted">{UI.landing.topicsSubheading}</p>

        <ul className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {TOPICS.map((topic) => (
            <TopicCard key={topic} topic={topic} />
          ))}
        </ul>
      </section>

      {/* Footer */}
      <footer className="mt-24 flex flex-col gap-4 border-t border-subtle/30 pt-8 text-xs text-subtle sm:flex-row sm:items-center sm:justify-between">
        <p className="leading-relaxed">{UI.landing.footerNote}</p>
        <p className="font-mono">{UI.meta.footer}</p>
      </footer>

      {/* dev links — 프로덕션에선 hidden */}
      {process.env.NODE_ENV !== 'production' && (
        <aside className="mt-8 flex items-center gap-3 text-xs text-subtle">
          <span className="font-mono uppercase tracking-wider">{UI.landing.devLinks}:</span>
          <Link href="/test-fonts" className="underline hover:text-accent">
            {UI.landing.devTestFonts}
          </Link>
        </aside>
      )}
    </main>
  );
}

function TopicCard({ topic }: { topic: Topic }) {
  const t = UI.topics[topic];
  return (
    <li className="group flex flex-col rounded-card bg-surface p-6 ring-1 ring-subtle/40 transition-colors hover:ring-accent/60">
      <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-subtle">
        {t.tagline}
      </p>
      <h3 className="mt-2 font-display text-2xl text-fg group-hover:text-accent-hi">
        {t.name}
      </h3>
      <p className="mt-3 grow text-sm leading-relaxed text-muted">{t.description}</p>

      <div className="mt-6 flex flex-wrap gap-2">
        {DIFFICULTIES.map((d) => (
          <DifficultyButton key={d} topic={topic} difficulty={d} />
        ))}
      </div>
    </li>
  );
}

function DifficultyButton({ topic, difficulty }: { topic: Topic; difficulty: Difficulty }) {
  const d = UI.difficulties[difficulty];
  const href = `/dojo?topic=${encodeURIComponent(topic)}&difficulty=${encodeURIComponent(difficulty)}`;

  // tone별 스타일 — accent는 입문/중급, 면접급은 강조
  const className =
    difficulty === '면접급'
      ? 'border-accent/60 bg-accent/10 text-accent-hi hover:bg-accent hover:text-bg'
      : 'border-subtle/50 bg-surface-2 text-fg hover:border-accent hover:text-accent';

  return (
    <Link
      href={href}
      title={d.description}
      aria-label={`${UI.topics[topic].name} · ${d.label}: ${d.description}`}
      className={`inline-flex items-center rounded-md border px-3 py-1.5 text-sm font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-bg ${className}`}
    >
      {d.label}
    </Link>
  );
}
