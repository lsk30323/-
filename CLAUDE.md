# WalkMate Coding Dojo

워크온(WalkOn, 만보기·헬스 앱 회사) 안드로이드 개발자 면접 준비용 코딩 문제 생성기.
Claude API로 6개 토픽(Coroutines/StateFlow, Foreground Service, JWT auth, Room DB,
MongoDB schema, Jetpack Compose) × 3 난이도(입문/중급/면접급) 안드로이드/Kotlin 문제를
즉석 생성하고, 4단계 점진 힌트 시스템 + 인터뷰 모의 모드(타이머)를 제공합니다.

## Stack (verified 2026-04)
- Next.js 16.2 (App Router, Turbopack, Server Actions)
- React 19.2 (use(), useTransition, useOptimistic)
- TypeScript 6.0 strict
- Tailwind CSS v4.2 (CSS-first @theme in app/globals.css)
- Drizzle ORM 0.45.x + @libsql/client 0.17 (로컬: file:./db/local.db, 프로덕션: Turso)
- @anthropic-ai/sdk 0.90 — 기본 모델 claude-sonnet-4-6, 면접급은 claude-opus-4-7
- @monaco-editor/react 4.7 (Kotlin은 자체 Monarch tokenizer)
- zod, vitest, playwright, pnpm

## 디렉토리 맵
- `app/`         — App Router 페이지 + API routes
- `app/api/`     — 서버 전용. Anthropic 호출은 여기서만.
- `components/`  — kebab-case 파일, PascalCase export
- `lib/`         — anthropic, models, prompts, monaco, hooks, ko, validation
- `db/`          — schema, drizzle client, migrations, seed
- `prompts/`     — 토픽별 시스템 프롬프트 TS 모듈

## Commands

```
pnpm dev               # localhost:3000
pnpm typecheck
pnpm lint
pnpm test              # vitest run
pnpm test:e2e          # playwright
pnpm db:generate       # 스키마 변경 후
pnpm db:migrate
pnpm db:studio
pnpm db:seed
pnpm db:setup          # generate + migrate + seed (한 번에)
```

## 셸 환경 — 중요

사용자는 Windows (PowerShell 5.1 디폴트, 7.x 가능). 셸 명령 제안 시:

- **`&&`, `||`, `??` 사용 금지** — PS 7+ 전용. 5.1에서 깨짐.
- 무조건 연결: `;`. 조건부: `if ($LASTEXITCODE -eq 0) { ... }`.
- 환경변수: `$env:NAME = "value"` (export 아님).
- `curl`은 PS에서 `Invoke-WebRequest` 별칭. 진짜 curl은 `curl.exe`, 또는 `Invoke-RestMethod`.
- 멀티스텝은 셸 체이닝 대신 `package.json` script로 캡슐화 (cross-platform).

## Conventions

### Korean UI strings
모든 한국어 UI 문자열은 `lib/ko.ts`의 타입드 객체로:
```ts
export const UI = {
  dojo: { startButton: "도전 시작", giveUp: "포기" },
  hint: { stage1: "1단계 힌트" /* ... */ },
} as const;
```
컴포넌트는 `UI.dojo.startButton`을 import — **인라인 한국어 문자열 금지**.

### Design tokens
`app/globals.css`의 Tailwind v4 `@theme` 블록에 정의됨:
- `--color-bg: #0a0908`     (near-black, dark warm 배경)
- `--color-surface: #14110f`
- `--color-fg: #f5e9d7`     (warm cream 텍스트)
- `--color-accent: #d4a574` (warm amber, 강조·포커스링)
- `--color-danger: #c87060` (muted terracotta — 빨강 X)
- 폰트:
  - `--font-sans` = IBM Plex Sans KR (모든 한국어 UI)
  - `--font-display` = Instrument Serif (Hero, 문제 제목)
  - `--font-mono` = JetBrains Mono (Monaco, 인라인 코드)
- 폰트는 `app/layout.tsx`의 `next/font` 한 군데에서만 import.

