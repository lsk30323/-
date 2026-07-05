# Concept Gate Taxonomy v7

정규화-검증형 개념 격자 추론기입니다.
자연어 개념을 proof-carrying feature 구조로 정규화하고, Gate 검증을 통과한
`is_a` 관계만 DAG에 반영합니다. 용도, 장소, 기능, 사회적 취급 같은 맥락 관계는
기본 개념 계층에서 분리하여 보조 관계로 다룹니다.

**is-a와 has-a의 분리**가 핵심 설계입니다:
- `essential_feature` (is-a) → DAG 간선 → 분류 계층 (DL concept axiom, C ⊑ D)
- `structural_composition` (has-a) → composition 그래프 → 부분-전체 관계 (DL role axiom, ∃R.C)

두 그래프는 독립적으로 추론되며, CompositionGate가 has-a 그래프에 mereology
공리(반대칭·비순환·is-a/has-a 배타)를, UFOAntiPatternGate가 UFO/OntoUML
안티패턴(MixRig·PartOver·WholeOver)을 적용해 혼동을 자동 감지합니다.

v7은 v6.3의 Gate/DAG 안정화 위에 expansion loop, sibling gate,
parent candidate classification, graph export, 그리고 Phase A/B/C
(UFO 판별 프롬프트 / STRUCTURAL 타입 / mereology 검증)를 추가한 버전입니다.
코어는 외부 라이브러리나 LLM API 없이 Python 3.10+ 표준 라이브러리만으로 실행됩니다.

## 파일 구성

```
concept-gate-taxonomy/
├── README.md              ← 이 파일
├── CLAUDE.md              ← 개발 지침 (Ponytail Rules, Subtree Registry)
├── qa_v7.py               ← v7 QA 스크립트 (89개 검증) ★ 최신
├── concept_gate_v7.py     ← v7 검증 대상 소스 (stdlib만 의존) ★ 최신
├── cg_partwhole.py        ← part-whole 어댑터 (vendor/obo-relations 조립) ★ 신규
├── cg_graph_export.py     ← GraphExporter: JSON/Mermaid/GraphML (별도 모듈)
├── qa_v6_3.py             ← v6.3 QA (33개, 회귀 참고용)
├── concept_gate_v6_3.py   ← v6.3 소스 (회귀 참고용)
├── files/                 ← MCP 서버 배포 디렉토리 (files/README.md 참조)
│   ├── server.py          ← FastMCP 어댑터
│   ├── concept_gate_v7.py ← 배포 복사본 (루트와 동기화 유지)
│   └── cg_partwhole.py    ← 배포 복사본
├── vendor/
│   └── obo-relations/     ← git subtree: OBO Relation Ontology (core.obo)
│                             part_of(BFO:0000050)/has_part(BFO:0000051) 표준 공리
├── docs/                  ← Phase A/C 구현·설계 패킷
└── reference/
    ├── INTEGRATION_NOTES.md   ← TaxoAdapt 통합 계획 (계약 명세)
    ├── taxonomy.py            ← TaxoAdapt 원본 (참고용, 실행 안 함)
    ├── expansion.py           ← TaxoAdapt 원본 (참고용)
    ├── classification.py      ← TaxoAdapt 원본 (참고용)
    └── prompts.py             ← TaxoAdapt 원본 (참고용)
```

## 실행 방법

```bash
# 저장소 루트에서 실행
cd concept-gate-taxonomy

# v7 QA 계약 검증 (89개)
python3 qa_v7.py

# 소스 자체 인라인 테스트 (60개)
python3 concept_gate_v7.py

# MCP 서버 테스트 (30개, fastmcp 필요)
python3 files/test_server.py

# GraphExporter 인라인 테스트 (12개)
python3 cg_graph_export.py

# v6.3 회귀 참고 (33개)
python3 qa_v6_3.py
```

종료 코드: 전체 통과 시 `0`, 하나라도 실패 시 `1`.

## v7이 무엇인가

v6.3(개념 정규화 + Gate 검증 + DAG 생성)에 **확장(expansion) 기능**을 추가한 버전.
같은 essential 속성을 가진 개념들이 구분되지 않을 때, 종차(differentia)를 추가하여
계층을 정교화하는 루프를 구현했습니다.

### 파이프라인 흐름 (v7)

