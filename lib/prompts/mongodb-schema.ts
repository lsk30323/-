import type { Difficulty } from '@/db/schema';
import { buildUserPromptHeader, type TopicPromptModule } from './_shared';

const topicSystemPrompt = `토픽: **MongoDB 스키마 설계 (서버 사이드 — 안드로이드 개발자 관점에서 백엔드 협업·이해도)**

이 토픽은 코드 작성보다 **설계/모델링/쿼리** 중심입니다. reference_solution은 Kotlin
대신 BSON/JSON 문서 예시 + 인덱스 정의 + 핵심 aggregation pipeline을 작성하세요.
(\`language\` 필드는 \`'kotlin'\`을 유지하되, code 본문은 \`// 스키마 / 쿼리 정의\` 주석과 함께
JSON-like 본문으로 작성해도 OK — 실행 가능 Kotlin이 아니라 설계 명세로 취급합니다.)

핵심 개념:
- Embedded vs Referenced: 1:Few (embed), 1:Many·N:M (reference).
- Time-series collection: \`createCollection(timeseries: { timeField, metaField, granularity })\` —
  걸음 수 분 단위 데이터, 자동 압축 저장.
- 인덱스: 단일·복합·multikey(배열)·해시·TTL·partial. 복합 인덱스의 prefix 규칙.
- Aggregation pipeline: \`$match\` → \`$group\` → \`$project\` 순서, \`$lookup\`(JOIN 유사),
  \`$facet\` 다중 집계, \`$bucket\`/\`$bucketAuto\` 버킷팅.
- Schema validation: \`$jsonSchema\` validator로 필드 타입·필수 검증.
- Sharding key 선택: 카디널리티·빈도·단조성 — userId 기반 vs 시간 기반 hash.
- 안티패턴: 무제한 성장 배열(unbounded array), 다단 \`$lookup\` 체이닝, 인덱스 없는 정렬.

도메인 훅 (필수 사용): 만보기 데이터의 일반적 패턴.
- \`steps\`: \`{ userId, date, count, source: 'sensor'|'manual', updatedAt }\` (일별 집계).
- \`steps_raw\`: time-series, \`metaField: { userId, deviceId }\`, \`timeField: ts\`.
- \`walk_sessions\`: \`{ userId, startTs, endTs, distanceMeters, route?: GeoJSON }\`.
- \`users\`: profile + 목표(daily_goal, weekly_goal).

흔한 함정 / 평가 포인트:
- 시계열을 일반 컬렉션에 분 단위로 넣어 인덱스 폭증 — time-series 컬렉션 사용 이유 설명 가능?
- \`$lookup\`의 비용과 캐시 전략 — 자주 join되면 denormalize 검토.
- \`updatedAt\` 인덱스 + TTL로 90일 raw 데이터 자동 삭제.
- 클라이언트 시간 신뢰 X — 서버 시간으로 \`ts\` 보정.

출제 시 고려:
- 입문: 기본 컬렉션 1~2개 + 단순 query + 인덱스 1개 추천.
- 중급: 복합 인덱스, aggregation pipeline 1개, embed/reference 결정.
- 면접급: time-series + 일별 rollup + sharding 키 선택 + 마이그레이션 시나리오.
`;

function buildUserPrompt(difficulty: Difficulty): string {
  return `${buildUserPromptHeader('mongodb-schema', difficulty)}

추가 지시:
- description은 비즈니스 요구사항 + 데이터 양/쿼리 패턴 가정을 명시하세요
  (예: "DAU 50만, 일별 사용자당 평균 1만 raw 이벤트, 최근 30일 조회가 95%").
- reference_solution.code는 BSON/JSON 형식의 컬렉션 스키마 + \`createIndex\` 호출 +
  대표 aggregation pipeline 1개를 \`// 컬렉션: ... \` 같은 주석과 함께 작성.
  (\`language\`는 \`'kotlin'\`이지만 본문은 설계 명세로 취급. 실행 가능성은 평가하지 않음.)
- complexity 필드는 시간/공간 대신 "쓰기 부하 / 인덱스 크기" 같은 운영 지표로 작성하세요.
- 면접급 stage 2(tradeoff)는 embed vs reference 또는 time-series vs 일반 컬렉션을
  쓰기·읽기·인덱스·쿼리 유연성 4축으로 비교하세요.`;
}

export const mongodbSchemaPrompt: TopicPromptModule = {
  topic: 'mongodb-schema',
  topicSystemPrompt,
  buildUserPrompt,
};