### Anthropic SDK
- 싱글톤 `lib/anthropic.ts`만 사용. 새 클라이언트 생성 금지.
- 모델은 `lib/models.ts` 상수로만 참조. 라우트에 모델 문자열 하드코딩 금지.
- 구조화 출력은 **Tool Use forcing** 패턴 (tool_choice: { type: 'tool', name }).
  Reference: @app/api/generate-problem/route.ts
- 스트리밍: `messages.stream()` + ReadableStream + SSE.
- try/catch로 감싸고, 에러 메시지에 ANTHROPIC_API_KEY가 누설되지 않도록 주의.

### Database
- 같은 Drizzle 스키마로 로컬 SQLite와 Turso 모두 운영. `db/index.ts`만 분기.
- 스키마 변경 → `pnpm db:generate` → 생성 SQL 검토 → `pnpm db:migrate`.
- 임의 SQL 스크립트보다 `pnpm db:studio` 사용.

### API routes
- POST 바디는 `lib/validation.ts`의 zod 스키마로 검증.
- 성공: `Response.json({ data })`. 실패: `Response.json({ error }, { status })`.
- vitest 테스트는 `route.test.ts`로 같은 폴더에.

### Code style
Prettier + ESLint를 `.claude/hooks/format-and-typecheck.sh`(PostToolUse 훅)이 처리.
스타일 규칙은 여기에 적지 말 것 — 훅이 결정론적으로 적용.

## 4단계 힌트 철학 (소크라테스식 — 최우선 원칙)

응시자가 막혔을 때 한 번에 하나씩만 공개. 절대 단계를 건너뛰거나 합치지 마세요.

1. **stage 1 — kind="decision"** (폐쇄형 결정 질문, A/B 또는 yes/no).
   options 필드에 선택지, rationale에 정답+이유.
   예: "이 동작을 메인 스레드에서 처리해도 되는가? (예/아니오)"

2. **stage 2 — kind="tradeoff"** (트레이드오프/철학 개방형 질문).
   정답 1개가 없는 설계 사고. rationale에 모범답 핵심 논점.
   예: "Flow vs LiveData를 lifecycle awareness, 테스트 용이성, 결합도 측면에서 비교하라."

3. **stage 3 — kind="comprehension"** (이해 점검).
   응시자가 문제 의도를 정확히 파악했는지 확인. options는 보통 null.
   예: "이 문제에서 메모리 누수가 발생할 수 있는 정확한 시점은?"

4. **stage 4 — kind="extension"** (학습할 추가 개념 1개).
   풀이에 직접 필요하지 않더라도 확장 학습으로 좋은 안드로이드 개념.
   rationale 2~4문장으로 요약.

힌트 프롬프트는 `lib/prompts/_shared.ts`의 페르소나 + 토픽별 프롬프트로 구성.

## 페르소나
페르소나는 워크온의 시니어 안드로이드 면접관 — 시니어가 후배에게 멘토링하는 톤.
한국어가 디폴트, 코드 키워드만 영어. 가능하면 만보기·헬스 도메인 예시
("사용자의 일일 걸음 수 시계열에서…")를 1~2개 사용.

## 인터뷰 모의 모드 (#1 우선 기능)

- 사용자가 30/45/60분 선택 → 문제 1개 잠금 + `useCountdown` 훅으로 카운트다운.
- 색상 phase: calm(>30%) → alert(<30%) → urgent(<10%) → final(<30s, muted red).
- `useDebouncedAutosave` 훅으로 12초마다 attempts 테이블에 코드 자동 저장.
- `useInterviewLock`: beforeunload 핸들러 + 글로벌 nav 숨김 (Next 16 App Router는
  내부 navigation block API가 없으므로 nav를 렌더링하지 않는 인터뷰 셸 사용).
- 만료 시 자동 제출. 리뷰 화면: 헤더(시간) → 코드 → 출력 → 4힌트 unlock(어코디언) →
  레퍼런스 솔루션 → diff editor → self-rating → 액션(저장/재시도/관련 변형).

