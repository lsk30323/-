'use client';

import dynamic from 'next/dynamic';
import { useCallback, useState } from 'react';
import { UI } from '@/lib/ko';

/**
 * Monaco는 브라우저 전용 (window 의존). next/dynamic({ ssr: false })로
 * 서버 렌더 시점엔 스켈레톤만, 클라이언트 hydrate 후 실제 에디터 마운트.
 *
 * Slice 8: Run 버튼은 console.log + 로컬 state 출력 패널만. 실제 Kotlin 실행은
 * Slice 12에서 Judge0 CE로 연결.
 * 자동 저장 (autosave to attempts table)은 Slice 10에서 useDebouncedAutosave로.
 */
const MonacoInner = dynamic(() => import('./monaco-inner'), {
  ssr: false,
  loading: () => (
    <div
      className="flex h-full w-full items-center justify-center bg-bg"
      role="status"
      aria-label="에디터 로딩 중"
    >
      <div className="space-y-2">
        <div className="h-3 w-32 animate-pulse rounded bg-surface" />
        <div className="h-3 w-48 animate-pulse rounded bg-surface" />
        <div className="h-3 w-40 animate-pulse rounded bg-surface" />
      </div>
    </div>
  ),
});

export function EditorPanel({ initialCode = '' }: { initialCode?: string }) {
  const [code, setCode] = useState(initialCode);
  const [output, setOutput] = useState<string | null>(null);

  const handleRun = useCallback(() => {
    const ts = new Date().toISOString().slice(11, 19);
    // Slice 12에서 Judge0 호출로 대체. 지금은 작성한 코드 길이 + console만 노출.
    const summary = `[${ts}] ${UI.editor.runStubLog} (${code.length}자)`;
    console.log('[walkmate-dojo] code length=', code.length, 'preview=', code.slice(0, 60));
    setOutput(summary);
  }, [code]);

  const handleClear = useCallback(() => {
    setOutput(null);
  }, []);

  return (
    <section
      className="flex h-full flex-col rounded-card bg-surface ring-1 ring-subtle/40"
      aria-label={UI.editor.panelLabel}
    >
      {/* Toolbar */}
      <header className="flex items-center justify-between border-b border-subtle/30 px-4 py-2">
        <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-subtle">
          {UI.editor.languageLabel}
        </p>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleRun}
            className="rounded-md border border-accent/60 bg-accent/10 px-3 py-1 font-mono text-xs text-accent-hi transition hover:bg-accent hover:text-bg focus:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-surface"
          >
            {UI.editor.run}
          </button>
        </div>
      </header>

      {/* Editor */}
      <div className="min-h-[420px] flex-1">
        <MonacoInner value={code} onChange={setCode} ariaLabel={UI.editor.panelLabel} />
      </div>

      {/* Output panel */}
      <footer className="border-t border-subtle/30 bg-bg/70 px-4 py-3">
        <div className="flex items-center justify-between">
          <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-subtle">
            {UI.editor.outputLabel}
          </p>
          {output && (
            <button
              type="button"
              onClick={handleClear}
              className="font-mono text-[10px] uppercase tracking-wider text-subtle hover:text-accent"
            >
              {UI.editor.clearOutput}
            </button>
          )}
        </div>
        <pre
          className="mt-2 min-h-[2.5rem] overflow-auto whitespace-pre-wrap font-mono text-xs text-fg/80"
          aria-live="polite"
        >
          {output ?? UI.editor.outputPlaceholder}
        </pre>
      </footer>
    </section>
  );
}
