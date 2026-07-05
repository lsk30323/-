"""
QA 검증 스크립트 — concept_gate_v7 계약 검증

이 스크립트는 같은 디렉토리의 concept_gate_v7.py만 import하며,
외부 라이브러리(pydantic, unidecode 등)나 LLM API가 필요 없습니다.

실행:
    python qa_v7.py

검증 항목:
  PART A. v6.3 단독 동작 (14건) — 소스 파일 내장 테스트 재실행
  PART B. TaxoAdapt 이식 검증 (get_siblings) — 독립 시나리오
  PART C. 통합 계약 검증 — INTEGRATION_NOTES.md가 약속한 API 표면 확인
  PART D. 회귀 불변식 — 상태 전이/엣지 안전성
  PART E. v7 Phase 1-3 — PostDAG, ExpansionPlanner, 재진입 루프
  PART F. v7 Phase 4 — ParentCandidateClassifier, generator 인터페이스
  PART G. v7 Phase 5 — Heuristic generator, dedup, HistoryAnalyzer
  PART H. GraphExporter — JSON/Mermaid/GraphML 내보내기
  PART I. Phase A/B — UFO 판별 가이드, relation_hint, STRUCTURAL 파싱
  PART J. Phase C1/C2 — CompositionGate 공리 + UFO 안티패턴
  PART K. Phase C3 — relational_scaling 파생·멱등성
  PART L. 구성 vs 구조 혼동 — Transformer/Attention 실 도메인 시나리오

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

# ═════════════════════════════════════════════
# PART I. v7 Phase B — has-a/STRUCTURAL + relation_hint (obo-relations 조립)
# ═════════════════════════════════════════════
print("\n[PART I] Phase B: STRUCTURAL + relation_hint")

# I1. STRUCTURAL은 비-essential (DAG 간선 미형성)
R.check("I1 STRUCTURAL 비-essential",
        cg.FeatureType.STRUCTURAL not in cg.ISA_ALLOWED_TYPES)

# I2. LLM이 structural_composition을 직접 출력 → STRUCTURAL로 파싱
import json as _json
raw = _json.dumps({"expansions": [{"concept": "자동차", "new_features": [
    {"feature": "엔진", "type": "structural_composition",
     "evidence": "자동차는 엔진을 가진다", "relation_hint": "component_of"},
]}]}, ensure_ascii=False)
cs, _ = cg.parse_expansion_response(raw, [NC("자동차", [])])
eng = next(f for f in cs[0].features if f.feature == "엔진")
R.check("I2 structural_composition 직접 출력 → STRUCTURAL", eng.type == cg.FeatureType.STRUCTURAL)

# I3. relation_hint=is_a + essential → essential 유지 (교정 없이 통과)
raw2 = _json.dumps({"expansions": [{"concept": "고양이", "new_features": [
    {"feature": "포유류", "type": "essential_feature",
     "evidence": "분류학상 포유강", "relation_hint": "is_a"},
]}]}, ensure_ascii=False)
cs2, _ = cg.parse_expansion_response(raw2, [NC("고양이", [])])
mam = next(f for f in cs2[0].features if f.feature == "포유류")
R.check("I3 is_a + essential → ESSENTIAL 유지", mam.type == cg.FeatureType.ESSENTIAL)

# I4. SemanticTypeInference 구조 마커
r_struct = cg.SemanticTypeInference.infer("구성요소", "", "")
R.check("I4 구성요소 → STRUCTURAL", r_struct.inferred_type == cg.FeatureType.STRUCTURAL)

# I5. obo-relations subtree 조립 (core.obo 로드, fallback 아님)
import cg_partwhole as _pw
_rels = _pw.load_obo_partwhole()
R.check("I5 obo part_of/has_part 로드",
        "BFO:0000050" in _rels and "BFO:0000051" in _rels and _rels["BFO:0000050"]["transitive"])

# I6. composition_view: STRUCTURAL만 구성 그래프에, DAG(is-a)와 분리
ST = cg.FeatureType.STRUCTURAL
_cs = [
    NC("자동차", [feat("탈것", "이동수단"), NF("엔진", ST, "엔진을 가진다", "엔진을 가진다")]),
    NC("보트",   [feat("탈것", "이동수단"), NF("엔진", ST, "엔진을 가진다", "엔진을 가진다")]),
]
_dr = cg.DAGReasoner(_cs)
_out = _dr.finalize()
comp = _out["composition"]
R.check("I6 composition edges에 STRUCTURAL만",
        ("자동차", "엔진") in comp["edges"] and ("보트", "엔진") in comp["edges"]
        and all(p != "탈것" for _, p in comp["edges"]))

# I7. shared_parts: 엔진이 자동차·보트 양쪽에 → UFO shareable 감지
R.check("I7 shared_parts 엔진 공유 감지",
        comp["shared_parts"].get("엔진") == ["보트", "자동차"])

# ═════════════════════════════════════════════
# PART J. v7 Phase C1/C2 — CompositionGate + UFO Anti-Pattern
# ═════════════════════════════════════════════
print("\n[PART J] Phase C1/C2: CompositionGate + UFO Anti-Pattern")

def _st(name, ev="ev"):
    return NF(name, ST, ev, ev)

# J1. 반대칭: A has B + B has A → ERROR
_ja = NC("A", [feat("x", "ev"), _st("B", "A는 B를 부분으로")])
_jb = NC("B", [feat("y", "ev"), _st("A", "B는 A를 부분으로")])
_jrep, _jiss = cg.CompositionGate.detect(cg.DAGReasoner([_ja, _jb]))
R.check("J1 반대칭 → ERROR + antisymmetry issue",
        any(i["kind"] == "antisymmetry" for i in _jiss)
        and any(g.severity == GS.ERROR and not g.passed for g in _jrep.results))

# J2. 순환: 가→나→다→가 추이 폐쇄 → ERROR
_c1 = NC("가", [_st("나", "가는 나를 부분으로")])
_c2 = NC("나", [_st("다", "나는 다를 부분으로")])
_c3 = NC("다", [_st("가", "다는 가를 부분으로")])
_j2rep, _j2iss = cg.CompositionGate.detect(cg.DAGReasoner([_c1, _c2, _c3]))
R.check("J2 순환 → ERROR + cycle issue",
        any(i["kind"] == "cycle" for i in _j2iss)
        and any(g.severity == GS.ERROR and not g.passed for g in _j2rep.results))

# J3. is-a/has-a 배타: 부모가 자식을 part로 선언 → NEEDS_CORRECTION
_jp = NC("동물", [feat("생물", "생명체"), _st("개", "동물은 개를 부분으로")])
_jc = NC("개", [feat("생물", "생명체"), feat("충성", "충성스러움")])
_r3 = cg.DAGReasoner([_jp, _jc])
_r3.add_edge("동물", "개")
_j3rep, _j3iss = cg.CompositionGate.detect(_r3)
R.check("J3 is-a/has-a 배타 → NEEDS_CORRECTION + conflict issue",
        any(i["kind"] == "isa_hasa_conflict" for i in _j3iss)
        and any(g.severity == GS.NEEDS_CORRECTION for g in _j3rep.results))

# J7. 무위반 입력 → passed + 빈 issues + run() 키 노출
_jx = NC("자동차", [feat("탈것", "이동수단"), _st("엔진", "엔진을 가진다")])
_jy = NC("보트", [feat("탈것", "이동수단"), _st("엔진", "엔진을 가진다")])
_j7rep, _j7iss = cg.CompositionGate.detect(cg.DAGReasoner([_jx, _jy]))
R.check("J7 무위반 → passed + 빈 issues", _j7rep.passed and _j7iss == [])
_out_j = cg.ConceptPipeline().run([[_jx, _jy]])
R.check("J7 run() composition_issues 키 노출 (빈 리스트)",
        "composition_issues" in _out_j and _out_j["composition_issues"] == [])

# J4. MixRig — 같은 feature가 ESSENTIAL / 비-ESSENTIAL 혼용 → WARNING + issue
_j_mix = [
    NC("스마트폰", [feat("배터리", "필수 전원부"), feat("통신", "무선 통신 기능")]),
    NC("노트북",   [feat("컴퓨팅", "연산 장치"),
                    NF("배터리", ST, "배터리를 부품으로 가진다", "배터리를 부품으로 가진다")]),
]
_j_dr_mix = cg.DAGReasoner(_j_mix)
_j_rep4, _j_iss4 = cg.UFOAntiPatternGate.detect(_j_dr_mix, _j_mix)
_j_mixrig = [i for i in _j_iss4 if i["pattern"] == "MixRig"]
R.check("J4 MixRig 감지 (배터리 E/비E 혼용, WARNING)",
        len(_j_mixrig) == 1 and _j_mixrig[0]["subject"] == "배터리"
        and sorted(_j_mixrig[0]["involved"]) == ["노트북", "스마트폰"]
        and _j_rep4.max_severity == GS.WARNING and _j_rep4.passed,
        f"got {_j_iss4}")

# J5. PartOver — 조상·자손이 같은 part 공유 → WARNING
_j_po = [
    NC("포유류", [feat("젖샘", "포유 특징"),
                  NF("심장", ST, "심장을 가진다", "심장을 가진다")]),
    NC("개",     [feat("젖샘", "포유 특징"), feat("짖음", "짖는다"),
                  NF("심장", ST, "심장을 가진다", "심장을 가진다")]),
]
_j_dr_po = cg.DAGReasoner(_j_po)
_j_dr_po.add_edge("포유류", "개")
_j_rep5, _j_iss5 = cg.UFOAntiPatternGate.detect(_j_dr_po, _j_po)
_j_partover = [i for i in _j_iss5 if i["pattern"] == "PartOver"]
R.check("J5 PartOver 감지 (심장이 포유류·개 중복, WARNING)",
        len(_j_partover) == 1 and _j_partover[0]["subject"] == "심장"
        and sorted(_j_partover[0]["involved"]) == ["개", "포유류"]
        and _j_rep5.max_severity == GS.WARNING,
        f"got {_j_iss5}")

# J6. WholeOver — 한 개념이 part와 그 특수화 동시 보유 → WARNING
_j_wo = [
    NC("자동차", [feat("탈것", "이동수단"),
                  NF("바퀴", ST, "바퀴를 가진다", "바퀴를 가진다"),
                  NF("앞바퀴", ST, "앞바퀴를 가진다", "앞바퀴를 가진다")]),
]
_j_dr_wo = cg.DAGReasoner(_j_wo)
_j_dr_wo.add_edge("바퀴", "앞바퀴")
_j_rep6, _j_iss6 = cg.UFOAntiPatternGate.detect(_j_dr_wo, _j_wo)
_j_wholeover = [i for i in _j_iss6 if i["pattern"] == "WholeOver"]
R.check("J6 WholeOver 감지 (바퀴·앞바퀴 동시 보유, WARNING)",
        len(_j_wholeover) == 1 and _j_wholeover[0]["subject"] == "자동차"
        and sorted(_j_wholeover[0]["involved"]) == ["바퀴", "앞바퀴"]
        and _j_rep6.max_severity == GS.WARNING,
        f"got {_j_iss6}")

# J6b. 무위반 입력 → issues 빈 리스트 + 게이트 passed
_j_clean = [NC("A2", [feat("x", "속성 x")]), NC("B2", [feat("y", "속성 y")])]
_j_dr_cl = cg.DAGReasoner(_j_clean)
_j_repc, _j_issc = cg.UFOAntiPatternGate.detect(_j_dr_cl, _j_clean)
R.check("J6b 무위반 → anti_patterns 빈 리스트 + passed",
        _j_issc == [] and _j_repc.passed and _j_repc.max_severity == GS.INFO)

# J6c. ExpansionPlanner: MixRig → CORRECTION action, PartOver/WholeOver는 무변환
_j_ap = [
    {"pattern": "MixRig", "subject": "배터리", "detail": "혼합", "involved": ["노트북", "스마트폰"]},
    {"pattern": "PartOver", "subject": "심장", "detail": "중복", "involved": ["개", "포유류"]},
]
_j_actions = cg.ExpansionPlanner.plan([], None, _j_ap)
_j_corr = [a for a in _j_actions if a.action_type == cg.ExpansionType.CORRECTION]
R.check("J6c MixRig → CORRECTION action (PartOver 무변환)",
        len(_j_corr) == 1 and "배터리" in _j_corr[0].shared_attrs
        and sorted(_j_corr[0].target_concepts) == ["노트북", "스마트폰"])

# ═════════════════════════════════════════════
# PART K. v7 Phase C3 — RCA relational scaling
# ═════════════════════════════════════════════
print("\n[PART K] Phase C3: relational_scaling")

ST_K = cg.FeatureType.STRUCTURAL

# K1. STRUCTURAL 부분이 개념으로 존재 → ∃has_part.X ESSENTIAL 파생 (원본 유지 + 마커 + 순수성)
k_src = [
    NC("자동차", [feat("탈것", "이동을 위한 수단"), NF("엔진", ST_K, "엔진을 가진다", "엔진을 가진다")]),
    NC("엔진",   [feat("동력장치", "동력을 만드는 장치")]),
]
k_out = cg.relational_scaling(k_src)
k_car = next(c for c in k_out if c.name == "자동차")
k_der = [ft for ft in k_car.features if ft.feature == "∃has_part.엔진"]
R.check("K1 STRUCTURAL 부분(개념 존재) → ∃has_part 파생 E + rca_scaling 마커 + 원본 S 유지",
        len(k_der) == 1 and k_der[0].type == E
        and "rca_scaling" in k_der[0].evidence
        and any(ft.feature == "엔진" and ft.type == ST_K for ft in k_car.features)
        and len(k_src[0].features) == 2,
        f"got {[(ft.feature, ft.type.value) for ft in k_car.features]}")

# K2. 멱등성 — 두 번 적용해도 파생 피처 1개
k_twice = cg.relational_scaling(cg.relational_scaling(k_src))
k_car2 = next(c for c in k_twice if c.name == "자동차")
R.check("K2 멱등성: 2회 적용에도 ∃has_part.엔진 1개",
        sum(1 for ft in k_car2.features if ft.feature == "∃has_part.엔진") == 1)

# K3. 비개념 부분("엔진"이 개념 아님) → 파생 없음, 원본 불변
k_src3 = [NC("자동차", [feat("탈것", "이동을 위한 수단"), NF("엔진", ST_K, "엔진을 가진다", "엔진을 가진다")])]
k_out3 = cg.relational_scaling(k_src3)
R.check("K3 비개념 부분 → 파생 없음 + 원본 불변",
        all(not ft.feature.startswith("∃has_part.") for ft in k_out3[0].features)
        and len(k_out3[0].features) == 2 and len(k_src3[0].features) == 2)

# K4. run_with_expansion 배선 — 기본 off 무변경, opt-in이면 파생이 DAG 간선 종차로
import inspect as _inspect
_sig_k = _inspect.signature(cg.ConceptPipeline.run_with_expansion)
k_wire = [
    NC("탈것",   [feat("이동수단", "이동을 위한 수단")]),
    NC("자동차", [feat("이동수단", "이동을 위한 수단"), NF("엔진", ST_K, "엔진을 가진다", "엔진을 가진다")]),
    NC("엔진",   [feat("동력장치", "동력을 만드는 장치")]),
]
out_k_off = pipe.run_with_expansion(k_wire, generator=None)
out_k_on = pipe.run_with_expansion(k_wire, generator=None, rca_scaling=True)
d_k = out_k_on["result"]["definitions"].get("자동차", {})
R.check("K4 rca_scaling 배선: 기본 False 무변경 + True면 탈것→자동차 간선(종차 ∃has_part.엔진)",
        _sig_k.parameters["rca_scaling"].default is False
        and "∃has_part.엔진" not in str(out_k_off["result"]["definitions"])
        and d_k.get("parents") == ["탈것"] and "∃has_part.엔진" in d_k.get("delta", []),
        f"off_defs={out_k_off['result']['definitions']}, on_car={d_k}")


# ═════════════════════════════════════════════
# PART L. 구성(composition) vs 구조(structure) 혼동 시나리오
# ═════════════════════════════════════════════
# 실 도메인(Transformer/Attention)에서 흔히 일어나는 모델링 오류 4가지 + 올바른 모델링 대조군 1건.
# "어텐션에 정형화된 구조가 있다고 착각" — 메커니즘을 부품으로 취급하는 실수.
print("\n[PART L] 구성 vs 구조 혼동 시나리오 (Transformer/Attention)")

# L1. MixRig — 메커니즘을 구성요소로 착각
# "어텐션"이 한 곳에서는 essential(분류 기준), 다른 곳에서는 structural(부품) → rigidity 혼합.
# 실수: 어텐션은 메커니즘(계산 방법)이지 분리 가능한 부품이 아닌데, 한쪽에서 has-a로 분류.
_l1 = [
    NC("신경망",     [feat("어텐션", "어텐션 메커니즘을 사용하는 모델"), feat("학습", "역전파 학습")]),
    NC("트랜스포머", [feat("학습", "역전파 학습"),
                      NF("어텐션", ST, "어텐션을 핵심 구성요소로 가진다", "어텐션을 핵심 구성요소로 가진다")]),
]
_l1_dr = cg.DAGReasoner(_l1)
_l1_rep, _l1_iss = cg.UFOAntiPatternGate.detect(_l1_dr, _l1)
_l1_mr = [i for i in _l1_iss if i["pattern"] == "MixRig"]
R.check("L1 MixRig: 어텐션이 E(신경망)과 S(트랜스포머)로 혼용 → WARNING",
        len(_l1_mr) == 1 and _l1_mr[0]["subject"] == "어텐션"
        and sorted(_l1_mr[0]["involved"]) == ["신경망", "트랜스포머"],
        f"got {_l1_iss}")

# L2. WholeOver — 개념 패밀리를 단일 부품으로 + 그 특수화도 부품으로
# "트랜스포머 has 어텐션" + "트랜스포머 has 셀프어텐션"인데
# 어텐션 is-a 셀프어텐션(또는 반대) → 부분과 그 특수화 동시 보유.
# 실수: "어텐션"이 정형화된 단일 구조라고 착각하면서, 그 변형도 따로 달아놓음.
_l2 = [
    NC("어텐션",     [feat("가중합", "입력의 가중 합산")]),
    NC("셀프어텐션", [feat("가중합", "입력의 가중 합산"), feat("자기참조", "Q=K=V 동일 시퀀스")]),
    NC("트랜스포머", [feat("시퀀스모델", "시퀀스 변환 모델"),
                      NF("어텐션", ST, "어텐션을 가진다", "어텐션을 가진다"),
                      NF("셀프어텐션", ST, "셀프어텐션을 가진다", "셀프어텐션을 가진다")]),
]
_l2_dr = cg.DAGReasoner(_l2)
_l2_dr.add_edge("어텐션", "셀프어텐션")
_l2_rep, _l2_iss = cg.UFOAntiPatternGate.detect(_l2_dr, _l2)
_l2_wo = [i for i in _l2_iss if i["pattern"] == "WholeOver"]
R.check("L2 WholeOver: 트랜스포머가 어텐션과 셀프어텐션(특수화) 동시 보유 → WARNING",
        len(_l2_wo) == 1 and _l2_wo[0]["subject"] == "트랜스포머"
        and sorted(_l2_wo[0]["involved"]) == ["셀프어텐션", "어텐션"],
        f"got {_l2_iss}")

# L3. PartOver — 상속 부분 중복 선언
# "트랜스포머 has 어텐션" + "인코더(is-a 트랜스포머) has 어텐션"
# → 자식이 부모에게서 상속받을 부분을 중복 선언.
# 실수: 인코더가 트랜스포머의 일종이면, 어텐션은 자동으로 상속됨 — 중복은 모델 오류.
_l3 = [
    NC("트랜스포머", [feat("시퀀스모델", "시퀀스 변환 모델"),
                      NF("어텐션", ST, "어텐션을 가진다", "어텐션을 가진다")]),
    NC("인코더",     [feat("시퀀스모델", "시퀀스 변환 모델"), feat("양방향", "양방향 문맥 참조"),
                      NF("어텐션", ST, "어텐션을 가진다", "어텐션을 가진다")]),
]
_l3_dr = cg.DAGReasoner(_l3)
_l3_dr.add_edge("트랜스포머", "인코더")
_l3_rep, _l3_iss = cg.UFOAntiPatternGate.detect(_l3_dr, _l3)
_l3_po = [i for i in _l3_iss if i["pattern"] == "PartOver"]
R.check("L3 PartOver: 어텐션이 트랜스포머·인코더(조상-자손)에 중복 → WARNING",
        len(_l3_po) == 1 and _l3_po[0]["subject"] == "어텐션"
        and sorted(_l3_po[0]["involved"]) == ["인코더", "트랜스포머"],
        f"got {_l3_iss}")

# L4. is-a/has-a 배타 — is-a 관계인 개념을 has-a로도 선언
# "트랜스포머 is-a 시퀀스모델"인데 "트랜스포머 has 시퀀스모델" (S)로도 선언.
# 실수: "트랜스포머는 시퀀스모델의 일종"이면서 동시에 "시퀀스모델을 부품으로 가진다"는 모순.
_l4 = [
    NC("시퀀스모델", [feat("시퀀스처리", "시퀀스 입력을 처리")]),
    NC("트랜스포머", [feat("시퀀스처리", "시퀀스 입력을 처리"), feat("병렬화", "어텐션으로 병렬 처리"),
                      NF("시퀀스모델", ST, "시퀀스모델을 구조로 가진다", "시퀀스모델을 구조로 가진다")]),
]
_l4_dr = cg.DAGReasoner(_l4)
_l4_dr.add_edge("시퀀스모델", "트랜스포머")
_l4_rep, _l4_iss = cg.CompositionGate.detect(_l4_dr)
_l4_conf = [i for i in _l4_iss if i["kind"] == "isa_hasa_conflict"]
R.check("L4 is-a/has-a 배타: 트랜스포머 is-a 시퀀스모델인데 has-a로도 선언 → NEEDS_CORRECTION",
        len(_l4_conf) == 1 and _l4_conf[0]["whole"] == "트랜스포머"
        and _l4_conf[0]["part"] == "시퀀스모델",
        f"got {_l4_iss}")

# L5. 복합 시나리오 — end-to-end pipeline 통과
# 올바른 모델링: 메커니즘은 functional, 실제 모듈은 structural, 분류는 essential.
# 게이트 위반 없이 is-a DAG + composition 그래프 모두 정상 생성되어야 한다.
_l5 = [
    NC("시퀀스모델", [feat("시퀀스처리", "시퀀스 입력을 처리")]),
    NC("트랜스포머", [feat("시퀀스처리", "시퀀스 입력을 처리"), feat("병렬화", "어텐션으로 병렬 처리"),
                      NF("인코더블록", ST, "인코더 블록을 쌓아 구성", "인코더 블록을 쌓아 구성"),
                      NF("디코더블록", ST, "디코더 블록을 쌓아 구성", "디코더 블록을 쌓아 구성")]),
]
_l5_out = cg.ConceptPipeline().run([_l5])
_l5_comp = _l5_out["result"].get("composition", {})
R.check("L5 올바른 모델링: PASS + 트랜스포머 is-a 시퀀스모델 + composition에 인코더/디코더블록",
        _l5_out["status"] in ("PASS", "PASS_WITH_REPAIR")
        and "시퀀스모델" in dict(_l5_out["result"]["dag"])
        and ("트랜스포머", "인코더블록") in _l5_comp.get("edges", [])
        and ("트랜스포머", "디코더블록") in _l5_comp.get("edges", [])
        and _l5_out.get("composition_issues", []) == []
        and _l5_out.get("anti_patterns", []) == [],
        f"status={_l5_out['status']}, dag={dict(_l5_out['result']['dag'])}, comp={_l5_comp}")

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
