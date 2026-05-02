'use client';

import Editor, { type OnMount } from '@monaco-editor/react';
import { useCallback } from 'react';
import { KOTLIN_LANGUAGE_ID, registerKotlin } from '@/lib/monaco/kotlin';
import { defineWarmTheme, WARM_THEME_NAME } from '@/lib/monaco/theme';

/**
 * 실제 Monaco 인스턴스를 호스팅하는 클라이언트 컴포넌트.
 *
 * EditorPanel.tsx에서 next/dynamic({ ssr: false })로만 import해야 합니다 —
 * 직접 server component에서 import하면 window 미정의로 빌드가 깨집니다.
 *
 * onMount 훅에서 (1) Kotlin 언어 등록 (2) warm-dark 테마 정의 + 적용을 수행.
 * Monaco editor.getLanguages()로 중복 등록 방지.
 */
export default function MonacoInner({
  value,
  onChange,
  readOnly = false,
  language = KOTLIN_LANGUAGE_ID,
  ariaLabel,
}: {
  value: string;
  onChange: (v: string) => void;
  readOnly?: boolean;
  language?: string;
  ariaLabel?: string;
}) {
  const handleMount: OnMount = useCallback(
    (editor, monaco) => {
      registerKotlin(monaco);
      defineWarmTheme(monaco);
      monaco.editor.setTheme(WARM_THEME_NAME);
      if (!readOnly) {
        editor.focus();
      }
    },
    [readOnly],
  );

  return (
    <Editor
      height="100%"
      width="100%"
      defaultLanguage={language}
      value={value}
      onChange={(v) => onChange(v ?? '')}
      onMount={handleMount}
      theme={WARM_THEME_NAME}
      options={{
        readOnly,
        ariaLabel,
        fontFamily: 'JetBrains Mono, ui-monospace, "Fira Code", monospace',
        fontSize: 14,
        lineHeight: 22,
        minimap: { enabled: false },
        smoothScrolling: true,
        cursorBlinking: 'smooth',
        cursorSmoothCaretAnimation: 'on',
        padding: { top: 16, bottom: 16 },
        scrollBeyondLastLine: false,
        renderLineHighlight: 'all',
        bracketPairColorization: { enabled: true },
        guides: { bracketPairs: true, indentation: true },
        wordWrap: 'on',
        tabSize: 4,
        insertSpaces: true,
        automaticLayout: true,
        scrollbar: { verticalScrollbarSize: 10, horizontalScrollbarSize: 10 },
      }}
    />
  );
}