```
ParseGate
→ SemanticTypeInference
→ ConceptGate (type/evidence/contradiction/semantic)
→ PreDAGSignatureGate     ← essential 중복 탐지 (DAG 전)
→ DAGReasoner (EdgeBuffer로 staged commit)
   ├── is-a DAG (ESSENTIAL 피처)
   └── composition_view() ← has-a 그래프 (STRUCTURAL 피처, 독립)
→ PostDAGSiblingGate      ← 실제 sibling 종차 부족 탐지 (DAG 후)
→ CompositionGate         ← mereology 공리 검증 (반대칭·비순환·is-a/has-a 배타) ★ Phase C
→ UFOAntiPatternGate      ← MixRig/PartOver/WholeOver 감지 (WARNING) ★ Phase C
→ ResultClassifier
→ ExpansionPlanner        ← WARNING/NEEDS_CORRECTION → ExpansionAction (MixRig도 CORRECTION으로)
   (run_with_expansion 루프에서)
→ generator.generate()    ← 종차 생성 (LLM 또는 Static)
→ parse_expansion_response → 재진입
→ ParentCandidateClassifier  ← 최종 부모 후보 multi-label 판정
```

### Phase A/B/C: is-a vs has-a 판별 (v7 후반 추가)

- **Phase A** — `build_expansion_prompt()`에 UFO 기반 판별 가이드 삽입.
  LLM이 부분-전체 관계를 `structural_composition`으로 직접 출력하도록 지시
  (Winston 3차원 테스트 + UFO 타입 매핑 + 부분-전체 패턴 6종).
- **Phase B** — `FeatureType.STRUCTURAL` 추가. is-a DAG에는 불참(`ISA_ALLOWED_TYPES`
  는 ESSENTIAL만), `composition_view()`로 분리. `relation_hint` 필드(UFO 어휘)를
  스키마에 추가. 어휘 매핑은 `cg_partwhole.py`가 vendor/obo-relations subtree에서 조립.
- **Phase C** — `CompositionGate`(mereology 공리), `UFOAntiPatternGate`(안티패턴 3종),
  `relational_scaling()`(RCA existential scaling, ∃has_part.X 파생 — opt-in).

파이프라인 출력에 `composition`(has-a 그래프), `composition_issues`(공리 위반),
`anti_patterns`(안티패턴)가 추가됩니다. 기존 키는 변경 없음 (하위호환).

## 무엇을 검증하는가

PART A — v6.3 단독 동작 (13건): ParseGate 스키마, 상태 분류, WarningAction 분리.
PART B — TaxoAdapt get_siblings() 이식 (5건).
PART C — API 표면 계약 (14건): PipelineStatus/GateSeverity 5단계 + v7 클래스 존재 확인.
  - C8-C10: ExpansionPlanner, PostDAGSiblingGate, PreDAGSignatureGate 존재해야 함
  - C11-C13: ParentCandidateClassifier, ExpansionGeneratorBase, StaticExpansionGenerator 존재해야 함
  - C14: LLM 직접 호출 클래스는 없어야 함 (외부 주입 설계)
PART D — 회귀 불변식 (5건): finalize() 멱등성, EdgeBuffer rollback.
PART E — v7 Phase 1-3 (7건): PostDAG 탐지, ExpansionPlanner, run_with_expansion 수렴.
PART F — v7 Phase 4 (8건): ParentCandidateClassifier, generator 인터페이스, CORRECTION 자동 처리.
PART G — v7 Phase 5 (7건): HeuristicExpansionGenerator, ExpansionPlanner dedup, ExpansionHistoryAnalyzer.
PART H — GraphExporter (4건): JSON/Mermaid/GraphML 내보내기 + summary.
PART I — Phase A/B (7건): UFO 판별 가이드, relation_hint 스키마, STRUCTURAL 파싱, subtree 연결.
PART J — Phase C1/C2 (9건): CompositionGate 공리 4종 + UFO 안티패턴 3종 + ExpansionPlanner 연계.
PART K — Phase C3 (4건): relational_scaling 파생·멱등성·배선.
PART L — 구성 vs 구조 혼동 (5건): Transformer/Attention 실 도메인 시나리오.
  메커니즘을 부품으로 착각(MixRig), 개념 패밀리를 단일 부품으로(WholeOver),
  상속 부분 중복 선언(PartOver), is-a를 has-a로도 선언(배타 위반), 올바른 모델링 대조군.

## LLM 연결 방법 (중요)

이 파일 자체는 LLM 없이 동작합니다. 확장 종차는 StaticExpansionGenerator로
주입합니다(사람 또는 다른 agent가 미리 작성). 실제 LLM을 연결하려면 두 가지 경로:

### 경로 1: claude.ai의 AI-Powered Apps (JSX artifact)
claude.ai에서 React artifact를 만들고 fetch("https://api.anthropic.com/v1/messages")로
Claude를 호출. build_expansion_prompt(action)으로 프롬프트를 만들고, 응답을
parse_expansion_response()에 넘깁니다.

