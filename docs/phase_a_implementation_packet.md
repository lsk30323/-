# Phase A Implementation Packet: UFO-based is-a vs has-a Discrimination

> **설계 이력**: Phase A 원안은 LLM에게 has-a를 `functional`로 출력하도록 지시했으나,
> Phase B에서 STRUCTURAL 타입 추가 후 프롬프트-교정 논리 모순이 발생.
> Option A(프롬프트가 structural_composition을 직접 지시, 교정 로직 삭제)로 해결.
> 아래 문서는 해결 후 현재 코드 상태를 반영한다.

## Goal

Add UFO-based is-a vs has-a discrimination guidance to `build_expansion_prompt()` so the LLM correctly classifies features as ESSENTIAL (is-a) vs STRUCTURAL (has-a) vs FUNCTIONAL/CONTEXTUAL/LOCATIONAL/SOCIAL during concept expansion.

## Constraints

- `FeatureType.STRUCTURAL` 추가됨 (Phase B). `ISA_ALLOWED_TYPES`는 ESSENTIAL만 유지.
- `parse_expansion_response()`의 hint→type 교정 로직은 삭제됨 (Phase A/B 모순 해소).
  LLM이 `structural_composition`을 직접 출력하므로 교정이 불필요.
- All existing tests (60 inline + 84 QA + 30 server) must pass
- Korean language for all prompt text

## Files to Modify

| File | What |
|------|------|
| `/home/user/-/concept_gate_v7.py` | Primary: add `_ufo_discrimination_guide()`, modify `build_expansion_prompt()`, extend `EXPANSION_OUTPUT_SCHEMA` |
| `/home/user/-/files/concept_gate_v7.py` | Copy: identical to primary, `server.py` imports from here. After editing primary, copy it: `cp concept_gate_v7.py files/concept_gate_v7.py` |

No changes needed in `files/server.py`, `qa_v7.py`, or `files/test_server.py`.

## Change 1: Add `_ufo_discrimination_guide()` function

**Location:** Insert at line 864, between the closing `}` of `EXPANSION_OUTPUT_SCHEMA` and `def build_expansion_prompt`.

**What:** A pure function `_ufo_discrimination_guide(mode: ExpansionType) -> str` that returns an XML-tagged Korean-language block with 3 sections, combined per mode.

**Section A — Winston 3-Dimension Test:**
```
<is_a_vs_has_a_test>
후보 속성을 추가하기 전에, 다음 3가지 질문으로 is-a(본질) vs has-a(부분) 관계를 판별하세요:

(1) 기능적 의존성: 전체의 기능이 이 부분에 의존하는가?
    예 → 부분-전체(has-a) 관계 가능성 높음
    아니오 → 속성/종차(is-a) 가능성 높음

(2) 동질성(homeomerous): 부분이 전체와 같은 종류인가?
    예 → 물질/수량 관계 (예: 물 → 수소, 산소)
    아니오 → 구성요소-통합체 또는 멤버-집합 관계

(3) 분리가능성: 부분을 제거해도 전체의 정체성이 유지되는가?
    예 → 비본질적 부분 (functional 또는 contextual_usage로 분류)
    아니오 → 본질적 부분이지만, 여전히 has-a 관계

핵심 원칙: "X는 Y의 일종이다"(is-a)만 essential_feature로.
"X는 Y를 가진다/포함한다"(has-a)는 반드시 다른 type으로.
</is_a_vs_has_a_test>
```

**Section B — UFO Type Mapping:**
```
<ufo_type_mapping>
속성 유형 판별 가이드:

essential_feature (is-a 계층에 사용):
  - 정체성 원리를 제공하는 속성 (해당 개념의 모든 인스턴스가 필연적으로 갖는 속성)
  - 예: "척추동물" → 척추를 가짐, "포유류" → 젖샘/체온조절

structural_composition (has-a 부분-전체):
  - 구성요소-통합체, 멤버-집합 등 부분-전체 관계
  - DL role axiom(∃R.C)에 해당 — is-a DAG에 참여하지 않음
  - 예: "자동차" → 엔진을 가짐, "숲" → 나무를 포함

functional (기능적 속성):
  - 용도, 역할, 기능에 의한 분류 (맥락에 따라 변할 수 있음)
  - 예: "사냥개" → 사냥용도, "식용식물" → 식용가능

contextual_usage (맥락적 용법):
  - 인간의 분류 관행, 시장/요리 맥락
  - 예: "채소" → 요리에서의 분류

locational (장소적 속성):
  - 서식지, 분포 지역, 생태적 위치
  - 예: "담수어" → 민물에 서식

social_treatment (사회적 취급):
  - 법적 지위, 사회적 관행, 문화적 의미
  - 예: "멸종위기종" → 법적 보호 대상
</ufo_type_mapping>
```

