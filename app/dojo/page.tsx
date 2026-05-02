'use client';

import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense, useMemo, useState, useTransition } from 'react';
import { TOPICS, DIFFICULTIES, type Difficulty, type Topic } from '@/db/schema';
import { UI } from '@/lib/ko';

type Mode = 'practice' | 'interview';
type TimeLimit = 30 | 45 | 60;

const TIME_OPTIONS: TimeLimit[] = [30, 45, 60];

function isTopic(v: string | null): v is Topic {
  return v !== null && (TOPICS as readonly string[]).includes(v);
}
function isDifficulty(v: string | null): v is Difficulty {
  return v !== null && (DIFFICULTIES as readonly string[]).includes(v);
}

export default function DojoLandingPage() {
  return (
    <Suspense fallback={<DojoLoading />}>
      <DojoLandingInner />
    </Suspense>
  );
}

function DojoLoading() {
  return (
    <main className="mx-auto max-w-3xl px-6 py-16">
      <div className="h-4 w-24 animate-pulse rounded bg-surface" aria-hidden />
      <div className="mt-6 h-12 w-48 animate-pulse rounded bg-surface" aria-hidden />
    </main>
  );
}

function DojoLandingInner() {
  const router = useRouter();
  const sp = useSearchParams();

  const topic = sp.get('topic');
  const difficulty = sp.get('difficulty');
  const valid = useMemo(() => isTopic(topic) && isDifficulty(difficulty), [topic, difficulty]);

  if (!valid || !isTopic(topic) || !isDifficulty(difficulty)) {
    return <PreSelectionRequired />;
  }

  return <ModeSelectionForm topic={topic} difficulty={difficulty} router={router} />;
}

function PreSelectionRequired() {
  return (
    <main className="mx-auto max-w-2xl px-6 py-16">
      <Link
        href="/"
        className="font-mono text-xs uppercase tracking-[0.2em] text-subtle hover:text-accent"
      >
        {UI.dojo.backToLanding}
      </Link>
      <h1 className="mt-6 font-display text-4xl text-fg">{UI.dojo.placeholderTitle}</h1>
      <p className="mt-3 text-danger">{UI.modeSelect.requireTopicAndDifficulty}</p>
    </main>
  );
}

