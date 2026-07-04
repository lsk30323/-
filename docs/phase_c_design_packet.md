# Phase C Design Packet: RCA 다중 격자 + UFO Anti-Pattern 감지

Phase C 최소 구현(composition_view, 커밋 `aea9dbc`)의 나머지 설계.
구현 전 설계 문서이며, 이 packet만 읽고 다른 에이전트가 구현할 수 있도록 작성됨.

## Goal

1. **C1 — CompositionGate**: 구성(has-a) 그래프를 mereology 공리로 검증
2. **C2 — UFO Anti-Pattern 감지**: MixRig / PartOver / WholeOver 자동 판별
3. **C3 — RCA 관계 스케일링**: is-a 격자와 has-a 그래프를 연결하는 관계 속성 파생

## 이론적 근거 (요약)

| 설계 요소 | 근거 |
|-----------|------|
| 반대칭·비순환 검증 | OBO RO part_of 공리 ("Two distinct things cannot be part of each other") — `vendor/obo-relations/core.obo` BFO:0000050 |
| 추이 폐쇄 | core.obo `is_transitive: true` (part_of/has_part) |
| Anti-pattern 3종 | UFO/OntoUML 카탈로그 (Guizzardi 2021) |
| 관계 스케일링 (∃R.C) | RCA (Rouane-Hacene 2013) — 관계적 문맥 가족의 existential scaling |

## Constraints

- stdlib only (기존 코드와 동일)
- 기존 테스트 160개(인라인 60 + QA 70 + 서버 30) 전부 통과 유지
- `finalize()` 출력·`run()` 반환 dict에는 **키 추가만** (기존 키 변경 금지)
- obo 공리는 `cg_partwhole.load_obo_partwhole()`로 읽음 (subtree 직접 수정 금지)
- 커밋은 로컬만, push 금지

## 현재 코드 기준점 (line 번호는 커밋 `aea9dbc` 기준)

- `DAGReasoner.composition_view()` — concept_gate_v7.py:706 (C의 입력)
- `ConceptPipeline.validate_hierarchy()` — :1341 (게이트 배선 지점, PostDAG는 :1382)
- `ConceptPipeline.run()` — :1387 (결과 dict 조립)
- `ExpansionPlanner.plan(sig_iss, post_iss)` — :797 부근 (CORRECTION action 생성)
- `ResultClassifier.classify()` — :751 (severity → PipelineStatus)
- `cg_partwhole.load_obo_partwhole()` — cg_partwhole.py (추이성/역관계 메타)

---

## C1. CompositionGate

### 목적
STRUCTURAL 간선(전체 → 부분)이 mereology 공리를 위반하는지 검사.
"is-a와 has-a의 혼동"이 그래프 수준에서 드러나는 지점을 잡는다.

### 클래스 설계

`concept_gate_v7.py`의 PostDAGSiblingGate 아래에 신설:

```python
class CompositionGate:
    """구성(has-a) 그래프의 mereology 공리 검증 (Phase C1).

    공리 출처: vendor/obo-relations core.obo (BFO:0000050/51)
    - 반대칭: 서로가 서로의 부분일 수 없음 (proper parthood)
    - 비순환: 추이 폐쇄에서 자기 자신에 도달하면 위반
    - is-a/has-a 배타: DAG 조상·자손 관계인 두 개념 사이에 has_part 간선 금지
    """

    @staticmethod
    def detect(reasoner: DAGReasoner) -> Tuple[GateReport, List[Dict]]:
        ...
```

### 검사 항목 (각각 GateResult 1개)

| # | 검사 | 입력 | 위반 시 severity |
|---|------|------|-----------------|
| 1 | 반대칭 | composition edges에서 (A,B)와 (B,A) 동시 존재 | ERROR |
| 2 | 비순환 | 부분 이름이 개념명과 일치하는 간선만 모아 추이 폐쇄 → 자기 도달 검사 | ERROR |
| 3 | is-a/has-a 배타 | (전체, 부분) 쌍이 DAG 조상-자손 관계이기도 함 | NEEDS_CORRECTION |
| 4 | 자기 부분 | (A, A) 간선 | WARNING (고전 mereology는 반사 허용, 모델링에선 의심) |

주의: 부분(feature 문자열)이 개념명과 일치할 때만 그래프 순환 검사가 의미 있음.
일치하지 않는 부분(예: "엔진"이 개념으로 없음)은 leaf로 취급하고 검사 1·4만 적용.

### 반환 형식

`PostDAGSiblingGate.detect`와 동일 패턴: `(GateReport, issues: List[Dict])`.
issue dict: `{"kind": "antisymmetry|cycle|isa_hasa_conflict|self_part", "whole": ..., "part": ..., "detail": ...}`