**Section C — Part-Whole Patterns:**
```
<part_whole_patterns>
has-a로 분류해야 하는 부분-전체 패턴 6가지:

(1) 구성요소-통합체: 엔진은 자동차의 구성요소 → structural_composition
(2) 멤버-집합: 나무는 숲의 구성원 → structural_composition
(3) 부분-질량: 조각은 파이의 부분 → structural_composition
(4) 재료-대상: 철은 칼의 재료 → essential_feature (재료는 본질이 될 수 있음)
(5) 단계-과정: 유충은 변태의 단계 → contextual_usage
(6) 장소-영역: 오아시스는 사막의 부분 → locational

주의: 재료-대상(4)만 essential_feature가 될 수 있습니다.
구성요소/멤버/부분-질량(1-3)은 structural_composition으로,
단계(5)는 contextual_usage로, 장소(6)는 locational로 분류하세요.
</part_whole_patterns>
```

**Mode-specific composition:**

| Mode | Section A | Section B | Section C |
|------|-----------|-----------|-----------|
| DEPTH | O | O | O |
| WIDTH | O | O | X |
| CORRECTION | X | O | O |

**Implementation:**
```python
def _ufo_discrimination_guide(mode: ExpansionType) -> str:
    section_a = (
        "<is_a_vs_has_a_test>\n"
        # ... section A content ...
        "</is_a_vs_has_a_test>\n"
    )
    section_b = (
        "<ufo_type_mapping>\n"
        # ... section B content ...
        "</ufo_type_mapping>\n"
    )
    section_c = (
        "<part_whole_patterns>\n"
        # ... section C content ...
        "</part_whole_patterns>\n"
    )
    if mode == ExpansionType.DEPTH:
        return f"\n<discrimination_guide>\n{section_a}{section_b}{section_c}</discrimination_guide>\n"
    elif mode == ExpansionType.WIDTH:
        return f"\n<discrimination_guide>\n{section_a}{section_b}</discrimination_guide>\n"
    else:  # CORRECTION
        return f"\n<discrimination_guide>\n{section_b}{section_c}</discrimination_guide>\n"
```

## Change 2: Modify `build_expansion_prompt()`

**Location:** Lines 870-897 in `concept_gate_v7.py`.

**What:** Add is-a/has-a emphasis lines within each mode's `<instruction>` block, then append the discrimination guide.

### DEPTH mode (lines 870-880)

**Current:**
```python
    if action.action_type == ExpansionType.DEPTH:
        body = (
            "<task>differentia_addition</task>\n"
            f"<shared_attrs>{shared}</shared_attrs>\n"
            f"<target_concepts>{targets}</target_concepts>\n"
            "<instruction>\n"
            "다음 개념들이 동일한 essential 속성을 갖고 있어 구분되지 않습니다.\n"
            "각 개념을 구분하는 종차(differentia)를 추가하세요.\n"
            "종차는 다른 개념에는 없고 해당 개념에만 있는 본질적 속성입니다.\n"
            "</instruction>"
        )
```

**New:**
```python
    if action.action_type == ExpansionType.DEPTH:
        body = (
            "<task>differentia_addition</task>\n"
            f"<shared_attrs>{shared}</shared_attrs>\n"
            f"<target_concepts>{targets}</target_concepts>\n"
            "<instruction>\n"
            "다음 개념들이 동일한 essential 속성을 갖고 있어 구분되지 않습니다.\n"
            "각 개념을 구분하는 종차(differentia)를 추가하세요.\n"
            "종차는 다른 개념에는 없고 해당 개념에만 있는 본질적 속성입니다.\n"
            "중요: 종차는 반드시 is-a(분류적) 속성이어야 합니다.\n"
            "부분-전체(has-a), 기능, 장소, 사회적 속성은 해당 type으로 표기하세요.\n"
            "</instruction>"
            + _ufo_discrimination_guide(ExpansionType.DEPTH)
        )
```

### WIDTH mode (lines 881-889)

**Current:**
```python
    elif action.action_type == ExpansionType.WIDTH:
        body = (
            "<task>sibling_discovery</task>\n"
            f"<parent>{action.parent_name}</parent>\n"
            f"<existing_children>{targets}</existing_children>\n"
            "<instruction>\n"
            "이 부모 아래에서 아직 다루어지지 않은 새 하위 개념을 제안하세요.\n"
            "</instruction>"
        )
```

**New:**
```python
    elif action.action_type == ExpansionType.WIDTH:
        body = (
            "<task>sibling_discovery</task>\n"
            f"<parent>{action.parent_name}</parent>\n"
            f"<existing_children>{targets}</existing_children>\n"
            "<instruction>\n"
            "이 부모 아래에서 아직 다루어지지 않은 새 하위 개념을 제안하세요.\n"
            "새 개념은 부모와 is-a 관계여야 합니다 (부모의 일종).\n"
            "부모의 부분(has-a)이나 기능적 역할은 하위 개념이 아닙니다.\n"
            "</instruction>"
            + _ufo_discrimination_guide(ExpansionType.WIDTH)
        )
```

### CORRECTION mode (lines 890-897)

**Current:**
```python
    else:  # CORRECTION
        body = (
            "<task>correction</task>\n"
            f"<target_concepts>{targets}</target_concepts>\n"
            "<instruction>\n"
            "이 개념들은 essential 속성이 없거나 충돌합니다. 수정하세요.\n"
            "</instruction>"
        )
```

