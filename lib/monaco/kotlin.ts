import type * as Monaco from 'monaco-editor';

/**
 * Kotlin은 Monaco 기본 언어가 아니므로 mount 시점에 직접 등록.
 * Monarch 토큰화 규칙 (TextMate 스타일 정규식 매칭)으로 80~90% 수준의 syntax
 * highlighting + bracket matching + auto-close를 제공합니다.
 *
 * 참고: 의미 분석(LSP)은 미지원 — 자동완성·이름 변경 같은 IDE 기능은 없음.
 * 본 도장은 코드 작성+읽기 위주라 충분.
 */

export const KOTLIN_LANGUAGE_ID = 'kotlin';

const keywords: readonly string[] = [
  // 선언
  'fun', 'val', 'var', 'class', 'object', 'interface', 'enum', 'sealed',
  'data', 'inline', 'infix', 'operator', 'tailrec', 'suspend', 'lateinit',
  'abstract', 'final', 'open', 'override', 'public', 'private', 'protected', 'internal',
  'package', 'import', 'typealias',
  // 연산·관계 키워드
  'as', 'is', 'in', 'out', 'by', 'where',
  // 제어 흐름
  'if', 'else', 'when', 'for', 'while', 'do', 'return', 'throw', 'try', 'catch', 'finally',
  'break', 'continue',
  // 리터럴/특수 식별자
  'this', 'super', 'null', 'true', 'false',
  // soft keywords
  'companion', 'init', 'constructor',
  'expect', 'actual', 'reified', 'noinline', 'crossinline',
  'get', 'set', 'field', 'value', 'vararg',
  'context', 'dynamic',
];

const builtinTypes: readonly string[] = [
  // 기본 타입
  'Int', 'Long', 'Short', 'Byte', 'Float', 'Double', 'Boolean', 'Char',
  'String', 'Unit', 'Nothing', 'Any', 'Number',
  // 컬렉션
  'Array', 'List', 'MutableList', 'Map', 'MutableMap', 'Set', 'MutableSet',
  'Collection', 'MutableCollection', 'Iterable', 'Iterator', 'MutableIterator',
  'Pair', 'Triple', 'Sequence',
  // 코루틴/Flow
  'Flow', 'StateFlow', 'SharedFlow', 'MutableStateFlow', 'MutableSharedFlow',
  'CoroutineScope', 'CoroutineContext', 'Job', 'Deferred', 'Mutex', 'Channel',
  'SupervisorJob', 'Dispatchers',
  // 결과 / 예외
  'Result', 'Throwable', 'Exception', 'Error',
  // 안드로이드 자주 등장
  'Context', 'Activity', 'Fragment', 'Intent', 'Bundle', 'View',
  'ViewModel', 'LiveData', 'MutableLiveData', 'SavedStateHandle',
  'Composable', 'Modifier',
];

const builtinFunctions: readonly string[] = [
  'println', 'print', 'arrayOf', 'listOf', 'mutableListOf', 'setOf', 'mutableSetOf',
  'mapOf', 'mutableMapOf', 'sequenceOf', 'emptyList', 'emptyMap', 'emptySet',
  'requireNotNull', 'checkNotNull', 'require', 'check', 'error', 'TODO',
  'lazy', 'lazyOf', 'with', 'apply', 'also', 'let', 'run', 'takeIf', 'takeUnless',
  'launch', 'async', 'runBlocking', 'coroutineScope', 'supervisorScope', 'withContext',
  'flow', 'flowOf', 'callbackFlow', 'channelFlow',
];

