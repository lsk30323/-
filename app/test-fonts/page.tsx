import Link from 'next/link';

const KOTLIN_SAMPLE = `class StepCounter(private val source: Flow<Long>) {
    val daily: StateFlow<Long> = source
        .scan(0L) { acc, v -> acc + v }
        .stateIn(scope, SharingStarted.Eagerly, 0L)
}`;

export default function TestFontsPage() {
  return (
    <main className="mx-auto max-w-4xl px-6 py-16">
      <Link
        href="/"
        className="font-mono text-xs uppercase tracking-[0.2em] text-subtle hover:text-accent"
      >
        ← 홈
      </Link>

      <h1 className="mt-6 font-display text-5xl text-fg">폰트 확인</h1>
      <p className="mt-2 text-muted">
        세 가지 폰트가 모두 로드되어야 Slice 1이 통과입니다.
      </p>

      <section className="mt-12 space-y-12">
        {/* IBM Plex Sans KR */}
        <article className="rounded-card bg-surface p-6 ring-1 ring-subtle">
          <header className="flex items-baseline justify-between">
            <h2 className="font-display text-2xl text-accent">IBM Plex Sans KR</h2>
            <code className="font-mono text-xs text-subtle">--font-sans-kr</code>
          </header>
          <div className="mt-6 space-y-3 font-sans">
            <p className="text-3xl font-bold">한글 본문 — 안드로이드 면접 준비</p>
            <p className="text-xl font-medium">중간 굵기 — 코루틴과 StateFlow를 활용한 상태 관리</p>
            <p className="text-base font-normal">
              일반 본문 — 사용자의 일일 걸음 수 시계열 데이터를 효율적으로 집계하고,
              백그라운드에서도 정확한 카운팅이 유지되도록 설계하시오.
            </p>
            <p className="text-sm font-light">
              가벼운 문구 — Light weight 300, ABCDEFG 0123456789 가나다라마바사
            </p>
          </div>
        </article>

        {/* Instrument Serif */}
        <article className="rounded-card bg-surface p-6 ring-1 ring-subtle">
          <header className="flex items-baseline justify-between">
            <h2 className="font-display text-2xl text-accent">Instrument Serif</h2>
            <code className="font-mono text-xs text-subtle">--font-serif</code>
          </header>
          <div className="mt-6 space-y-3 font-display">
            <p className="text-6xl leading-[1.05]">Coding Dojo</p>
            <p className="text-4xl">Walk with intention.</p>
            <p className="text-xl italic">
              Hero & display headings — 문제 제목, 챕터 헤더에 사용
            </p>
          </div>
        </article>

        {/* JetBrains Mono */}
        <article className="rounded-card bg-surface p-6 ring-1 ring-subtle">
          <header className="flex items-baseline justify-between">
            <h2 className="font-display text-2xl text-accent">JetBrains Mono</h2>
            <code className="font-mono text-xs text-subtle">--font-mono-jb</code>
          </header>
          <pre className="mt-6 overflow-x-auto rounded-md bg-surface-2 p-4 font-mono text-sm leading-relaxed text-fg">
            <code>{KOTLIN_SAMPLE}</code>
          </pre>
          <p className="mt-4 font-mono text-xs uppercase tracking-[0.2em] text-subtle">
            tabular-nums · 00:14:32 · 1234567890
          </p>
        </article>
      </section>

      <section className="mt-12 rounded-card bg-surface p-6 ring-1 ring-subtle">
        <h2 className="font-display text-2xl text-fg">팔레트 확인</h2>
        <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Swatch label="bg" value="#0a0908" className="bg-bg" />
          <Swatch label="surface" value="#14110f" className="bg-surface" />
          <Swatch label="surface-2" value="#1a1512" className="bg-surface-2" />
          <Swatch label="fg" value="#f5e9d7" className="bg-fg" textClassName="text-bg" />
          <Swatch label="muted" value="#a89683" className="bg-muted" textClassName="text-bg" />
          <Swatch label="subtle" value="#6a5d4d" className="bg-subtle" />
          <Swatch label="accent" value="#d4a574" className="bg-accent" textClassName="text-bg" />
          <Swatch label="danger" value="#c87060" className="bg-danger" textClassName="text-bg" />
        </div>
      </section>
    </main>
  );
}

function Swatch({
  label,
  value,
  className,
  textClassName = 'text-fg',
}: {
  label: string;
  value: string;
  className: string;
  textClassName?: string;
}) {
  return (
    <div className={`rounded-card p-4 ring-1 ring-subtle ${className} ${textClassName}`}>
      <div className="font-mono text-xs uppercase tracking-wider">{label}</div>
      <div className="mt-1 font-mono text-xs opacity-70">{value}</div>
    </div>
  );
}