**New:**
```python
    else:  # CORRECTION
        body = (
            "<task>correction</task>\n"
            f"<target_concepts>{targets}</target_concepts>\n"
            "<instruction>\n"
            "이 개념들은 essential 속성이 없거나 충돌합니다. 수정하세요.\n"
            "기존 속성 중 has-a(부분-전체) 관계가 essential로 잘못 분류된 것이\n"
            "있을 수 있습니다. 아래 가이드를 참고하여 type을 교정하세요.\n"
            "</instruction>"
            + _ufo_discrimination_guide(ExpansionType.CORRECTION)
        )
```

## Change 3: Extend `EXPANSION_OUTPUT_SCHEMA`

**Location:** Lines 850-854 in `concept_gate_v7.py`.

**Current:**
```python
                            "properties": {
                                "feature": {"type": "string"},
                                "type": {"type": "string"},
                                "evidence": {"type": "string", "minLength": 4},
                            }
```

**New:**
```python
                            "properties": {
                                "feature": {"type": "string"},
                                "type": {"type": "string"},
                                "evidence": {"type": "string", "minLength": 4},
                                "relation_hint": {
                                    "type": "string",
                                    "enum": ["is_a", "component_of", "member_of",
                                             "subcollection_of", "subquantity_of",
                                             "material_of", "phase_of", "located_in"]
                                },
                            }
```

Note: `relation_hint` is NOT added to the `"required"` array (line 849). The `required` list stays `["feature", "type", "evidence"]`.

## Change 4: Update `schema_hint` in `build_expansion_prompt()`

**Location:** Lines 899-912 in `concept_gate_v7.py`.

**Current:**
```python
    schema_hint = (
        '\n\n출력 형식 (JSON):\n'
        '{\n'
        '  "expansions": [\n'
        '    {\n'
        '      "concept": "개념명",\n'
        '      "new_features": [\n'
        '        {"feature": "종차명", "type": "essential_feature", "evidence": "근거 텍스트"}\n'
        '      ],\n'
        '      "reason": "추가 이유"\n'
        '    }\n'
        '  ]\n'
        '}'
    )
```

**New:**
```python
    schema_hint = (
        '\n\n출력 형식 (JSON):\n'
        '{\n'
        '  "expansions": [\n'
        '    {\n'
        '      "concept": "개념명",\n'
        '      "new_features": [\n'
        '        {\n'
        '          "feature": "종차명",\n'
        '          "type": "essential_feature",\n'
        '          "evidence": "근거 텍스트",\n'
        '          "relation_hint": "is_a"\n'
        '        }\n'
        '      ],\n'
        '      "reason": "추가 이유"\n'
        '    }\n'
        '  ]\n'
        '}\n'
        'relation_hint 선택지: is_a, component_of, member_of, '
        'subcollection_of, subquantity_of, material_of, phase_of, located_in'
    )
```

## Change 5: Sync files

After all edits to `/home/user/-/concept_gate_v7.py`:
```bash
cp /home/user/-/concept_gate_v7.py /home/user/-/files/concept_gate_v7.py
```

## Verification

1. Run inline tests: `cd /home/user/- && python3 concept_gate_v7.py`
   - Expect: all 60 tests pass
2. Run QA suite: `cd /home/user/- && python3 qa_v7.py`
   - Expect: all 84 tests pass (Phase B/C에서 PART I/J/K 추가)
3. Manual verification:
   - `build_expansion_prompt()` with DEPTH action should contain `<discrimination_guide>`, `<is_a_vs_has_a_test>`, `<ufo_type_mapping>`, `<part_whole_patterns>`
   - `build_expansion_prompt()` with WIDTH action should contain `<discrimination_guide>`, `<is_a_vs_has_a_test>`, `<ufo_type_mapping>` but NOT `<part_whole_patterns>`
   - `build_expansion_prompt()` with CORRECTION action should contain `<discrimination_guide>`, `<ufo_type_mapping>`, `<part_whole_patterns>` but NOT `<is_a_vs_has_a_test>`
   - `EXPANSION_OUTPUT_SCHEMA` contains `relation_hint` in properties, NOT in required

## What NOT to Change (Phase A 단독 기준 — Phase B/C에서 일부 변경됨)

- `ISA_ALLOWED_TYPES` — ESSENTIAL만 유지 (변경 없음)
- `DAGReasoner.finalize()` — 기존 키 변경 금지, 키 추가만 허용
- `vendor/obo-relations/` — subtree 직접 수정 금지 (wrap/adapt)

> **참고**: Phase B에서 `FeatureType.STRUCTURAL` 추가, `SemanticTypeInference`에
> 구조 마커 추가, `parse_expansion_response()`에서 hint 교정 로직 추가 후 삭제됨.
> Phase C에서 `CompositionGate`, `UFOAntiPatternGate`, `relational_scaling` 추가.

## Git

Branch: `claude/enable-remote-control-Lh6Di`
Commit message suggestion: "Add UFO-based is-a vs has-a discrimination guide to expansion prompts"
