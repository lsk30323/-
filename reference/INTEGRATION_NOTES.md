# TaxoAdapt → ConceptGate v6.2 통합 매핑

## Subtree 파일 4개 분석 요약

### taxonomy.py (327행)

**핵심 구조**: `Node` + `DAG` 클래스.

```
Node:
  id, label, dimension, description
  children: Dict[str, Node]
  parents: List[Node]
  level: int
  papers: Dict[str, Paper]
  source: "initial" | "width" | "depth"
```

**가져올 것**:
- `get_ancestors()`: BFS 조상 수집. 우리 `DAGReasoner.collect_ancestors()`와 동일 기능.
- `get_siblings()`: 부모를 통해 형제 노드 수집. 우리 SignatureGate에서 same_signature sibling 탐지에 활용.
- `source` 필드: 노드가 어디서 왔는지 추적. 우리 `RepairAction`과 결합 가능.

**수정 필요**:
- `level = min(parent.level) + 1` (add_child/add_parent 시). 
  우리 다중 부모 meet에서는 `max(parent.level) + 1`이 안전.
  초기화에서는 `max`를 쓰고 있지만, add_child/add_parent에서 `min`으로 바꿈 → 비일관.

**가져오지 않을 것**:
- `classify_node()`, `classify_dag()`, `enrich_dag()`: LLM 호출부. 우리 파이프라인과 결합도 낮음.
- `papers` 딕셔너리: corpus 기반. 우리는 개념 속성 기반.

---

### expansion.py (222행)

**핵심 로직**:

```
expandNodeWidth(node):
  1. unlabeled papers 수집 (부모에 있지만 자식에 미분류)
  2. unlabeled > max_density → 확장 트리거
  3. 각 paper에 대해 "새 subtopic 제안" 프롬프트
  4. 제안된 subtopic을 빈도 기반 클러스터링
  5. 클러스터 → 새 child 노드 생성
  6. cycle 방지: ancestor에 이미 있으면 skip

expandNodeDepth(node):
  1. leaf 노드의 papers에서 "더 구체적 subtopic" 제안
  2. 클러스터링 후 새 child 생성
  3. 같은 cycle 방지 로직
```

**가져올 핵심 아이디어**:
- **확장 트리거 조건**: unlabeled > max_density (width) / leaf node (depth)
  → 우리: `WARNING_UNDERSPECIFIED` → depth expansion 요청
  → 우리: `same_essential_signature` siblings → width expansion 요청
- **중복 방지**: `label2node`에 이미 있으면 skip, ancestor면 skip
  → 우리: Cycle Gate + SignatureGate가 이미 처리
- **source 추적**: `source='width'` / `source='depth'`
  → 우리: `RepairAction`에 expansion_type 추가 가능

**가져오지 않을 것**:
- LLM 호출 방식 (`promptLLM`, `constructPrompt`): 우리는 Anthropic API 직접 사용.
- Counter 기반 빈도 분석: 우리는 corpus가 아니라 속성 기반이므로 불필요.

---

### classification.py (34행)

**핵심**: multi-label classification 프롬프트.

```
classify_prompt(node, paper):
  "이 paper가 node의 children 중 어디에 속하는가?"
  → class_labels: List[str] (multi-label)
  → explanation: str
```

**가져올 핵심 아이디어**:
- **ParentCandidateClassifier로 응용**: 
  "이 개념이 여러 부모 후보 중 어디에 속하는가?"
  → multi-label → 다중 부모(meet) 자동 탐지
  → 우리 `validate_edge()`의 Subsumption Gate 보조
- **Pydantic schema**: `ClassifySchema(explanation, class_labels)`
  → 우리 `ParseGate`의 출력 스키마와 결합 가능

**가져오지 않을 것**:
- paper 기반 분류 로직 (우리는 속성 기반)

---

### prompts.py (1054행)

**핵심**: width/depth expansion 프롬프트 + Pydantic 스키마.

```
Width:
  WidthExpansionSchema: { new_subtopic_label: str }
  width_main_prompt: "이 paper가 parent 밑에서 어떤 새 subtopic을 다루는가?"
  WidthClusterListSchema: { new_cluster_topics: List[{label, description, covered_paper_topics}] }

Depth:
  DepthExpansionSchema: { new_subtopic_label: str }
  depth_main_prompt: "parent보다 더 구체적인 subtopic은?"
  DepthClusterListSchema: 동일 구조
```

**가져올 핵심 아이디어**:
- **프롬프트 구조**: `<parent_node>`, `<path_to_parent_node>`, `<type_definition>` XML 태그 사용
  → 우리 correction prompt에 동일 구조 적용 가능
