import type { Difficulty } from '@/db/schema';
import { buildUserPromptHeader, type TopicPromptModule } from './_shared';

const topicSystemPrompt = `토픽: **Room Database**

핵심 개념:
- \`@Entity\` / \`@Dao\` / \`@Database\` / \`@TypeConverter\` 기본 구조.
- DAO 반환 타입: \`suspend\` 단발 vs \`Flow<T>\` 관찰 가능. \`Flow\`는 자동 emit on change.
- Migrations: \`Migration(from, to)\` + 명시적 SQL. \`fallbackToDestructiveMigration\`은 prod에서 안티패턴.
- Indices (\`@Entity(indices=...)\`)로 조회 성능 + 유니크 제약. Compound index 순서 중요.
- \`@Transaction\` — 다중 DAO 호출의 원자성 + \`@Relation\`으로 연관 데이터 조회.
- \`PagingSource\` (\`androidx.paging\`)와 Room의 \`PagingSource<Int, T>\` 통합.
- FTS4/FTS5 가상 테이블로 텍스트 검색 (\`@Fts4\`).
- 동시성: WAL 모드 디폴트, 읽기 동시성 OK, 쓰기 직렬화. 트랜잭션 안에서 외부 suspend 호출 금지.
- Schema export (\`exportSchema = true\`)로 \`schemas/\` 디렉토리 버전 관리.

도메인 훅: 만보기 앱 → \`StepRecord(date, count, source)\`, 일/주/월 집계 쿼리,
센서에서 들어오는 raw event를 증분 insert + 기간별 \`SUM\` 집계.

흔한 함정 / 평가 포인트:
- Migration 누락 시 \`IllegalStateException\` — schema 변경마다 migration 필수.
- Main thread access 검사: 일반 query를 main thread에서 호출하면 \`IllegalStateException\`.
- \`Flow\` DAO를 매번 \`distinctUntilChanged()\`로 감쌀 필요 없음 (Room이 이미 처리).
- \`@Transaction\`이 빠진 \`@Relation\` 쿼리는 race condition 위험.
- Date/시간 저장: \`Long\` (epoch millis) + \`TypeConverter\` vs \`String\` (ISO-8601) 트레이드오프.

출제 시 고려:
- 입문: Entity·DAO·Database 골격 + 기본 INSERT/QUERY + Flow 관찰.
- 중급: Migration 작성, TypeConverter, 집계 쿼리(\`GROUP BY date\`).
- 면접급: schema 진화 전략, FTS·Paging 통합, 동시성 보장, 테스트(\`Room.inMemoryDatabaseBuilder\`).
`;

function buildUserPrompt(difficulty: Difficulty): string {
  return `${buildUserPromptHeader('room-db', difficulty)}

추가 지시:
- 도메인 모델은 만보기·헬스 데이터(걸음 수 일별 집계, 운동 세션, 사용자 목표 등)를 사용하세요.
- reference_solution에는 Entity 정의 + DAO + Database 클래스 + (필요 시) Migration을 포함.
  Flow 반환 DAO 메서드를 최소 1개 보이세요.
- 면접급은 stage 2(tradeoff)에서 schema 변경 시 migration vs destructive 재생성을 비교하고
  데이터 보존 측면 + 사용자 영향을 분석하세요.`;
}

export const roomDbPrompt: TopicPromptModule = {
  topic: 'room-db',
  topicSystemPrompt,
  buildUserPrompt,
};