### 배선

`validate_hierarchy()` :1382 PostDAG 직후:

```python
comp_rep, comp_iss = CompositionGate.detect(reasoner)
all_reps.append(comp_rep)
```

반환 튜플 끝에 `comp_iss` 추가 → `run()`에서 `"composition_issues": comp_iss`로 노출.
반환 arity가 6→7로 변하므로 `run()`의 언패킹(:1392)도 같이 수정.

---

## C2. UFO Anti-Pattern 감지

### 목적
UFO 카탈로그 중 ConceptGate 데이터로 판별 가능한 3종을 자동 감지.
결과는 WARNING(정보성)으로, CORRECTION expansion action의 재료가 된다.

### 클래스 설계

```python
class UFOAntiPatternGate:
    """UFO/OntoUML anti-pattern 감지 (Phase C2). 전부 WARNING — 차단하지 않음."""

    @staticmethod
    def detect(reasoner: DAGReasoner, concepts: List[NormalizedConcept]) -> Tuple[GateReport, List[Dict]]:
        ...
```

### 패턴별 판별 규칙

**MixRig (rigidity 혼합)**
같은 feature 이름이 어떤 개념에선 ESSENTIAL, 다른 개념에선 비-ESSENTIAL로 등장.
```
feature_types = defaultdict(set)   # feature명 → {FeatureType,...}
for c in concepts, f in c.features: feature_types[f.feature].add(f.type)
위반: ESSENTIAL과 비-ESSENTIAL이 공존하는 feature
```
의미: rigid(정체성) 속성과 anti-rigid 속성이 같은 이름으로 혼용 → 분류 기준 오염.

**PartOver (부분이 겹치는 전체에 속함)**
`composition_view().shared_parts`의 각 부분에 대해, 전체들 중 한 쌍이 DAG 조상-자손 관계이면 위반.
```
for part, wholes in shared_parts.items():
    for w1, w2 in combinations(wholes, 2):
        if is_ancestor(w1, w2) or is_ancestor(w2, w1): 위반
```
의미: 자식이 상속받을 부분을 중복 선언 → 모델 중복 (예: 포유류 has 심장 + 개 has 심장).

**WholeOver (전체가 겹치는 부분을 가짐)**
한 개념의 STRUCTURAL 부분 두 개가 DAG 조상-자손 관계이면 위반.
```
for c in concepts:
    parts = [f.feature for f in c.contextual_features if f.type == STRUCTURAL]
    for p1, p2 in combinations(parts, 2):
        if is_ancestor(p1, p2) or is_ancestor(p2, p1): 위반
```
의미: 일반 부분과 그 특수화를 동시 선언 (예: 차 has 바퀴 + has 앞바퀴).

`is_ancestor(a, b)`: `reasoner.dag`의 도달 가능성 (BFS/DFS, 소규모라 단순 구현으로 충분).

### issue dict

`{"pattern": "MixRig|PartOver|WholeOver", "subject": ..., "detail": ..., "involved": [...]}`

### 배선

CompositionGate 직후, 동일 방식. `run()` 결과에 `"anti_patterns": ap_iss` 추가.

### ExpansionPlanner 연계 (선택)

`ExpansionPlanner.plan(sig_iss, post_iss)`에 세 번째 인자 `ap_iss=None` 추가(기본값으로 하위호환).
MixRig issue → CORRECTION action (해당 feature의 type 교정 지시). PartOver/WholeOver는 정보만.

---

## C3. RCA 관계 스케일링 (existential scaling)

### 목적
RCA의 핵심: 객체 간 관계(has_part)를 **관계 속성**(∃has_part.C)으로 변환해
FCA 문맥에 주입 → 구성이 비슷한 개념들이 is-a 격자에서 묶이게 함.

### 범위 제한 (Ponytail)
완전한 RCA 고정점(다중 격자 상호 참조 반복)은 이 코드베이스 규모에 과함.
**단일 스케일링 패스 1회**만 구현한다 — 기존 `run_with_expansion` 루프(:1411)가
이미 재진입 구조이므로, 스케일링을 루프 앞단에 한 번 적용하면
"확장 루프 ≈ RCA 수렴"의 실용적 근사가 된다.

### 함수 설계 (클래스 불필요)

```python
def relational_scaling(concepts: List[NormalizedConcept]) -> List[NormalizedConcept]:
    """RCA existential scaling 1-pass (Phase C3).

    부분 이름이 개념명과 일치하는 STRUCTURAL 피처를
    파생 ESSENTIAL 피처 "∃has_part.{부분}"으로 추가한 사본을 반환.
    파생 피처는 evidence에 'rca_scaling' 마커를 남겨 추적 가능하게 한다.
    원본 리스트는 변경하지 않는다 (순수 함수).
    """
```

