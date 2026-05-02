# WalkMate Coding Dojo

워크온(WalkOn) 안드로이드 개발자 면접 준비용 코딩 문제 생성기.
Claude API로 6개 토픽 × 3 난이도 안드로이드/Kotlin 문제를 즉석 생성하고,
4단계 점진 힌트 + 인터뷰 모의 모드를 제공합니다.

## Stack

- Next.js 16 (App Router) · React 19 · TypeScript 6 strict
- Tailwind CSS v4 (CSS-first `@theme`)
- Drizzle ORM + libSQL (로컬 SQLite ↔ Turso 동일 코드)
- @anthropic-ai/sdk 0.90 — `claude-sonnet-4-6` 기본, `claude-opus-4-7` 폴백
- Monaco Editor (Kotlin Monarch tokenizer)
- Judge0 CE (RapidAPI) — Kotlin 자동 실행 (옵션)

## Quick start

```bash
# 의존성
pnpm install

# 환경 변수 (Slice 3+ 부터 필요)
cp .env.example .env.local
# ANTHROPIC_API_KEY 등을 직접 채워 넣으세요.

# 개발 서버
pnpm dev

# 폰트/팔레트 확인 (Slice 1 결과물)
open http://localhost:3000/test-fonts
```

## Scripts

| Script | 설명 |
|---|---|
| `pnpm dev` | Next.js dev server |
| `pnpm build` | production build |
| `pnpm typecheck` | `tsc --noEmit` |
| `pnpm lint` | ESLint |
| `pnpm test` | Vitest (단위) |
| `pnpm test:e2e` | Playwright |
| `pnpm db:generate` | Drizzle migrations 생성 |
| `pnpm db:migrate` | migrations 적용 |
| `pnpm db:studio` | Drizzle Studio |
| `pnpm db:setup` | generate + migrate + seed |

## Slice 진행 상황

- [x] **Slice 1** — 프로젝트 초기화, Tailwind v4 토큰, next/font, `/test-fonts`
- [x] **Slice 2** — Drizzle 스키마 + 로컬 SQLite (libSQL)
- [x] **Slice 3** — Anthropic SDK 싱글톤 + 모델 상수 + base prompt
- [x] **Slice 4** — 6 토픽 프롬프트 모듈 + `getPromptFor` 헬퍼
- [x] **Slice 5** — `/api/generate-problem` 라우트 (non-stream)
- [x] **Slice 6** — 한국어 UI strings + 랜딩 6×3 그리드
- [x] **Slice 7a** — `/api/sessions` + 모드/시간 선택 폼
- [x] **Slice 7b** — `[sessionId]` 페이지 + server action + 문제 렌더
- [ ] Slice 8 — Monaco 에디터
- [ ] Slice 9 — 4단계 HintLadder
- [ ] Slice 10 — 인터뷰 모의 모드
- [ ] Slice 11 — 리뷰 화면 + diff
- [ ] Slice 12 — Kotlin 자동 실행 + 배포

자세한 작업 가이드는 [`CLAUDE.md`](./CLAUDE.md)를 참고하세요.

## License

Private — internal interview prep tool.