- **cluster → 새 노드** 패턴: LLM이 제안한 subtopic을 클러스터링 후 노드로 전환
  → 우리: SignatureGate WARNING 이후 "종차 추가 요청"에 활용
- **dimension_definitions**: 각 차원의 정의를 프롬프트에 포함
  → 우리: FeatureType 정의를 시스템 프롬프트에 포함하는 것과 동일

---

## v6.2 통합 위치

```
ConceptPipeline v6.2 현재 흐름:

  ParseGate
  → SemanticTypeInference
  → FeatureRepair
  → SignatureGate
  → DAGReasoner (Gate-before-commit + EdgeBuffer)
  → ResultClassifier

TaxoAdapt 반영 후 v7 흐름:

  ParseGate
  → SemanticTypeInference
  → FeatureRepair
  → SignatureGate
  → [NEW] ExpansionPlanner          ← TaxoAdapt expansion.py 번역
      → WARNING_UNDERSPECIFIED → depth expansion 요청
      → same_signature siblings → width expansion 요청
      → empty essential → NEEDS_CORRECTION (변경 없음)
  → DAGReasoner (Gate-before-commit + EdgeBuffer)
  → [NEW] ParentCandidateClassifier  ← TaxoAdapt classification.py 번역
      → multi-label → 다중 부모 자동 탐지
  → ResultClassifier
```

## 이식 시 이름 변환

| TaxoAdapt 원본 | ConceptGate 이름 | 이유 |
|---|---|---|
| `taxonomy.py::Node` | `dag_node.py::ConceptNode` | Node가 너무 일반적 |
| `taxonomy.py::DAG` | 기존 `DAGReasoner`에 흡수 | 별도 클래스 불필요 |
| `expansion.py::expandNodeWidth` | `expansion_planner.py::plan_width_expansion` | 함수 이름 동사화 |
| `expansion.py::expandNodeDepth` | `expansion_planner.py::plan_depth_expansion` | 동일 |
| `classification.py::classify_prompt` | `parent_classifier.py::classify_parent_candidates` | 용도 명시 |
| `prompts.py::WidthExpansionSchema` | `expansion_schemas.py::WidthExpansionSchema` | 그대로 유지 |
| `Node.source` | `RepairAction.expansion_type` | 기존 필드와 통합 |
| `Node.get_siblings()` | `DAGReasoner.get_siblings()` | 메서드로 추가 |
| `Node.level = min(...)` | `level = max(...)` | 다중 부모 meet 안전성 |

## 실제 이행 상태 vs 계획 (v6.3.1 기준)

### 완료 (v6.3)
- `DAGReasoner.get_siblings()` 추가 (taxonomy.py에서 이식)

### 완료 (v7 Phase 1-4) ✓
- `SignatureGate` → `PreDAGSignatureGate` / `PostDAGSiblingGate` 분리 (Phase 1)
  PreDAG는 essential frozenset 비교, PostDAG는 buf.commit 이후 get_siblings() 활용.
- `ExpansionType` / `ExpansionAction` 추가 (Phase 2)
  DEPTH / WIDTH / CORRECTION 세 종류.
- `ExpansionPlanner.plan()`: WARNING/NEEDS_CORRECTION → ExpansionAction (Phase 2)
- `EXPANSION_OUTPUT_SCHEMA` + `build_expansion_prompt()` + `parse_expansion_response()` (Phase 3)
- `MockExpansionGenerator` / `StaticExpansionGenerator` + `run_with_expansion()` (Phase 3-4)
  LLM 없이 종차 주입, round0 WARNING → 최종 PASS 수렴 검증.
- `ParentCandidateClassifier`: multi-label 다중 부모 판정 (Phase 4)
  essential_attrs 포함관계로 direct parents 반환. 정사각형 → [마름모, 직사각형].
- `ExpansionGeneratorBase`: LLM 연결용 추상 인터페이스 (Phase 4)
  generate(action) → raw JSON. 상속하여 Anthropic API 연결.

### 다음 (Phase 5)
- CORRECTION action 자동 처리 (현재 DEPTH/WIDTH만, CORRECTION skip)
- 실제 LLM generator 구현체 (ExpansionGeneratorBase 상속)
- LLMs4OL TaskB/C 데이터셋 벤치마크
- corpus 기반 expansion 트리거 (TaxoAdapt 빈도 분석)

### 장기
- LLMs4OL TaskB/C 데이터셋으로 Gate 정확도 벤치마크
- corpus 연동: expansion 트리거를 문서 빈도 기반으로 전환

### 이름 변환표 (계획 — v7에서 파일 생성 예정, v6.3에는 미존재)

파일들이 실제로 존재하지 않습니다. v7에서 생성 예정인 후보 이름입니다.
