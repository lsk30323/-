"""
QA 검증 스크립트 — concept_gate_v6.3 + TaxoAdapt 통합

이 스크립트는 같은 디렉토리의 concept_gate_v6_3.py만 import하며,
외부 라이브러리(pydantic, unidecode 등)나 LLM API가 필요 없습니다.

실행:
    python qa_v6_3.py

검증 항목:
  PART A. v6.3 단독 동작 (14건) — 소스 파일 내장 테스트 재실행
  PART B. TaxoAdapt 이식 검증 (get_siblings) — 독립 시나리오
  PART C. 통합 계약 검증 — INTEGRATION_NOTES.md가 약속한 API 표면 확인
  PART D. 회귀 불변식 — 상태 전이/엣지 안전성

각 PART는 독립이며, 하나가 실패해도 나머지는 계속 실행됩니다.
종료 코드: 모두 통과 0, 하나라도 실패 1.
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "concept_gate_v6_3.py"

if not SRC.exists():
    print(f"[FATAL] concept_gate_v6_3.py가 {HERE}에 없습니다.")
    print("        v6.3 소스를 이 스크립트와 같은 디렉토리에 두세요.")
    sys.exit(2)

# dataclass의 모듈 해석을 위해 sys.path 기반 import 사용
sys.path.insert(0, str(HERE))
import concept_gate_v6_3 as cg

# 단축 별칭
E = cg.FeatureType.ESSENTIAL
NC = cg.NormalizedConcept
NF = cg.NormalizedFeature
GS = cg.GateSeverity
PS = cg.PipelineStatus
FV = cg.FeatureVerdict

def feat(name, ev, ftype=None):
    return NF(name, ftype or E, ev, ev)

# ─────────────────────────────────────────────
# 테스트 러너
# ─────────────────────────────────────────────
class Results:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.failures = []

    def check(self, label, cond, detail=""):
        if cond:
            self.passed += 1
            print(f"  ✓ {label}")
        else:
            self.failed += 1
            self.failures.append((label, detail))
            print(f"  ✗ {label}  {detail}")

R = Results()

# ═════════════════════════════════════════════
# PART A. v6.3 단독 동작
# ═════════════════════════════════════════════
print("\n[PART A] v6.3 단독 동작")

pipe = cg.ConceptPipeline()
g = cg.ConceptGate()

# A1. concepts not list
c, r = cg.ParseGate.parse('{"concepts": "not a list"}')
R.check("A1 concepts 비-list → ERROR", (not r.passed) and c is None)

# A2. features not list
c, r = cg.ParseGate.parse('{"concepts": [{"name": "A", "features": "bad"}]}')
R.check("A2 features 비-list → ERROR", not r.passed)

# A3. confidence NaN/inf
_, r1 = cg.ParseGate.parse('{"concepts": [{"name": "A", "features": [{"feature": "x", "type": "essential_feature", "evidence": "valid text", "confidence": "NaN"}]}]}')
_, r2 = cg.ParseGate.parse('{"concepts": [{"name": "B", "features": [{"feature": "y", "type": "essential_feature", "evidence": "valid text", "confidence": "Infinity"}]}]}')
R.check("A3 confidence NaN/inf → ERROR", (not r1.passed) and (not r2.passed))

# A4. single concept repair → PASS_WITH_REPAIR
out = pipe.run([[NC("토마토", [feat("생물","생명 활동을 하는 존재"), feat("요리분류","요리에서 채소로 사용됨")])]])
R.check("A4 단일 개념 repair → PASS_WITH_REPAIR",
        out["status"] == "PASS_WITH_REPAIR" and len(out["repairs"]) > 0 and len(out["warnings"]) == 0,
        f"got {out['status']}")

# A5. evidence-only contextual → WarningAction
r5, j5, rp5, wn5 = g.semantic_type_gate(NC("채소성물질", [NF("채소성", E, "요리에서 채소로 분류되어 사용됨")]))
R.check("A5 evidence-only → WarningAction (repairs=0, warnings=1)",
        r5.severity == GS.WARNING and len(rp5) == 0 and len(wn5) == 1 and isinstance(wn5[0], cg.WarningAction))

# A6. sparse sibling → PASS_WITH_WARNING
out = pipe.run([[NC("개",[feat("동물","살아있는 생명체")]), NC("고양이",[feat("동물","살아있는 생명체")])]])
R.check("A6 sparse sibling → PASS_WITH_WARNING", out["status"] == "PASS_WITH_WARNING", f"got {out['status']}")

# A7. 정사각형 meet
out = pipe.run([[
    NC("사각형",[feat("4변","네 개의 변을 가짐"), feat("4각","네 개의 꼭짓점")]),
    NC("직사각형",[feat("4변","네 개의 변을 가짐"), feat("4각","네 개의 꼭짓점"), feat("직각","네 각이 모두 직각")]),
    NC("마름모",[feat("4변","네 개의 변을 가짐"), feat("4각","네 개의 꼭짓점"), feat("등변","네 변의 길이가 같음")]),
    NC("정사각형",[feat("4변","네 개의 변을 가짐"), feat("4각","네 개의 꼭짓점"), feat("직각","네 각이 모두 직각"), feat("등변","네 변의 길이가 같음")]),
]])
d = out["result"]["definitions"].get("정사각형", {})
R.check("A7 정사각형 = 마름모 ∧ 직사각형 (meet)",
        out["status"] == "PASS" and d.get("is_meet") and sorted(d.get("parents",[])) == ["마름모","직사각형"])

# A8. 체온유지 evidence noise
rw, jw, rpw, wnw = g.semantic_type_gate(NC("고래", [NF("체온유지", E, "수중생활에서도 체온 유지")]))
R.check("A8 체온유지 evidence noise → ACCEPT + warning",
        jw[0].verdict == FV.ACCEPT and len(rpw) == 0 and len(wnw) == 1)

# A9-A14. v6.3 신규
c, r = cg.ParseGate.parse('{"concepts": []}')
R.check("A9 concepts=[] → ERROR", (not r.passed) and c is None)

out = pipe.run([[NC("고래",[feat("체온유지","수중생활에서도 체온 유지"), feat("포유류","포유류에 속하는 동물")])]])
R.check("A10 warning-only → PASS_WITH_WARNING",
        out["status"] == "PASS_WITH_WARNING" and len(out["repairs"]) == 0 and len(out["warnings"]) > 0)

_, r = cg.ParseGate.parse('{"concepts": [{"name": 123, "features": []}]}')
R.check("A11 name 비문자열 → ERROR", not r.passed)

_, r = cg.ParseGate.parse('{"concepts": [{"name": "A", "features": [{"feature": 42, "type": "essential_feature", "evidence": "valid"}]}]}')
R.check("A12 feature name 비문자열 → ERROR", not r.passed)

_, r = cg.ParseGate.parse('{"concepts": [{"name": "A", "features": [{"feature": "x", "type": "essential_feature", "evidence": 999}]}]}')
R.check("A13 evidence 비문자열 → ERROR", not r.passed)

# A14는 PART B에서 get_siblings로 다룸

# ═════════════════════════════════════════════
# PART B. TaxoAdapt 이식 검증 (get_siblings)
# ═════════════════════════════════════════════
print("\n[PART B] TaxoAdapt get_siblings() 이식")

dag = cg.DAGReasoner([
    NC("사각형",[feat("4변","네 개의 변을 가짐"), feat("4각","네 개의 꼭짓점")]),
    NC("직사각형",[feat("4변","네 개의 변을 가짐"), feat("4각","네 개의 꼭짓점"), feat("직각","네 각이 모두 직각")]),
    NC("마름모",[feat("4변","네 개의 변을 가짐"), feat("4각","네 개의 꼭짓점"), feat("등변","네 변의 길이가 같음")]),
])
dag.add_edge("사각형", "직사각형")
dag.add_edge("사각형", "마름모")

sib = dag.get_siblings("직사각형")
R.check("B1 형제 노드 수집 (마름모 포함)", "마름모" in sib)
R.check("B2 자기 자신 제외", "직사각형" not in sib)
R.check("B3 부모 제외 (사각형은 sibling 아님)", "사각형" not in sib)
R.check("B4 루트 노드는 형제 없음", dag.get_siblings("사각형") == set())
R.check("B5 존재하지 않는 노드 → 빈 집합", dag.get_siblings("없는노드") == set())

# ═════════════════════════════════════════════
# PART C. 통합 계약 검증 (API 표면)
# ═════════════════════════════════════════════
print("\n[PART C] INTEGRATION_NOTES 계약 — API 표면 확인")

# C1. PipelineStatus 5단계
expected_statuses = {"PASS","PASS_WITH_REPAIR","PASS_WITH_WARNING","NEEDS_CORRECTION","FAIL"}
actual_statuses = {s.value for s in PS}
R.check("C1 PipelineStatus 5단계", actual_statuses == expected_statuses,
        f"got {sorted(actual_statuses)}")

# C2. GateSeverity 5단계
expected_sev = {"info","repair","warning","needs_correction","error"}
actual_sev = {s.value for s in GS}
R.check("C2 GateSeverity 5단계", actual_sev == expected_sev)

# C3. RepairAction과 WarningAction 분리
R.check("C3 RepairAction / WarningAction 별도 클래스",
        hasattr(cg, "RepairAction") and hasattr(cg, "WarningAction") and cg.RepairAction is not cg.WarningAction)

# C4. semantic_type_gate 4-tuple 반환
ret = g.semantic_type_gate(NC("test", [feat("속성","유효한 근거 텍스트")]))
R.check("C4 semantic_type_gate → 4-tuple (result, judgments, repairs, warnings)",
        isinstance(ret, tuple) and len(ret) == 4)

# C5. DAGReasoner.get_siblings 메서드 존재 (TaxoAdapt 이식 핵심)
R.check("C5 DAGReasoner.get_siblings 메서드 존재",
        hasattr(cg.DAGReasoner, "get_siblings") and callable(cg.DAGReasoner.get_siblings))

# C6. public API: collect_ancestors, direct_parents 노출
R.check("C6 collect_ancestors / direct_parents public 노출",
        hasattr(cg.DAGReasoner, "collect_ancestors") and hasattr(cg.DAGReasoner, "direct_parents"))

# C7. run() 결과에 warnings 키 존재
out = pipe.run([[NC("A",[feat("x","유효한 근거 텍스트")])]])
R.check("C7 run() 결과에 'warnings' 키 존재", "warnings" in out)

# [v6.3.1] 범위 경계 — v6.3에 없어야 하는 것
R.check("C8 v6.3에 ExpansionPlanner 없어야 함 (v7 범위)",
        not hasattr(cg, "ExpansionPlanner"))
R.check("C9 v6.3에 ParentCandidateClassifier 없어야 함 (v7 범위)",
        not hasattr(cg, "ParentCandidateClassifier"))
R.check("C10 RepairAction에 expansion_type 필드 없어야 함 (v7 범위)",
        "expansion_type" not in getattr(cg.RepairAction, "__dataclass_fields__", {}))

# ═════════════════════════════════════════════
# PART D. 회귀 불변식
# ═════════════════════════════════════════════
print("\n[PART D] 회귀 불변식")

# D1. topo_sort 순수성 — finalize 두 번 호출해도 동일
dag2 = cg.DAGReasoner([
    NC("동물",[feat("생물","생명체")]),
    NC("포유류",[feat("생물","생명체"), feat("젖","젖을 먹임")]),
])
dag2.add_edge("동물","포유류")
r_first = dag2.finalize()
r_second = dag2.finalize()
R.check("D1 finalize() 멱등성 (levels 동일)",
        r_first["levels"] == r_second["levels"])

# D2. EdgeBuffer rollback 후 DAG 미오염
buf = cg.EdgeBuffer()
buf.stage("p1", "c1")
buf.stage("p2", "c1")
buf.rollback_child("c1")
R.check("D2 EdgeBuffer rollback 후 staged 비어있음", len(buf.staged_parents) == 0)

# D3. ParseGate 정상 입력은 통과
valid = '{"concepts": [{"name": "동물", "features": [{"feature": "생물", "type": "essential_feature", "evidence": "생명 활동을 함"}]}]}'
c, r = cg.ParseGate.parse(valid)
R.check("D3 정상 JSON 파싱 성공", r.passed and c is not None and len(c) == 1)

# D4. 빈 features 개념 거부
c, r = cg.ParseGate.parse('{"concepts": [{"name": "A", "features": []}]}')
R.check("D4 빈 features 개념 → ERROR", not r.passed)

# D5. AMBIGUOUS → NEEDS_CORRECTION
amb = NC("테스트", [NF("요리분류", E, "생물학적 분류가 아니라 요리 분류")])
ra, ja, rpa, wna = g.semantic_type_gate(amb)
R.check("D5 exception+combo 동시 → AMBIGUOUS (NEEDS_CORRECTION)",
        ra.severity == GS.NEEDS_CORRECTION)

# ─────────────────────────────────────────────
# 요약
# ─────────────────────────────────────────────
print("\n" + "=" * 57)
total = R.passed + R.failed
print(f"  통과: {R.passed}/{total}")
if R.failed:
    print(f"  실패: {R.failed}")
    for label, detail in R.failures:
        print(f"    - {label}  {detail}")
    print("=" * 57)
    sys.exit(1)
else:
    print(f"  전체 통과 ✓")
    print("=" * 57)
    sys.exit(0)
