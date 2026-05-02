/**
 * 한국어 UI 문자열 단일 소스.
 * 컴포넌트 안에 인라인 한국어 리터럴 금지 — 무조건 여기서 import.
 *
 * 구조 가이드:
 * - 페이지/기능 단위로 그룹핑
 * - `as const`로 좁은 string literal 타입 유지
 * - 키는 영문 camelCase, 값만 한국어
 */

import type { Difficulty, Topic } from '@/db/schema';

export const UI = {
  app: {
    name: 'WalkMate Coding Dojo',
    tagline: '워크온 면접 준비용 안드로이드 코딩 도장',
    description:
      'Claude API로 즉석 출제되는 안드로이드/Kotlin 코딩 면접 문제. 6개 토픽 × 3 난이도, 4단계 점진 힌트, 인터뷰 모의 모드.',
  },

  landing: {
    heroLine1: 'WalkMate',
    heroLine2: 'Coding Dojo',
    heroSubtitle: '워크온 안드로이드 면접 준비를 위한 코딩 도장.',
    heroBody:
      '6개 토픽 × 3 난이도, 매번 새로 출제되는 Kotlin 문제. 막히면 4단계 힌트가 한 칸씩 열립니다.',
    topicsHeading: '토픽을 고르세요',
    topicsSubheading: '난이도를 누르면 곧바로 도전이 시작됩니다.',
    footerNote:
      'Sonnet 4.6이 입문·중급을, Opus 4.7이 면접급을 출제합니다. 사용자의 풀이는 로컬 SQLite에만 저장됩니다.',
    devLinks: '개발용 도구',
    devTestFonts: '폰트 확인',
  },

  topics: {
    'coroutines-stateflow': {
      name: 'Coroutines & StateFlow',
      tagline: '구조적 동시성과 상태 흐름',
      description:
        'hot/cold flow, lifecycle-aware collection, sharing 전략과 동시성 테스트까지 — ViewModel 레벨의 상태 흐름 설계 문제.',
    },
    'foreground-service': {
      name: 'Foreground Service',
      tagline: '백그라운드에서도 살아남기',
      description:
        'Android 14+ foregroundServiceType, 권한, Doze/Battery Optimization, FGS vs WorkManager 결정. 만보기의 핵심 컴포넌트.',
    },
    'jwt-auth': {
      name: 'JWT 인증',
      tagline: 'OkHttp Authenticator + 안전 저장',
      description:
        'EncryptedSharedPreferences vs Keystore, 401 retry, Mutex single-flight refresh, token rotation. 클라이언트 측 보안 설계.',
    },
    'room-db': {
      name: 'Room Database',
      tagline: '관계형 + 흐름 + 마이그레이션',
      description:
        'Entity·DAO·Migration·TypeConverter, Flow 반환 DAO, FTS·Paging 통합. 일별 걸음 수 집계 같은 도메인 쿼리.',
    },
    'mongodb-schema': {
      name: 'MongoDB 스키마 설계',
      tagline: '시계열·인덱싱·샤딩',
      description:
        'time-series 컬렉션, embed vs reference, 복합 인덱스, sharding key. 안드로이드 개발자가 알아야 할 백엔드 협업.',
    },
    'jetpack-compose': {
      name: 'Jetpack Compose',
      tagline: '상태 호이스팅과 재구성',
      description:
        'state hoisting, side effects, recomposition stability, semantics. 만보기 progress ring 같은 도메인 컴포넌트.',
    },
  } satisfies Record<Topic, { name: string; tagline: string; description: string }>,

  difficulties: {
    입문: {
      label: '입문',
      description: '1~2년차. 단일 파일·기본기 확인.',
      tone: 'calm',
    },
    중급: {
      label: '중급',
      description: '3~5년차. 컴포넌트 협업·lifecycle 이슈.',
      tone: 'steady',
    },
    면접급: {
      label: '면접급',
      description: '시니어 후보. 트레이드오프·시스템 사고.',
      tone: 'sharp',
    },
  } satisfies Record<Difficulty, { label: string; description: string; tone: string }>,

  dojo: {
    placeholderTitle: '도장 — Slice 7에서 구현',
    placeholderBody:
      '여기에 세션이 만들어지고 문제가 표시됩니다. Slice 7에서 모드 선택과 문제 생성을 연결할 예정.',
    startButton: '도전 시작',
    giveUp: '포기',
    submit: '제출',
    runCode: '코드 실행',
    backToLanding: '← 랜딩으로',
    selectedTopic: '선택한 토픽',
    selectedDifficulty: '선택한 난이도',
    invalidSelection: '잘못된 선택입니다. 랜딩에서 다시 골라주세요.',
  },

  hint: {
    stage1: '1단계 — 결정 질문',
    stage2: '2단계 — 트레이드오프',
    stage3: '3단계 — 이해 점검',
    stage4: '4단계 — 확장 학습',
    reveal: '힌트 보기',
    locked: '잠김',
    confirmTitle: '다음 힌트를 보시겠습니까?',
    confirmBody:
      '한 번 보면 되돌릴 수 없습니다. 본 힌트는 시도 기록에 남아 자기 평가에 반영됩니다.',
    confirmYes: '예, 보겠습니다',
    confirmNo: '취소',
    rationaleHeading: '해설',
  },

  errors: {
    generationFailed: '문제 생성에 실패했습니다. 잠시 후 다시 시도해주세요.',
    rateLimited: 'API 사용량 한도에 도달했습니다. 잠시 후 다시 시도해주세요.',
    unconfigured:
      'ANTHROPIC_API_KEY가 설정되지 않았습니다. 관리자에게 문의하거나 .env.local을 확인하세요.',
    invalidBody: '요청 형식이 올바르지 않습니다.',
    network: '네트워크 오류가 발생했습니다.',
  },

  meta: {
    footer: 'Next.js 16 · React 19 · Tailwind v4 · Claude Sonnet 4.6 / Opus 4.7',
    builtFor: '워크온 안드로이드 면접 준비용',
  },
} as const;

export type UIShape = typeof UI;
