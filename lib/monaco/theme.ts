import type * as Monaco from 'monaco-editor';

/**
 * 워크온 도장 warm-dark 테마.
 * app/globals.css의 Tailwind v4 토큰과 색상 팔레트가 일치합니다 — 디자인 시스템 통일.
 *
 * 주요 매핑:
 *   keyword/type → accent (#d4a574 / #e8b988) — 강조
 *   string/number → success (#b8c994) — 데이터 톤
 *   comment       → subtle (#6a5d4d) — 본문 흐름 방해 X
 *   annotation    → danger (#c87060) — "이건 메타다" 시각 신호
 */

export const WARM_THEME_NAME = 'walkmate-warm-dark';

export function defineWarmTheme(monaco: typeof Monaco): void {
  monaco.editor.defineTheme(WARM_THEME_NAME, {
    base: 'vs-dark',
    inherit: true,
    rules: [
      { token: '', foreground: 'f5e9d7' },

      { token: 'comment', foreground: '6a5d4d', fontStyle: 'italic' },
      { token: 'comment.doc', foreground: '8c7860', fontStyle: 'italic' },
      { token: 'comment.doc.tag', foreground: 'd4a574', fontStyle: 'italic' },

      { token: 'keyword', foreground: 'd4a574', fontStyle: 'bold' },

      { token: 'type', foreground: 'e8b988' },
      { token: 'type.identifier', foreground: 'e8b988' },

      { token: 'identifier', foreground: 'f5e9d7' },
      { token: 'predefined', foreground: 'd4a574' },

      { token: 'number', foreground: 'b8c994' },
      { token: 'number.hex', foreground: 'b8c994' },
      { token: 'number.binary', foreground: 'b8c994' },
      { token: 'number.float', foreground: 'b8c994' },

      { token: 'string', foreground: 'b8c994' },
      { token: 'string.escape', foreground: 'd4a574' },
      { token: 'string.escape.invalid', foreground: 'c87060' },
      { token: 'string.interpolation', foreground: 'e8b988' },

      { token: 'annotation', foreground: 'c87060' },

      { token: 'operator', foreground: 'a89683' },
      { token: 'delimiter', foreground: 'a89683' },
      { token: 'delimiter.bracket', foreground: 'f5e9d7' },
    ],
    colors: {
      'editor.background': '#0a0908',
      'editor.foreground': '#f5e9d7',

      'editorLineNumber.foreground': '#6a5d4d',
      'editorLineNumber.activeForeground': '#d4a574',

      'editor.lineHighlightBackground': '#14110f',
      'editor.lineHighlightBorder': '#14110f',

      'editor.selectionBackground': '#d4a57440',
      'editor.inactiveSelectionBackground': '#d4a57420',
      'editor.selectionHighlightBackground': '#d4a57420',
      'editor.wordHighlightBackground': '#d4a57420',
      'editor.findMatchBackground': '#d4a57460',
      'editor.findMatchHighlightBackground': '#d4a57430',

      'editorCursor.foreground': '#d4a574',

      'editorWidget.background': '#14110f',
      'editorWidget.border': '#6a5d4d',
      'editorSuggestWidget.background': '#14110f',
      'editorSuggestWidget.foreground': '#f5e9d7',
      'editorSuggestWidget.selectedBackground': '#1a1512',
      'editorSuggestWidget.highlightForeground': '#d4a574',

      'editorIndentGuide.background': '#1a1512',
      'editorIndentGuide.activeBackground': '#3a3026',

      'editorBracketMatch.background': '#d4a57430',
      'editorBracketMatch.border': '#d4a574',

      'editorGutter.background': '#0a0908',

      'scrollbarSlider.background': '#1a151280',
      'scrollbarSlider.hoverBackground': '#1a1512',
      'scrollbarSlider.activeBackground': '#d4a57440',

      'minimap.background': '#0a0908',
    },
  });
}
