import Link from 'next/link';

export default function HomePage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-4xl flex-col justify-center px-6 py-16">
      <p className="font-mono text-xs uppercase tracking-[0.2em] text-subtle">
        Slice 01 · scaffolding
      </p>
      <h1 className="mt-4 font-display text-6xl leading-[1.05] text-fg">
        WalkMate
        <br />
        <span className="text-accent">Coding Dojo</span>
      </h1>
      <p className="mt-6 max-w-prose text-lg leading-relaxed text-muted">
        워크온 면접 준비용 안드로이드/Kotlin 코딩 문제 생성기.
        6개 토픽 × 3 난이도, 4단계 점진 힌트, 인터뷰 모의 모드.
      </p>

      <div className="mt-10 flex flex-wrap gap-4">
        <Link
          href="/test-fonts"
          className="inline-flex items-center rounded-card bg-accent px-5 py-2.5 font-medium text-bg transition hover:bg-accent-hi"
        >
          폰트 확인 →
        </Link>
        <span className="inline-flex items-center rounded-card bg-surface px-5 py-2.5 text-muted ring-1 ring-subtle">
          Slice 02부터 도장(/dojo) 추가 예정
        </span>
      </div>

      <footer className="mt-24 font-mono text-xs text-subtle">
        Next.js 16 · React 19 · Tailwind v4 · Claude Sonnet 4.6
      </footer>
    </main>
  );
}