export function registerKotlin(monaco: typeof Monaco): void {
  if (monaco.languages.getLanguages().some((l) => l.id === KOTLIN_LANGUAGE_ID)) {
    return;
  }

  monaco.languages.register({
    id: KOTLIN_LANGUAGE_ID,
    extensions: ['.kt', '.kts'],
    aliases: ['Kotlin', 'kotlin', 'kt'],
    mimetypes: ['text/x-kotlin'],
  });

  monaco.languages.setLanguageConfiguration(KOTLIN_LANGUAGE_ID, {
    comments: { lineComment: '//', blockComment: ['/*', '*/'] },
    brackets: [
      ['{', '}'],
      ['[', ']'],
      ['(', ')'],
    ],
    autoClosingPairs: [
      { open: '{', close: '}' },
      { open: '[', close: ']' },
      { open: '(', close: ')' },
      { open: '"', close: '"', notIn: ['string'] },
      { open: "'", close: "'", notIn: ['string', 'comment'] },
      { open: '`', close: '`', notIn: ['string', 'comment'] },
    ],
    surroundingPairs: [
      { open: '{', close: '}' },
      { open: '[', close: ']' },
      { open: '(', close: ')' },
      { open: '"', close: '"' },
      { open: "'", close: "'" },
      { open: '`', close: '`' },
    ],
    indentationRules: {
      increaseIndentPattern: /^.*\{[^}"']*$/,
      decreaseIndentPattern: /^\s*\}/,
    },
  });

  monaco.languages.setMonarchTokensProvider(KOTLIN_LANGUAGE_ID, {
    defaultToken: '',
    tokenPostfix: '.kt',

    keywords: [...keywords],
    builtinTypes: [...builtinTypes],
    builtinFunctions: [...builtinFunctions],
    operators: [
      '+', '-', '*', '/', '%', '=', '==', '===', '!=', '!==',
      '<', '>', '<=', '>=', '&&', '||', '!', '+=', '-=', '*=', '/=', '%=',
      '?', '?:', '?.', '!!', '::', '->', '..', '...', '&', '|', '^',
    ],

    symbols: /[=><!~?:&|+\-*/^%]+/,
    escapes: /\\(?:[abfnrtv0\\"'$]|u[0-9A-Fa-f]{4})/,

    tokenizer: {
      root: [
        // KDoc
        [/\/\*\*(?!\/)/, 'comment.doc', '@kdoc'],
        // Block comment
        [/\/\*/, 'comment', '@blockcomment'],
        // Line comment
        [/\/\/.*$/, 'comment'],

        // Annotations
        [/@[a-zA-Z_][\w]*(?:\.[a-zA-Z_][\w]*)*/, 'annotation'],

        // Multi-line string """..."""
        [/"""/, 'string', '@multistring'],
        // Single-line string
        [/"/, 'string', '@string'],
        // Char literal
        [/'/, 'string', '@charliteral'],
        // Backticked identifier
        [/`[^`]+`/, 'identifier'],

        // Numbers
        [/0[xX][0-9a-fA-F][0-9a-fA-F_]*[uU]?[Ll]?/, 'number.hex'],
        [/0[bB][01][01_]*[uU]?[Ll]?/, 'number.binary'],
        [/\d[\d_]*\.\d[\d_]*(?:[eE][+-]?\d+)?[fFdD]?/, 'number.float'],
        [/\d[\d_]*[eE][+-]?\d+[fFdD]?/, 'number.float'],
        [/\d[\d_]*[uU]?[Ll]?/, 'number'],

        // Identifiers / keywords
        [
          /[a-zA-Z_$][\w$]*/,
          {
            cases: {
              '@keywords': 'keyword',
              '@builtinTypes': 'type',
              '@builtinFunctions': 'predefined',
              '[A-Z][\\w$]*': 'type.identifier',
              '@default': 'identifier',
            },
          },
        ],

        // Whitespace
        [/[ \t\r\n]+/, 'white'],

        // Brackets
        [/[{}()[\]]/, '@brackets'],

        // Operators
        [
          /@symbols/,
          {
            cases: {
              '@operators': 'operator',
              '@default': '',
            },
          },
        ],

        [/[;,.]/, 'delimiter'],
      ],

      kdoc: [
        [/[^/*@]+/, 'comment.doc'],
        [/@[a-zA-Z]+/, 'comment.doc.tag'],
        [/\*\//, 'comment.doc', '@pop'],
        [/[/*]/, 'comment.doc'],
      ],

      blockcomment: [
        [/[^/*]+/, 'comment'],
        [/\*\//, 'comment', '@pop'],
        [/[/*]/, 'comment'],
      ],

      string: [
        [/[^\\"$]+/, 'string'],
        [/@escapes/, 'string.escape'],
        [/\$\{/, { token: 'string.interpolation', next: '@interp' }],
        [/\$[a-zA-Z_][\w]*/, 'string.interpolation'],
        [/\\./, 'string.escape.invalid'],
        [/"/, 'string', '@pop'],
      ],

      multistring: [
        [/[^"$]+/, 'string'],
        [/\$\{/, { token: 'string.interpolation', next: '@interp' }],
        [/\$[a-zA-Z_][\w]*/, 'string.interpolation'],
        [/"""/, 'string', '@pop'],
        [/"/, 'string'],
      ],

      charliteral: [
        [/[^\\']+/, 'string'],
        [/@escapes/, 'string.escape'],
        [/\\./, 'string.escape.invalid'],
        [/'/, 'string', '@pop'],
      ],

      // ${...} 안에서는 일반 토큰화 — 단순화하여 } 만 매칭
      interp: [
        [/\}/, { token: 'string.interpolation', next: '@pop' }],
        { include: 'root' },
      ],
    },
  });
}
