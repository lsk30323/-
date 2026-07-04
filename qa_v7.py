"""
QA 검증 스크립트 — concept_gate_v6.3 + TaxoAdapt 통합

이 스크립트는 같은 디렉토리의 concept_gate_v7.py만 import하며,
외부 라이브러리(pydantic, unidecode 등)나 LLM API가 필요 없습니다.

실행:
    python qa_v6_3.py

검증 항목:
  PART A. v6.3 단독 동작 (14건) — 소스 파일 내장 테스트 재실행
  PART B. TaxoAdapt 이식 검증 (get_siblings) — 독립 시나리오
  PART C. 통합 계약 검증 — INTEGRATION_NOTES.md가 약속한 API 표면 확인
  PART D. 회귀 불변식 — 상태 전이/엣지 안전성
  PART E. v7 Phase 1-3 — PostDAG, ExpansionPlanner, 재진입 루프
  PART F. v7 Phase 4 — ParentCandidateClassifier, generator 인터페이스
  PART G. v7 Phase 5 — Heuristic generator, dedup, HistoryAnalyzer
  PART H. GraphExporter — JSON/Mermaid/GraphML 내보내기

각 PART는 독립이며, 하나가 실패해도 나머지는 계속 실행됩니다.
종료 코드: 모두 통과 0, 하나라도 실패 1.
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "concept_gate_v7.py"

if not SRC.exists():
    print(f"[FATAL] concept_gate_v7.py가 {HERE}에 없습니다.")
    print("        v6.3 소스를 이 스크립트와 같은 디렉토리에 두세요.")
    sys.exit(2)

# dataclass의 모듈 해석을 위해 sys.path 기반 import 사용
sys.path.insert(0, str(HERE))
import concept_gate_v7 as cg

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

# [v7] 범위 경계 — v7에 있어야/없어야 하는 것
R.check("C8 v7에 ExpansionPlanner 존재해야 함",
        hasattr(cg, "ExpansionPlanner"))
R.check("C9 v7에 PostDAGSiblingGate 존재해야 함",
        hasattr(cg, "PostDAGSiblingGate"))
R.check("C10 v7에 PreDAGSignatureGate 존재해야 함",
        hasattr(cg, "PreDAGSignatureGate"))
R.check("C11 v7 Phase 4에 ParentCandidateClassifier 존재해야 함",
        hasattr(cg, "ParentCandidateClassifier"))
R.check("C12 v7 Phase 4에 ExpansionGeneratorBase 존재해야 함",
        hasattr(cg, "ExpansionGeneratorBase"))
R.check("C13 v7 Phase 4에 StaticExpansionGenerator 존재해야 함",
        hasattr(cg, "StaticExpansionGenerator"))
R.check("C14 LLM 직접 호출 클래스는 없어야 함 (외부 generator로 주입)",
        not hasattr(cg, "AnthropicExpansionGenerator") and
        not hasattr(cg, "LLMExpansionGenerator"))

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

# ═════════════════════════════════════════════
# PART E. v7 Phase 1-3 기능 검증
# ═════════════════════════════════════════════
print("\n[PART E] v7 Phase 1-3")
import json as _json

# E1. PostDAGSiblingGate: edge 있는 same-essential sibling 탐지
dag_e = cg.DAGReasoner([
    NC("도형",[feat("도형","도형이다")]),
    NC("A",[feat("도형","도형이다"), feat("색","색 있음")]),
    NC("B",[feat("도형","도형이다"), feat("색","색 있음")]),
])
dag_e.add_edge("도형","A"); dag_e.add_edge("도형","B")
_, post_iss = cg.PostDAGSiblingGate.detect(dag_e, [
    NC("도형",[feat("도형","도형이다")]),
    NC("A",[feat("도형","도형이다"), feat("색","색 있음")]),
    NC("B",[feat("도형","도형이다"), feat("색","색 있음")]),
])
R.check("E1 PostDAG same-essential sibling → SIBLING_UNDERSPECIFIED",
        len(post_iss) > 0 and post_iss[0].get("severity") == "SIBLING_UNDERSPECIFIED")

# E2. ExpansionPlanner: WARNING → DEPTH action
acts = cg.ExpansionPlanner.plan(
    [{"same_essential_signature": ["X","Y"], "attrs": ["a"], "severity": "WARNING_UNDERSPECIFIED", "correction": "t"}])
R.check("E2 WARNING_UNDERSPECIFIED → DEPTH action",
        len(acts) == 1 and acts[0].action_type == cg.ExpansionType.DEPTH)

# E3. run() 결과에 expansion_actions, post_dag_issues 키
out_e = pipe.run([[NC("개",[feat("동물","살아있는 생명체")]), NC("고양이",[feat("동물","살아있는 생명체")])]])
R.check("E3 run() 결과에 expansion_actions + post_dag_issues 키",
        "expansion_actions" in out_e and "post_dag_issues" in out_e)

# E4. expansion 파서: 정상 입력
raw_ok = _json.dumps({"expansions": [
    {"concept": "개", "new_features": [{"feature": "가축화", "type": "essential_feature", "evidence": "가축화된 동물"}]}
]}, ensure_ascii=False)
merged, prep = cg.parse_expansion_response(raw_ok, [NC("개",[feat("동물","살아있는 생명체")])])
R.check("E4 expansion 파싱 정상 → 가축화 추가",
        prep.passed and any(ft.feature == "가축화" for c in merged if c.name == "개" for ft in c.features))

# E5. expansion 파서: 스키마 위반
_, prep_bad = cg.parse_expansion_response('{"expansions": [{"concept": "개"}]}', [NC("개",[feat("동물","생명체")])])
R.check("E5 new_features 누락 → ERROR", not prep_bad.passed)

# E6. run_with_expansion 수렴
mock = cg.MockExpansionGenerator({
    "개": [{"feature": "가축화", "type": "essential_feature", "evidence": "가축화된 동물"}],
    "고양이": [{"feature": "독립성", "type": "essential_feature", "evidence": "독립적 동물"}],
})
out_loop = pipe.run_with_expansion(
    [NC("개",[feat("동물","살아있는 생명체")]), NC("고양이",[feat("동물","살아있는 생명체")])],
    generator=mock, max_expansion_rounds=2)
hist = out_loop.get("expansion_history", [])
R.check("E6 run_with_expansion: round0 WARNING → 최종 PASS",
        hist[0]["status"] == "PASS_WITH_WARNING" and out_loop["status"] == "PASS",
        f"final={out_loop['status']}")

# E7. generator=None → 확장 안 함
out_n = pipe.run_with_expansion([NC("개",[feat("동물","생명체")]), NC("고양이",[feat("동물","생명체")])], generator=None)
R.check("E7 generator=None → 확장 history 1개",
        len(out_n.get("expansion_history", [])) == 1)

# ═════════════════════════════════════════════
# PART F. v7 Phase 4 — ParentCandidateClassifier + generator
# ═════════════════════════════════════════════
print("\n[PART F] v7 Phase 4")

# F1. 단일 부모 (indirect 제거)
existing_f = [
    NC("동물",[feat("동물","살아있는 생명체")]),
    NC("포유류",[feat("동물","살아있는 생명체"), feat("젖","젖을 먹임")]),
]
new_dog = NC("개",[feat("동물","살아있는 생명체"), feat("젖","젖을 먹임"), feat("가축화","가축화됨")])
parents = cg.ParentCandidateClassifier.classify(new_dog, existing_f + [new_dog])
R.check("F1 개 → 포유류 (동물은 indirect)", parents == ["포유류"], f"got {parents}")

# F2. 다중 부모 (meet)
existing_meet = [
    NC("사각형",[feat("4변","네 변"), feat("4각","네 각")]),
    NC("직사각형",[feat("4변","네 변"), feat("4각","네 각"), feat("직각","직각")]),
    NC("마름모",[feat("4변","네 변"), feat("4각","네 각"), feat("등변","등변")]),
]
new_sq = NC("정사각형",[feat("4변","네 변"), feat("4각","네 각"), feat("직각","직각"), feat("등변","등변")])
parents_sq = cg.ParentCandidateClassifier.classify(new_sq, existing_meet + [new_sq])
R.check("F2 정사각형 → 다중 부모 [마름모, 직사각형]",
        parents_sq == ["마름모", "직사각형"], f"got {parents_sq}")

# F3. root → 부모 없음
parents_root = cg.ParentCandidateClassifier.classify(NC("동물",[feat("동물","생명체")]), existing_f)
R.check("F3 동물(root) → 부모 없음", parents_root == [])

# F4. StaticExpansionGenerator는 ExpansionGeneratorBase
gen = cg.StaticExpansionGenerator()
gen.add_response("개", [{"feature": "가축화", "type": "essential_feature", "evidence": "가축화된 동물"}])
R.check("F4 StaticExpansionGenerator는 ExpansionGeneratorBase",
        isinstance(gen, cg.ExpansionGeneratorBase))

# F5. Base.generate() → NotImplementedError
import json as _json2
base = cg.ExpansionGeneratorBase()
try:
    base.generate(cg.ExpansionAction(cg.ExpansionType.DEPTH, ["x"], []))
    R.check("F5 Base.generate() → NotImplementedError", False)
except NotImplementedError:
    R.check("F5 Base.generate() → NotImplementedError", True)

# F6. run_with_expansion → parent_candidates
gen_full = cg.StaticExpansionGenerator({
    "개": [{"feature": "가축화", "type": "essential_feature", "evidence": "가축화된 동물"}],
    "고양이": [{"feature": "독립성", "type": "essential_feature", "evidence": "독립적 동물"}],
})
out_f = pipe.run_with_expansion(
    [NC("동물",[feat("동물","살아있는 생명체")]),
     NC("개",[feat("동물","살아있는 생명체")]),
     NC("고양이",[feat("동물","살아있는 생명체")])],
    generator=gen_full, max_expansion_rounds=2)
R.check("F6 run_with_expansion → parent_candidates 키", "parent_candidates" in out_f)

pc = out_f.get("parent_candidates", {})
R.check("F7 개·고양이 → 동물 부모", pc.get("개") == ["동물"] and pc.get("고양이") == ["동물"], f"got {pc}")

# F8. CORRECTION action 자동 처리 (non-sparse same signature)
gen_corr = cg.StaticExpansionGenerator({
    "X": [{"feature": "x고유", "type": "essential_feature", "evidence": "X에만 있는 속성"}],
    "Y": [{"feature": "y고유", "type": "essential_feature", "evidence": "Y에만 있는 속성"}],
})
out_corr = pipe.run_with_expansion(
    [NC("X", [feat("a","근거 텍스트 입력"), feat("b","근거 텍스트 입력")]),
     NC("Y", [feat("a","근거 텍스트 입력"), feat("b","근거 텍스트 입력")])],
    generator=gen_corr, max_expansion_rounds=2)
hist_corr = out_corr.get("expansion_history", [])
R.check("F8 CORRECTION: round0 NEEDS_CORRECTION → 수렴",
        len(hist_corr) >= 2 and hist_corr[0]["status"] == "NEEDS_CORRECTION"
        and hist_corr[-1]["status"] in ("PASS", "PASS_WITH_WARNING"),
        f"got {[h['status'] for h in hist_corr]}")

# ═════════════════════════════════════════════
# PART G. v7 Phase 5 — Heuristic + dedup + HistoryAnalyzer
# ═════════════════════════════════════════════
print("\n[PART G] v7 Phase 5")

# G1. ExpansionPlanner dedup
dup_issues = [
    {"same_essential_signature": ["A","B"], "attrs": ["x"], "severity": "WARNING_UNDERSPECIFIED", "correction": "t"},
    {"same_essential_signature": ["B","A"], "attrs": ["x"], "severity": "WARNING_UNDERSPECIFIED", "correction": "t"},
]
R.check("G1 dedup: 같은 targets → 1개", len(cg.ExpansionPlanner.plan(dup_issues)) == 1)

# G2. HeuristicExpansionGenerator lexicon
heur = cg.HeuristicExpansionGenerator({"개": [{"feature": "가축화", "type": "essential_feature", "evidence": "가축화된 동물"}]})
import json as _json3
ph = _json3.loads(heur.generate(cg.ExpansionAction(cg.ExpansionType.DEPTH, ["개"], ["동물"])))
R.check("G2 Heuristic lexicon (개→가축화)",
        ph["expansions"][0]["new_features"][0]["feature"] == "가축화")

# G3. fallback template
pfb = _json3.loads(heur.generate(cg.ExpansionAction(cg.ExpansionType.DEPTH, ["미지"], [])))
R.check("G3 fallback template (미지→고유속성)",
        "미지_고유속성" in pfb["expansions"][0]["new_features"][0]["feature"])

# G4. fallback off → skip
heur_off = cg.HeuristicExpansionGenerator({}, fallback_template=False)
R.check("G4 fallback off → 빈 expansions",
        len(_json3.loads(heur_off.generate(cg.ExpansionAction(cg.ExpansionType.DEPTH, ["x"], [])))["expansions"]) == 0)

# G5. Heuristic으로 수렴 + analysis
heur_full = cg.HeuristicExpansionGenerator({
    "개": [{"feature": "가축화", "type": "essential_feature", "evidence": "가축화된 동물"}],
    "고양이": [{"feature": "독립성", "type": "essential_feature", "evidence": "독립적 동물"}],
})
out_h = pipe.run_with_expansion(
    [NC("개",[feat("동물","살아있는 생명체")]), NC("고양이",[feat("동물","살아있는 생명체")])],
    generator=heur_full, max_expansion_rounds=2)
R.check("G5 Heuristic 확장 → PASS + verdict=converged",
        out_h["status"] == "PASS" and
        out_h.get("expansion_analysis", {}).get("verdict") == cg.ExpansionHistoryAnalyzer.CONVERGED)

# G6. NO_OP 판정
out_noop = pipe.run_with_expansion(
    [NC("개",[feat("동물","살아있는 생명체")]), NC("고양이",[feat("동물","살아있는 생명체")])], generator=None)
R.check("G6 generator=None → NO_OP",
        cg.ExpansionHistoryAnalyzer.analyze(out_noop["expansion_history"])["verdict"]
        == cg.ExpansionHistoryAnalyzer.NO_OP)

# G7. STALLED/OSCILLATING (빈 종차)
out_stall = pipe.run_with_expansion(
    [NC("개",[feat("동물","살아있는 생명체")]), NC("고양이",[feat("동물","살아있는 생명체")])],
    generator=cg.HeuristicExpansionGenerator({}, fallback_template=False), max_expansion_rounds=2)
R.check("G7 빈 종차 → STALLED/OSCILLATING",
        out_stall.get("expansion_analysis", {}).get("verdict")
        in (cg.ExpansionHistoryAnalyzer.STALLED, cg.ExpansionHistoryAnalyzer.OSCILLATING))

# ═════════════════════════════════════════════
# PART H. GraphExporter (cg_graph_export.py)
# ═════════════════════════════════════════════
print("\n[PART H] GraphExporter")

try:
    from cg_graph_export import GraphExporter
    _ge_avail = True
except ImportError:
    _ge_avail = False
    R.check("H0 cg_graph_export.py import", False, "모듈 없음")

if _ge_avail:
    out_g = pipe.run([[
        NC("사각형",[feat("4변","네 개의 변을 가짐"),feat("4각","네 개의 꼭짓점")]),
        NC("직사각형",[feat("4변","네 개의 변을 가짐"),feat("4각","네 개의 꼭짓점"),feat("직각","네 각이 모두 직각")]),
        NC("마름모",[feat("4변","네 개의 변을 가짐"),feat("4각","네 개의 꼭짓점"),feat("등변","네 변의 길이가 같음")]),
        NC("정사각형",[feat("4변","네 개의 변을 가짐"),feat("4각","네 개의 꼭짓점"),feat("직각","네 각이 모두 직각"),feat("등변","네 변의 길이가 같음")]),
    ]])

    gj = _json3.loads(GraphExporter.to_json(out_g))
    R.check("H1 to_json: 정사각형 edge 2개",
            sum(1 for e in gj["edges"] if e["to"] == "정사각형") == 2)

    gm = GraphExporter.to_mermaid(out_g)
    R.check("H2 to_mermaid: graph TD + 화살표", gm.startswith("graph TD") and "-->" in gm)

    import xml.etree.ElementTree as _ET
    gx = GraphExporter.to_graphml(out_g)
    R.check("H3 to_graphml: XML 파싱 + is_a", _ET.fromstring(gx) is not None and "is_a" in gx)

    gs = GraphExporter.summary(out_g)
    R.check("H4 summary: edge=4, meet=1, max_level=2",
            gs["edge_count"] == 4 and gs["meet_count"] == 1 and gs["max_level"] == 2)

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