규칙:
- 대상: `f.type == STRUCTURAL`이고 `f.feature`가 개념명 집합에 존재
- 파생 피처명: `∃has_part.{part}` (문자열 그대로 — FCA는 문자열 동일성만 봄)
- 파생 type: ESSENTIAL — 이래야 DAG 간선 형성에 기여. 단 **원본 STRUCTURAL은 유지**
  (composition_view는 계속 동작)
- 이미 같은 파생 피처가 있으면 추가하지 않음 (멱등 — 재진입 루프에서 안전)

예시: 자동차{탈것(E), 엔진(S)} + 전기차{탈것(E), 엔진(S), 배터리(S)} + 엔진{동력장치(E)}
→ 자동차·전기차 모두 `∃has_part.엔진`(E) 획득 → 격자에서 "엔진 보유 탈것"으로 묶임.

### 배선

`run_with_expansion()` :1417 직전에 opt-in:

```python
def run_with_expansion(self, initial_concepts, generator=None,
                       max_expansion_rounds=2, rca_scaling=False):
    if rca_scaling:
        initial_concepts = relational_scaling(initial_concepts)
    out = self.run([initial_concepts])
```

기본 `False` — 기존 호출 전부 무변경. MCP server의 `run_pipeline`/`expand` tool에
`rca_scaling` 파라미터를 노출할지는 구현 시 판단(서버 변경 최소화 원칙이면 보류).

---

## 구현 순서와 커밋 단위

| 단계 | 내용 | 커밋 |
|------|------|------|
| C1 | CompositionGate + validate_hierarchy/run 배선 + QA PART J (4~5건) | 1 |
| C2 | UFOAntiPatternGate + ExpansionPlanner 연계 + QA PART J 추가 (3~4건) | 1 |
| C3 | relational_scaling + run_with_expansion opt-in + QA PART K (3건) | 1 |

각 단계 후: `python3 concept_gate_v7.py && python3 qa_v7.py && python3 files/test_server.py`
전부 통과 확인 → `cp concept_gate_v7.py files/concept_gate_v7.py` 동기화 → 로컬 커밋.

## 테스트 계획 (QA 추가분)

**PART J — C1/C2:**
- J1 반대칭: (A has B) + (B has A) → ERROR
- J2 순환: A→B→C→A 추이 폐쇄 → ERROR
- J3 is-a/has-a 배타: 부모가 자식을 part로 선언 → NEEDS_CORRECTION
- J4 MixRig: 같은 feature가 E/비E 혼용 → WARNING + issue
- J5 PartOver: 조상·자손이 같은 part 공유 → WARNING
- J6 WholeOver: 한 개념이 part와 그 특수화 동시 보유 → WARNING
- J7 무위반 입력 → 모든 게이트 passed, issues 빈 리스트

**PART K — C3:**
- K1 스케일링: STRUCTURAL 부분이 개념으로 존재 → `∃has_part.X` ESSENTIAL 파생
- K2 멱등성: 두 번 적용해도 파생 피처 1개
- K3 비개념 부분("엔진"이 개념 아님) → 파생 없음, 원본 불변

## 하위호환 체크리스트

- [ ] `validate_hierarchy` 반환 arity 변경에 따른 내부 호출자 전수 수정 (run이 유일한 호출자인지 grep으로 확인)
- [ ] `finalize()`/`run()` dict는 키 추가만
- [ ] `ExpansionPlanner.plan` 새 인자는 기본값으로
- [ ] `run_with_expansion` 새 인자 `rca_scaling=False`
- [ ] GraphExporter가 `composition` 키를 모르는 것은 무해 (dict 접근이 명시 키만)
- [ ] 기존 160개 테스트 통과

## 미해결 설계 판단 (구현자가 결정)

1. C1 검사 3(is-a/has-a 배타)에서 NEEDS_CORRECTION은 파이프라인 status를
   NEEDS_CORRECTION으로 끌어올림 — 의도된 동작이지만, 기존 fixture가 걸리면
   WARNING으로 낮추고 근거를 커밋 메시지에 남길 것.
2. `∃has_part.` 접두사의 표기 — 한국어 환경이므로 `부분:엔진` 같은 표기도 가능.
   FCA 동작에는 무관하니 출력 가독성 기준으로 선택.
3. MCP server에 composition_issues/anti_patterns 노출 여부 — server.py 무수정
   원칙이면 run() dict에 이미 포함되므로 자동 노출됨 (별도 작업 불필요할 수 있음).