function ModeSelectionForm({
  topic,
  difficulty,
  router,
}: {
  topic: Topic;
  difficulty: Difficulty;
  router: ReturnType<typeof useRouter>;
}) {
  const [mode, setMode] = useState<Mode>('practice');
  const [timeLimit, setTimeLimit] = useState<TimeLimit>(45);
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  const submitLabel =
    mode === 'interview' ? UI.modeSelect.submitInterview : UI.modeSelect.submitPractice;

  const handleSubmit = () => {
    setError(null);
    startTransition(async () => {
      try {
        const res = await fetch('/api/sessions', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            mode,
            topic,
            difficulty,
            ...(mode === 'interview' ? { timeLimitMinutes: timeLimit } : {}),
          }),
        });
        if (!res.ok) {
          setError(UI.modeSelect.networkError);
          return;
        }
        const json = (await res.json()) as { sessionId: number };
        router.push(`/dojo/${json.sessionId}`);
      } catch {
        setError(UI.modeSelect.networkError);
      }
    });
  };

  return (
    <main className="mx-auto max-w-3xl px-6 py-16">
      <Link
        href="/"
        className="font-mono text-xs uppercase tracking-[0.2em] text-subtle hover:text-accent"
      >
        {UI.dojo.backToLanding}
      </Link>

      {/* Selected topic + difficulty (read-only) */}
      <section className="mt-6 rounded-card bg-surface p-6 ring-1 ring-subtle">
        <dl className="grid gap-4 sm:grid-cols-2">
          <ReadField label={UI.dojo.selectedTopic} value={UI.topics[topic].name} sub={UI.topics[topic].tagline} />
          <ReadField
            label={UI.dojo.selectedDifficulty}
            value={UI.difficulties[difficulty].label}
            sub={UI.difficulties[difficulty].description}
          />
        </dl>
      </section>

      {/* Mode selection */}
      <section className="mt-10">
        <h2 className="font-display text-3xl text-fg">{UI.modeSelect.heading}</h2>
        <p className="mt-2 text-muted">{UI.modeSelect.subheading}</p>

        <fieldset className="mt-6 grid gap-4 sm:grid-cols-2">
          <ModeRadio
            value="practice"
            checked={mode === 'practice'}
            onSelect={() => setMode('practice')}
            label={UI.modeSelect.practiceLabel}
            description={UI.modeSelect.practiceDescription}
          />
          <ModeRadio
            value="interview"
            checked={mode === 'interview'}
            onSelect={() => setMode('interview')}
            label={UI.modeSelect.interviewLabel}
            description={UI.modeSelect.interviewDescription}
          />
        </fieldset>
      </section>

      {/* Time limit (only when interview) */}
      {mode === 'interview' && (
        <section className="mt-10">
          <h3 className="font-display text-2xl text-fg">{UI.modeSelect.timeHeading}</h3>
          <fieldset className="mt-4 flex flex-wrap gap-3">
            {TIME_OPTIONS.map((t) => (
              <TimeRadio
                key={t}
                value={t}
                checked={timeLimit === t}
                onSelect={() => setTimeLimit(t)}
                label={`${t}${UI.modeSelect.timeMinutesUnit}`}
              />
            ))}
          </fieldset>
        </section>
      )}

      {error && (
        <p className="mt-6 rounded-md border border-danger/60 bg-danger/10 p-3 text-sm text-danger">
          {error}
        </p>
      )}

      <div className="mt-10 flex items-center gap-4">
        <button
          type="button"
          onClick={handleSubmit}
          disabled={isPending}
          className="inline-flex items-center rounded-card bg-accent px-6 py-3 font-medium text-bg transition hover:bg-accent-hi disabled:cursor-not-allowed disabled:opacity-60"
        >
          {isPending ? UI.modeSelect.submitting : submitLabel}
        </button>
      </div>
    </main>
  );
}

function ReadField({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div>
      <dt className="font-mono text-xs uppercase tracking-[0.2em] text-subtle">{label}</dt>
      <dd className="mt-1 font-display text-2xl text-accent">{value}</dd>
      <p className="mt-1 text-sm text-muted">{sub}</p>
    </div>
  );
}

function ModeRadio({
  value,
  checked,
  onSelect,
  label,
  description,
}: {
  value: Mode;
  checked: boolean;
  onSelect: () => void;
  label: string;
  description: string;
}) {
  return (
    <label
      className={`group flex cursor-pointer flex-col rounded-card border bg-surface p-5 transition-colors ${
        checked ? 'border-accent ring-1 ring-accent' : 'border-subtle/40 hover:border-accent/60'
      }`}
    >
      <input
        type="radio"
        name="mode"
        value={value}
        checked={checked}
        onChange={onSelect}
        className="sr-only"
      />
      <span className="font-display text-2xl text-fg group-hover:text-accent">{label}</span>
      <span className="mt-2 text-sm leading-relaxed text-muted">{description}</span>
    </label>
  );
}

function TimeRadio({
  value,
  checked,
  onSelect,
  label,
}: {
  value: TimeLimit;
  checked: boolean;
  onSelect: () => void;
  label: string;
}) {
  return (
    <label
      className={`inline-flex cursor-pointer items-center rounded-md border px-4 py-2 font-mono text-sm transition-colors ${
        checked
          ? 'border-accent bg-accent/15 text-accent-hi'
          : 'border-subtle/50 bg-surface-2 text-fg hover:border-accent hover:text-accent'
      }`}
    >
      <input
        type="radio"
        name="timeLimit"
        value={value}
        checked={checked}
        onChange={onSelect}
        className="sr-only"
      />
      {label}
    </label>
  );
}