### 경로 2: ExpansionGeneratorBase 상속
```python
class LLMExpansionGenerator(ExpansionGeneratorBase):
    def __init__(self, anthropic_client):
        self.client = anthropic_client

    def generate(self, action):
        prompt = build_expansion_prompt(action)   # v7 내장 함수
        response = self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}])
        return response.content[0].text  # raw JSON string

# 사용
pipe.run_with_expansion(concepts, generator=LLMExpansionGenerator(client))
```

generate(action)이 raw JSON 문자열을 반환하기만 하면, 나머지(파싱/검증/재진입)는
파이프라인이 처리합니다.

## QA 에이전트를 위한 검토 지침

1. TaxoAdapt 통합 범위: taxonomy.py::get_siblings()의 부분 이식만 적용됨.
   reference/의 4개 파일은 pydantic/unidecode/LLM 호출부에 의존하므로
   import하면 실패합니다 — 정상입니다.

2. v7에 있어야 / 없어야 하는 것:
   - 있어야 함: ExpansionPlanner, PostDAGSiblingGate, PreDAGSignatureGate,
     ParentCandidateClassifier, ExpansionGeneratorBase, StaticExpansionGenerator,
     run_with_expansion, build_expansion_prompt, parse_expansion_response
   - 없어야 함: AnthropicExpansionGenerator, LLMExpansionGenerator
     (LLM은 외부에서 주입, 코어에 하드코딩 안 함)

3. 확장 루프 수렴 확인 (가장 중요):
   개·고양이·말이 모두 {동물} essential로 동일 → PASS_WITH_WARNING →
   StaticExpansionGenerator가 종차 추가 → 각자 다른 essential → PASS.
   이 수렴이 PART E E6에서 검증됩니다. 실패하면 expansion 루프 또는 ResultClassifier
   문제입니다.

4. ParentCandidateClassifier 다중 부모 (meet) 확인:
   정사각형 → [마름모, 직사각형] (PART F F2). indirect 조상(사각형)은 제외되어야 함.

5. 추가 hard-case 제안:
   - 3단계 이상 깊이의 확장 (현재 테스트는 1회 확장)
   - 확장 후에도 여전히 WARNING인 경우 (max_expansion_rounds 도달)
   - CORRECTION action (현재 루프는 DEPTH/WIDTH만 처리, CORRECTION은 skip)
   - 확장 generator가 잘못된 JSON 반환 시 PARSE_FAIL 경로

## 미구현 (다음 마일스톤)

- 실제 LLM generator 구현체 (경로 2의 LLMExpansionGenerator)
- LLMs4OL TaskB/C 데이터셋 벤치마크 (Gate 정확도 정량 평가)
- corpus 기반 expansion 트리거 (TaxoAdapt의 빈도 분석)

## 최근 변경

- **Phase A/B/C 설계 비정합 해결**: Phase A 프롬프트가 has-a를 `functional`로
  지시하던 것을 `structural_composition` 직접 출력으로 수정. Phase B의
  hint→type 후교정 로직 삭제 (프롬프트-교정 모순 제거, 삭제 > 추가).
  anti_context_gate에서 STRUCTURAL 제외 ("자동차 has 엔진"이
  "전기차 is-a 자동차"를 차단하지 않도록). 한국어 STRUCTURAL 마커는
  정확 일치로 전환 ("부품" ⊂ "일부품목" 오탐 방지).
- PART L 추가: Transformer/Attention 도메인의 구성 vs 구조 혼동 시나리오 5종.
- CORRECTION action 자동 처리: non-sparse same signature → NEEDS_CORRECTION →
  generator가 종차 추가 → 재진입 → PASS 수렴. DEPTH/WIDTH/CORRECTION 전부 처리됨.

## 버전 메타

- 검증 대상: concept_gate_v7.py (2208행) + cg_partwhole.py + cg_graph_export.py
- 의존성: Python 3.10+ 표준 라이브러리만 (MCP 서버만 fastmcp 필요)
- 외부 패키지: 코어 없음. vendor/obo-relations는 git subtree (읽기 전용 데이터)
- LLM API: 코어는 불필요. 확장은 generator로 주입 (Static 또는 LLM).
- 인라인 테스트: 60건 (concept_gate_v7.py) + 12건 (cg_graph_export.py)
- QA 검증: 89건 (`python3 qa_v7.py` 실행, PART A-L)
- MCP 서버 테스트: 30건 (`python3 files/test_server.py`)