## Known gotchas
- Monaco는 client-only. `'use client'` 파일에서 `next/dynamic({ ssr: false })`로만 import.
- `@libsql/client`는 Edge·Node 모두 작동 (HTTP). `better-sqlite3`는 Edge X — 사용 X.
- Tailwind v4 `@theme` 블록은 `@import "tailwindcss"` 뒤가 아니라 같은 파일 안에 있어야 토큰 인식.
- Drizzle SQLite의 `mode: 'json'`은 **`text()` 컬럼에만** 적용 가능. `integer()`에 쓰면 TS 에러.
  JSON 배열·객체는 무조건 `text('col', { mode: 'json' }).$type<T>()` 패턴.
- Drizzle 0.45+ 인덱스 콜백은 객체 `{ idx: index(...) }` 대신 **배열** `[index(...)]` 반환.
- Anthropic 스트리밍 on Vercel: `runtime = 'nodejs'` + Fluid Compute (300s) 권장.
  Edge는 25s TTFB 룰 (Anthropic 첫 토큰은 보통 <1s라 OK이지만 안전 마진).
- Kotlin은 Monaco 기본 언어 X. `lib/monaco/kotlin.ts`의 Monarch tokenizer를 mount 시점에 등록.
- Piston 퍼블릭 API는 2026-02-15 폐쇄. 자동 채점은 Judge0 CE(RapidAPI) 사용.
  키 미설정 시 503 + 한국어 에러 메시지 — 수동 비교 모드로 graceful fallback.
- PowerShell 5.1: `&&`/`||`/`??` 금지, `~/` 확장 X (`$HOME` 사용).
- Next.js 16은 Node 20.9+ 필수. params/searchParams는 await 필수.

## 모델 ID (중요)
- **claude-sonnet-4-6** — 기본. 1M context, $3/$15 per MTok.
- **claude-opus-4-7** — 면접급 난이도 폴백 (2026-04-16 출시).
- **claude-haiku-4-5** — 빠른 힌트 재생성용.
- ❌ `claude-sonnet-4-7`은 **존재하지 않음** — 절대 사용 금지.

## 작업 분할 원칙

태스크 단위:
- 파일 ≤5개 변경
- `pnpm typecheck && pnpm test` 통과로 종료
- 1 logical commit

이보다 큰 태스크는 **STOP, propose split first**.

## Slice 진행 상황

- [x] **Slice 1** — 프로젝트 초기화 + Tailwind v4 design tokens + next/font + `/test-fonts`
- [x] **Slice 2** — Drizzle 스키마 (problems/sessions/attempts) + 로컬 SQLite (libSQL)
- [x] **Slice 3** — Anthropic SDK 싱글톤 + 모델 상수 + base prompt
- [x] **Slice 4** — 6개 토픽 프롬프트 모듈
- [x] **Slice 5** — `/api/generate-problem` 라우트 (non-stream, Tool Use forcing, vitest 14 tests)
- [x] **Slice 6** — 한국어 UI strings (`lib/ko.ts`) + 랜딩 6×3 그리드 + `/dojo` stub
- [x] **Slice 7a** — `/api/sessions` POST + `/dojo` 모드/시간 선택 폼
- [x] **Slice 7b** — `[sessionId]` 페이지 + server action + 문제 렌더 (sessions.problem_id FK)
- [ ] Slice 8 — Monaco 에디터 통합
- [ ] Slice 9 — 4단계 HintLadder
- [ ] Slice 10 — 인터뷰 모의 모드 (타이머 + 락 + autosave)
- [ ] Slice 11 — 리뷰 화면 + diff editor
- [ ] Slice 12 — Kotlin 자동 실행 + Vercel/Turso 배포 (옵션)

## 하지 말 것
- 의존성 추가 시 먼저 물어보기 — pnpm-lock 변경은 신중히.
- 피처 작업 중 무관한 코드 리팩터링 금지.
- TS 에러 무마용 `any` 금지 — 타입을 고치거나 `unknown` + narrow.
- `.env.local`, `db/local.db`, `.next/` commit 금지.
- 사용자 대신 `git commit` 하지 말 것 — 사용자가 직접 검토 후 커밋.
