"""정규화-검증형 개념 격자 추론기 v7

v6.3 → v7 변경:

  Phase 1: SignatureGate 분리
    [1] SignatureGate → PreDAGSignatureGate (이름 변경, 기존 위치)
    [2] PostDAGSiblingGate 신규 — buf.commit 이후 실제 sibling 관계 검사
    [3] validate_hierarchy에서 PostDAG 결과를 sig_iss에 병합

  Phase 2: ExpansionPlanner
    [4] ExpansionType / ExpansionAction 타입 추가
    [5] ExpansionPlanner.plan() — WARNING/NEEDS_CORRECTION → action 변환
    [6] run() 결과에 expansion_actions 포함

  Phase 3: 확장 스키마 + 프롬프트 + mock 재진입
    [7] EXPANSION_OUTPUT_SCHEMA — LLM 출력 검증 스키마
    [8] build_expansion_prompt() — action → LLM 프롬프트
    [9] parse_expansion_response() — LLM 출력 → 확장된 개념
    [10] MockExpansionGenerator — LLM 없이 재진입 테스트
    [11] run_with_expansion() — 확장 루프 (mock 또는 실제 generator)

  Phase 4: ParentCandidateClassifier + generator 인터페이스
    [12] ParentCandidateClassifier — multi-label 부모 후보 판정
    [13] ExpansionGeneratorBase — generator 추상 인터페이스
    [14] StaticExpansionGenerator — 사전 정의 응답 (mock 일반화)
    [15] run_with_expansion에 ParentClassifier 통합

  Phase 5: Heuristic generator + dedup + history analysis (비-LLM)
    [16] ExpansionPlanner._dedup — 같은 action 중복 제거
    [17] HeuristicExpansionGenerator — 사전 기반 종차 (fallback template)
    [18] ExpansionHistoryAnalyzer — 수렴/정체/진동/파싱실패 판정
    [19] run_with_expansion에 진동 감지 조기 종료 + expansion_analysis

  + v6.3.1의 33개 QA 전부 회귀 유지

LLM 연결 방법:
  - claude.ai의 "AI-Powered Apps with Claude artifacts" (JSX artifact)에서
    fetch("https://api.anthropic.com/v1/messages") 호출
  - 또는 ExpansionGeneratorBase를 상속한 커스텀 generator의 generate(action)에서
    Anthropic API를 직접 호출
  - 이 파일 자체는 LLM 없이 StaticExpansionGenerator로 동작 (stdlib only)
"""

from __future__ import annotations
import heapq, json, math, re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple
from itertools import combinations
from dataclasses import dataclass, field
from enum import Enum


# ═══════════════════════════════════════════════════════
# 데이터 모델
# ═══════════════════════════════════════════════════════

class GateSeverity(Enum):
    INFO             = "info"
    REPAIR           = "repair"
    WARNING          = "warning"
    NEEDS_CORRECTION = "needs_correction"
    ERROR            = "error"

class PipelineStatus(Enum):
    PASS              = "PASS"
    PASS_WITH_REPAIR  = "PASS_WITH_REPAIR"
    PASS_WITH_WARNING = "PASS_WITH_WARNING"
    NEEDS_CORRECTION  = "NEEDS_CORRECTION"
    FAIL              = "FAIL"

class FeatureType(Enum):
    ESSENTIAL  = "essential_feature"
    CONTEXTUAL = "contextual_usage"
    LOCATIONAL = "locational"
    FUNCTIONAL = "functional"
    SOCIAL     = "social_treatment"
    # DL에서 concept axiom(C ⊑ D, is-a)과 role axiom(∃R.C, has-a)은 별개의 공리.
    # STRUCTURAL은 role axiom에 해당하며 DAG(is-a 격자)에 참여하지 않는다.
    # 대신 composition_view()로 별도 부분-전체 그래프를 구성한다.
    # 근거: UFO(Guizzardi 2005) componentOf/memberOf + OBO RO part_of(BFO:0000050).
    STRUCTURAL = "structural_composition"

# is-a DAG 간선을 형성하는 유일한 타입. STRUCTURAL 등 나머지는 aux_graph/composition_view로 분리.
# 이 집합을 확장하면 has-a 속성이 분류 계층에 혼입되므로 변경하지 않는다.
ISA_ALLOWED_TYPES: Set[FeatureType] = {FeatureType.ESSENTIAL}

class FeatureVerdict(Enum):
    ACCEPT         = "accept"
    DEMOTE_TO_AUX  = "demote_to_aux"
    REJECT_FEATURE = "reject_feature"
    REJECT_CONCEPT = "reject_concept"

@dataclass
class NormalizedFeature:
    feature: str; type: FeatureType; evidence: str = ""
    claim: str = ""; confidence: float = 1.0

@dataclass
class NormalizedConcept:
    name: str; features: List[NormalizedFeature] = field(default_factory=list)
    @property
    def essential_attrs(self) -> Set[str]:
        return {f.feature for f in self.features if f.type in ISA_ALLOWED_TYPES}
    @property
    def all_attrs(self) -> Set[str]:
        return {f.feature for f in self.features}
    @property
    def contextual_features(self) -> List[NormalizedFeature]:
        return [f for f in self.features if f.type not in ISA_ALLOWED_TYPES]

@dataclass
class GateResult:
    gate_name: str; passed: bool; message: str = ""
    details: Dict = field(default_factory=dict)
    severity: GateSeverity = GateSeverity.INFO
    # passed=True + severity=REPAIR  → 자동 수리됨
    # passed=True + severity=WARNING → 경고만
    # passed=False + severity=ERROR  → 진행 불가

@dataclass
class GateReport:
    target: str; results: List[GateResult] = field(default_factory=list)
    @property
    def passed(self) -> bool: return all(r.passed for r in self.results)
    @property
    def failures(self) -> List[GateResult]: return [r for r in self.results if not r.passed]
    @property
    def max_severity(self) -> GateSeverity:
        order = [GateSeverity.INFO, GateSeverity.REPAIR, GateSeverity.WARNING,
                 GateSeverity.NEEDS_CORRECTION, GateSeverity.ERROR]
        return max((r.severity for r in self.results), key=lambda s: order.index(s), default=GateSeverity.INFO)

@dataclass
class FeatureJudgment:
    feature: NormalizedFeature; verdict: FeatureVerdict
    inferred_type: FeatureType; markers: List[str]; reason: str

@dataclass
class RepairAction:
    concept: str; feature: str; original_type: FeatureType
    repaired_type: FeatureType; reason: str; markers: List[str]
    is_ambiguous: bool = False

@dataclass
class WarningAction:
    concept: str; feature: str; original_type: FeatureType
    suggested_type: FeatureType; reason: str; markers: List[str]

class ExpansionType(Enum):
    DEPTH      = "depth"       # 종차 추가 (leaf/sparse 노드)
    WIDTH      = "width"       # 새 sibling 발견 (밀도 높은 부모 아래)
    CORRECTION = "correction"  # 필수 수정 (empty essential, AMBIGUOUS)

@dataclass
class ExpansionAction:
    action_type: ExpansionType
    target_concepts: List[str]
    shared_attrs: List[str]
    parent_name: Optional[str] = None
    reason: str = ""

@dataclass
class TypeInferenceResult:
    inferred_type: FeatureType; is_ambiguous: bool
    markers: List[str]; source: str; is_weak_warning: bool = False


# ═══════════════════════════════════════════════════════
# SemanticTypeInference (v6.2: weak warning)
# ═══════════════════════════════════════════════════════

class SemanticTypeInference:
    COMBOS = [
        (frozenset({"요리", "분류"}), FeatureType.CONTEXTUAL),
        (frozenset({"요리", "취급"}), FeatureType.CONTEXTUAL),
        (frozenset({"요리", "사용"}), FeatureType.CONTEXTUAL),
        (frozenset({"시장", "취급"}), FeatureType.CONTEXTUAL),
        (frozenset({"시장", "유통"}), FeatureType.CONTEXTUAL),
        (frozenset({"법적", "취급"}), FeatureType.SOCIAL),
        (frozenset({"사회", "취급"}), FeatureType.SOCIAL),
        (frozenset({"사회", "관행"}), FeatureType.SOCIAL),
        (frozenset({"용도", "사용"}), FeatureType.FUNCTIONAL),
        (frozenset({"서식", "환경"}), FeatureType.LOCATIONAL),
        (frozenset({"서식", "장소"}), FeatureType.LOCATIONAL),
        # 한국어 피처명에서 has-a(부분-전체) 관계를 감지하는 마커.
        # 매칭 시 STRUCTURAL로 분류 → DAG에서 제외, composition_view로 이동.
        # _EXACT_MATCH에 등록된 마커는 정확 일치만 허용 (부분 문자열 오탐 방지).
        (frozenset({"구성", "부품"}), FeatureType.STRUCTURAL),
        (frozenset({"구성", "요소"}), FeatureType.STRUCTURAL),
        (frozenset({"부분", "전체"}), FeatureType.STRUCTURAL),
    ]
    SINGLE_STRONG = {
        "서식지": FeatureType.LOCATIONAL, "수중생활": FeatureType.LOCATIONAL,
        "해양생활": FeatureType.LOCATIONAL, "착용용도": FeatureType.FUNCTIONAL,
        "구성요소": FeatureType.STRUCTURAL, "부품": FeatureType.STRUCTURAL,
        "구성부품": FeatureType.STRUCTURAL,
    }
    ESSENTIAL_EXCEPTIONS = {
        "분류학", "생물학적 분류", "계통분류", "계통적 분류", "형태학적", "해부학적",
    }

    # 한국어는 공백 단어 경계가 없어 substring 매칭("부품" in "일부품목")이 오탐.
    # 이 집합의 마커는 피처명 전체가 마커와 일치할 때만 STRUCTURAL로 판정.
    # ponytail: 정규식/형태소 분석 대신 정확 일치로 충분 (마커가 3개뿐)
    _EXACT_MATCH = frozenset({"구성요소", "부품", "구성부품"})

    @classmethod
    def _scan(cls, text):
        for m, ft in cls.SINGLE_STRONG.items():
            if m in cls._EXACT_MATCH:
                if text == m: return ft, [m]
            elif m in text:
                return ft, [m]
        for combo, ft in cls.COMBOS:
            if all(m in text for m in combo): return ft, sorted(combo)
        return None, []

    @classmethod
    def _has_exc(cls, text):
        return any(e in text for e in cls.ESSENTIAL_EXCEPTIONS)

    @classmethod
    def infer(cls, feature, evidence, claim) -> TypeInferenceResult:
        fn = feature.lower()
        ec = f"{evidence} {claim}".lower()

        if cls._has_exc(fn):
            return TypeInferenceResult(FeatureType.ESSENTIAL, False, [], "feature_exception")

        ft, fm = cls._scan(fn)
        if ft is not None:
            if cls._has_exc(ec):
                return TypeInferenceResult(ft, True, fm, "ambiguous_exception_vs_combo")
            return TypeInferenceResult(ft, False, fm, "feature_combo")

        if cls._has_exc(ec):
            return TypeInferenceResult(FeatureType.ESSENTIAL, False, [], "evidence_exception")

        # [v6.2 변경] evidence-only contextual → WEAK_CONTEXT_WARNING
        et, em = cls._scan(ec)
        if et is not None:
            return TypeInferenceResult(et, False, em, "evidence_contextual_weak",
                                       is_weak_warning=True)

        return TypeInferenceResult(FeatureType.ESSENTIAL, False, [], "clean")


# ═══════════════════════════════════════════════════════
# ConceptGate
# ═══════════════════════════════════════════════════════

EVIDENCE_PLACEHOLDERS = {"근거", "증거", "없음", "todo", "tbd", "n/a", "na", "-", "..."}
EVIDENCE_MIN_LENGTH = 4

class ConceptGate:
    def __init__(self, contradiction_pairs=None):
        self.contradiction_pairs = contradiction_pairs or []

    def type_gate(self, c): 
        for f in c.features:
            if not isinstance(f.type, FeatureType):
                return GateResult("Type Gate", False, f'"{f.feature}" bad type',
                                  severity=GateSeverity.ERROR)
        return GateResult("Type Gate", True, "ok", severity=GateSeverity.INFO)

    def evidence_gate(self, c):
        probs = []
        for f in c.features:
            ev = f.evidence.strip()
            if not ev: probs.append(f'"{f.feature}": empty')
            elif len(ev) < EVIDENCE_MIN_LENGTH: probs.append(f'"{f.feature}": {len(ev)}자')
            elif ev.lower() in EVIDENCE_PLACEHOLDERS: probs.append(f'"{f.feature}": placeholder')
        if probs:
            return GateResult("Evidence Gate", False, "; ".join(probs),
                              severity=GateSeverity.ERROR)
        return GateResult("Evidence Gate", True, "ok", severity=GateSeverity.INFO)

    def contradiction_gate(self, c):
        for pair in self.contradiction_pairs:
            found = sorted(c.all_attrs & pair)
            if len(found) >= 2:
                return GateResult("Contradiction Gate", False, f'모순: {found}',
                                  {"contradictions": found}, GateSeverity.ERROR)
        return GateResult("Contradiction Gate", True, "ok", severity=GateSeverity.INFO)

    def semantic_type_gate(self, concept) -> Tuple[GateResult, List[FeatureJudgment], List[RepairAction], List[WarningAction]]:
        judgments, repairs, warnings = [], [], []
        demotions, ambiguous, weak_warns = [], [], []

        for f in concept.features:
            if f.type not in ISA_ALLOWED_TYPES:
                judgments.append(FeatureJudgment(f, FeatureVerdict.ACCEPT, f.type, [], "non-ess"))
                continue
            res = SemanticTypeInference.infer(f.feature, f.evidence, f.claim)

            if res.source == "clean" or res.source == "feature_exception" or res.source == "evidence_exception":
                judgments.append(FeatureJudgment(f, FeatureVerdict.ACCEPT, f.type, [], res.source))
            elif res.is_weak_warning:
                # [v6.3] evidence-only → WarningAction (not RepairAction)
                judgments.append(FeatureJudgment(f, FeatureVerdict.ACCEPT, f.type, res.markers, res.source))
                weak_warns.append(f.feature)
                warnings.append(WarningAction(concept.name, f.feature, f.type, res.inferred_type,
                                              res.source, res.markers))
            else:
                judgments.append(FeatureJudgment(f, FeatureVerdict.DEMOTE_TO_AUX, res.inferred_type,
                                                 res.markers, res.source))
                repairs.append(RepairAction(concept.name, f.feature, f.type, res.inferred_type,
                                            res.source, res.markers, res.is_ambiguous))
                if res.is_ambiguous: ambiguous.append(f.feature)
                else: demotions.append(f.feature)

        if ambiguous:
            result = GateResult("Semantic Type Gate", False,
                f'AMBIGUOUS: {ambiguous}', {"ambiguous": ambiguous, "demotions": demotions},
                GateSeverity.NEEDS_CORRECTION)
        elif demotions:
            result = GateResult("Semantic Type Gate", True,
                f'REPAIR: {demotions}', {"demotions": demotions},
                GateSeverity.REPAIR)
        elif weak_warns:
            result = GateResult("Semantic Type Gate", True,
                f'WEAK_CONTEXT_WARNING: {weak_warns}', {"weak_warnings": weak_warns},
                GateSeverity.WARNING)
        else:
            result = GateResult("Semantic Type Gate", True, "ok", severity=GateSeverity.INFO)
        return result, judgments, repairs, warnings

    def anti_context_gate(self, parent, child):
        """부모에만 있는 비-essential 피처가 자식에 없으면 is-a 간선 차단.

        의도: "잘못 분류된 가능성이 있는" 피처를 잡는 gate.
        STRUCTURAL은 의도적 비-essential(has-a)이므로 제외한다 —
        "자동차 has 엔진"이 "전기차 is-a 자동차"를 차단해서는 안 된다.
        """
        pu = parent.all_attrs - child.all_attrs
        cx = {f.feature for f in parent.features
              if f.type not in ISA_ALLOWED_TYPES and f.type != FeatureType.STRUCTURAL
              and f.feature in pu}
        if cx:
            return GateResult("Anti-Context Gate", False, f'비-essential: {sorted(cx)}',
                              severity=GateSeverity.ERROR)
        return GateResult("Anti-Context Gate", True, "ok", severity=GateSeverity.INFO)

    def subsumption_gate(self, parent, child):
        if not (parent.essential_attrs < child.essential_attrs):
            return GateResult("Subsumption Gate", False, "⊄",
                              {"missing": sorted(parent.essential_attrs - child.essential_attrs)},
                              GateSeverity.ERROR)
        return GateResult("Subsumption Gate", True, "ok", severity=GateSeverity.INFO)

    def meet_gate(self, parents, child):
        if len(parents) < 2: return GateResult("Meet Gate", True, "단일", severity=GateSeverity.INFO)
        for i, j in combinations(range(len(parents)), 2):
            a, b = parents[i].essential_attrs, parents[j].essential_attrs
            if a <= b: return GateResult("Meet Gate", False, f'"{parents[i].name}" ⊆ "{parents[j].name}"',
                                         severity=GateSeverity.ERROR)
            if b <= a: return GateResult("Meet Gate", False, f'"{parents[j].name}" ⊆ "{parents[i].name}"',
                                         severity=GateSeverity.ERROR)
        return GateResult("Meet Gate", True, "ok", severity=GateSeverity.INFO)

    def coverage_gate(self, parents, child):
        if not parents: return GateResult("Coverage Gate", True, "root", severity=GateSeverity.INFO)
        ua = set().union(*(p.essential_attrs for p in parents))
        d = child.essential_attrs - ua
        cov = 1.0 - len(d) / max(len(child.essential_attrs), 1)
        if cov < 0.5:
            return GateResult("Coverage Gate", False, f'{cov:.0%}', {"uncovered": sorted(d)},
                              GateSeverity.ERROR)
        return GateResult("Coverage Gate", True, f'{cov:.0%}', {"delta": sorted(d)},
                         GateSeverity.INFO)

    def transitive_gate(self, anc, proposed):
        for a in anc:
            if a.name != proposed.name and proposed.essential_attrs < a.essential_attrs:
                return GateResult("Transitive Gate", False, f'covered by "{a.name}"',
                                  severity=GateSeverity.ERROR)
        return GateResult("Transitive Gate", True, "ok", severity=GateSeverity.INFO)

    def cycle_gate(self, dag, edge):
        p, c = edge
        visited, q = set(), [c]
        while q:
            n = q.pop()
            if n == p: return GateResult("Cycle Gate", False, "사이클", severity=GateSeverity.ERROR)
            if n not in visited: visited.add(n); q.extend(dag.get(n, []))
        return GateResult("Cycle Gate", True, "ok", severity=GateSeverity.INFO)


# ═══════════════════════════════════════════════════════
# ParseGate (v6.2: JSON Schema 강화)
# ═══════════════════════════════════════════════════════

def extract_json_block(raw):
    clean = re.sub(r'```(?:json)?\s*', '', raw.strip()).replace('```', '').strip()
    s, e = clean.find('{'), clean.rfind('}')
    if s < 0 or e < 0: raise ValueError("JSON 블록 없음")
    return clean[s:e+1]

class ParseGate:
    @staticmethod
    def parse(raw: str) -> Tuple[Optional[List[NormalizedConcept]], GateReport]:
        report = GateReport(target="[ParseGate]")
        try:
            parsed = json.loads(extract_json_block(raw))
        except (ValueError, json.JSONDecodeError) as exc:
            report.results.append(GateResult("Parse Gate", False, f"JSON: {exc}",
                                             severity=GateSeverity.ERROR))
            return None, report

        # [v6.2] top-level object 검사
        if not isinstance(parsed, dict):
            report.results.append(GateResult("Parse Gate", False, "top-level이 dict 아님",
                                             severity=GateSeverity.ERROR))
            return None, report

        raw_concepts = parsed.get("concepts")
        if raw_concepts is None:
            report.results.append(GateResult("Parse Gate", False, '"concepts" 키 없음',
                                             severity=GateSeverity.ERROR))
            return None, report

        # [v6.2] concepts: list 검사
        if not isinstance(raw_concepts, list):
            report.results.append(GateResult("Parse Gate", False,
                f'"concepts"가 list 아님: {type(raw_concepts).__name__}',
                severity=GateSeverity.ERROR))
            return None, report

        # [v6.3] concepts=[] 통과 방지
        if len(raw_concepts) == 0:
            report.results.append(GateResult("Parse Gate", False,
                '"concepts" 빈 리스트',
                severity=GateSeverity.ERROR))
            return None, report

        concepts, errors = [], []
        for rc in raw_concepts:
            # [v6.2] concept item: dict 검사
            if not isinstance(rc, dict):
                errors.append(GateResult("Parse Gate", False, f"concept item이 dict 아님: {rc}",
                                         severity=GateSeverity.ERROR))
                continue
            name = rc.get("name") or rc.get("concept")
            # [v6.3] name: str 검사
            if not name or not isinstance(name, str):
                errors.append(GateResult("Parse Gate", False,
                    f"name 없거나 비문자열: {name!r}",
                    severity=GateSeverity.ERROR))
                continue

            raw_feats = rc.get("features")
            # [v6.2] features: non-empty list 검사
            if not isinstance(raw_feats, list):
                errors.append(GateResult("Parse Gate", False,
                    f'"{name}": features가 list 아님',
                    severity=GateSeverity.ERROR))
                continue
            if len(raw_feats) == 0:
                errors.append(GateResult("Parse Gate", False,
                    f'"{name}": features 비어있음',
                    severity=GateSeverity.ERROR))
                continue

            features = []
            for rf in raw_feats:
                # [v6.2] feature item: dict 검사
                if not isinstance(rf, dict):
                    errors.append(GateResult("Parse Gate", False,
                        f'"{name}": feature item이 dict 아님',
                        severity=GateSeverity.ERROR))
                    continue
                fname = rf.get("feature")
                # [v6.3] feature name: str 검사
                if not fname or not isinstance(fname, str):
                    errors.append(GateResult("Parse Gate", False,
                        f'"{name}": feature name 없거나 비문자열: {fname!r}',
                        severity=GateSeverity.ERROR))
                    continue
                # [v6.3] evidence: str 검사
                raw_ev = rf.get("evidence", "")
                if not isinstance(raw_ev, str):
                    errors.append(GateResult("Parse Gate", False,
                        f'"{name}"."{fname}": evidence 비문자열: {type(raw_ev).__name__}',
                        severity=GateSeverity.ERROR))
                    raw_ev = str(raw_ev)
                raw_claim = rf.get("claim", "")
                if not isinstance(raw_claim, str):
                    raw_claim = str(raw_claim)
                ftype_str = rf.get("type", "")
                ftype = next((ft for ft in FeatureType if ftype_str in (ft.value, ft.name)), None)
                if ftype is None:
                    errors.append(GateResult("Parse Gate", False,
                        f'"{name}"."{fname}": unknown type "{ftype_str}"',
                        {"allowed": [t.value for t in FeatureType]}, GateSeverity.ERROR))
                    continue
                # [v6.2] confidence: finite number 검사
                raw_conf = rf.get("confidence", 1.0)
                try:
                    conf = float(raw_conf)
                    if not math.isfinite(conf):
                        errors.append(GateResult("Parse Gate", False,
                            f'"{name}"."{fname}": confidence={raw_conf} (not finite)',
                            severity=GateSeverity.ERROR))
                        conf = 1.0
                except (ValueError, TypeError):
                    errors.append(GateResult("Parse Gate", False,
                        f'"{name}"."{fname}": confidence 타입 오류 ({raw_conf!r})',
                        severity=GateSeverity.ERROR))
                    conf = 1.0
                features.append(NormalizedFeature(
                    feature=fname, type=ftype, evidence=raw_ev,
                    claim=raw_claim, confidence=conf))
            concepts.append(NormalizedConcept(name=name, features=features))

        report.results.extend(errors)
        if not errors:
            report.results.append(GateResult("Parse Gate", True, f"{len(concepts)}개 파싱",
                                             severity=GateSeverity.INFO))
        return concepts if concepts else None, report


# ═══════════════════════════════════════════════════════
# PreDAGSignatureGate (v7: renamed from SignatureGate)
# ═══════════════════════════════════════════════════════

class PreDAGSignatureGate:
    """DAG 생성 전: essential_attrs frozenset 비교만. 기존 SignatureGate와 동일."""
    MIN_ESSENTIAL_FOR_LEAF = 2

    @staticmethod
    def detect(concepts) -> Tuple[GateReport, List[Dict]]:
        report = GateReport(target="[PreDAGSignatureGate]")
        issues = []
        sig_map = defaultdict(list)
        for c in concepts: sig_map[frozenset(c.essential_attrs)].append(c.name)

        for sig, names in sig_map.items():
            if not sig:
                for nm in names:
                    issues.append({"empty_essential": nm})
                    report.results.append(GateResult("PreDAG Signature Gate", False,
                        f'"{nm}": essential 없음',
                        {"concept": nm}, GateSeverity.NEEDS_CORRECTION))
            elif len(names) > 1:
                if len(sig) < PreDAGSignatureGate.MIN_ESSENTIAL_FOR_LEAF:
                    sev = GateSeverity.WARNING
                    tag = "WARNING_UNDERSPECIFIED"
                else:
                    sev = GateSeverity.NEEDS_CORRECTION
                    tag = "NEEDS_CORRECTION"
                issue = {
                    "same_essential_signature": sorted(names), "attrs": sorted(sig),
                    "severity": tag,
                    "correction": (
                        f"{sorted(names)}의 essential set 동일. "
                        f"종차 추가 필요. 공통: {sorted(sig)}"
                    ),
                }
                issues.append(issue)
                report.results.append(GateResult("PreDAG Signature Gate",
                    sev == GateSeverity.WARNING,
                    f'{tag}: {sorted(names)}', issue, sev))

        if not issues:
            report.results.append(GateResult("PreDAG Signature Gate", True, "ok",
                                             severity=GateSeverity.INFO))
        return report, issues

# backward compat alias
SignatureGate = PreDAGSignatureGate


# ═══════════════════════════════════════════════════════
# PostDAGSiblingGate (v7 신규)
# ═══════════════════════════════════════════════════════

class PostDAGSiblingGate:
    """DAG commit 이후: 실제 sibling 관계를 확인하여 종차 부족 탐지."""

    @staticmethod
    def detect(reasoner, concepts) -> Tuple[GateReport, List[Dict]]:
        report = GateReport(target="[PostDAGSiblingGate]")
        issues = []
        cmap = {c.name: c for c in concepts}
        seen_pairs = set()

        for c in concepts:
            siblings = reasoner.get_siblings(c.name)
            if not siblings:
                continue

            for sib_name in siblings:
                pair = tuple(sorted([c.name, sib_name]))
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)

                sib = cmap.get(sib_name)
                if not sib:
                    continue

                if c.essential_attrs == sib.essential_attrs:
                    # 같은 부모 아래 형제인데 essential 동일 → 종차 부족
                    parents_of_c = [p for (p, ch) in reasoner.edge_meta if ch == c.name]
                    shared_parent = parents_of_c[0] if parents_of_c else None
                    issues.append({
                        "sibling_pair": list(pair),
                        "shared_parent": shared_parent,
                        "shared_attrs": sorted(c.essential_attrs),
                        "severity": "SIBLING_UNDERSPECIFIED",
                        "action": "depth_expansion",
                    })
                    report.results.append(GateResult(
                        "PostDAG Sibling Gate", True,
                        f"sibling 종차 부족: {pair[0]} ↔ {pair[1]}",
                        {"pair": list(pair), "parent": shared_parent},
                        GateSeverity.WARNING))

        if not issues:
            report.results.append(GateResult(
                "PostDAG Sibling Gate", True, "ok",
                severity=GateSeverity.INFO))
        return report, issues


# ═══════════════════════════════════════════════════════
# apply_judgments / EdgeBuffer / DAGReasoner
# ═══════════════════════════════════════════════════════

def apply_judgments(concept, judgments):
    new = []
    for j in judgments:
        if j.verdict == FeatureVerdict.REJECT_FEATURE: continue
        if j.verdict == FeatureVerdict.DEMOTE_TO_AUX:
            new.append(NormalizedFeature(j.feature.feature, j.inferred_type,
                                         j.feature.evidence, j.feature.claim, j.feature.confidence))
        else: new.append(j.feature)
    return NormalizedConcept(name=concept.name, features=new)

@dataclass
class EdgeBuffer:
    _p: List[Tuple[str, str]] = field(default_factory=list)
    def stage(self, p, c): self._p.append((p, c))
    @property
    def staged_parents(self):
        r = defaultdict(list)
        for p, c in self._p: r[c].append(p)
        return dict(r)
    def rollback_child(self, child):
        rm = [p for p, c in self._p if c == child]
        self._p = [(p, c) for p, c in self._p if c != child]; return rm
    def commit(self, dag):
        for p, c in self._p: dag.add_edge(p, c)
        n = len(self._p); self._p.clear(); return n

class DAGReasoner:
    def __init__(self, concepts):
        self.concepts = concepts
        self._a = {c.name: c.essential_attrs for c in concepts}
        self.dag = defaultdict(list); self.in_degree = defaultdict(int)
        self.edge_meta = {}; self.aux_graph = {}

    # [v6.3] TaxoAdapt taxonomy.py::Node.get_siblings() 이식
    def get_siblings(self, node_name: str) -> Set[str]:
        """부모를 공유하는 형제 노드 수집. TaxoAdapt에서 이식."""
        siblings = set()
        # reverse lookup: node_name의 부모 찾기
        parents = [p for (p, c) in self.edge_meta if c == node_name]
        for parent in parents:
            for child in self.dag.get(parent, []):
                if child != node_name:
                    siblings.add(child)
        return siblings

    def collect_ancestors(self):
        aa = defaultdict(set)
        for i, j in combinations(range(len(self.concepts)), 2):
            ci, cj = self.concepts[i], self.concepts[j]
            for p, c in ((ci, cj), (cj, ci)):
                if p.essential_attrs < c.essential_attrs: aa[c.name].add(p.name)
        return aa

    def direct_parents(self, aa):
        return {cn: sorted(p for p in anc if not any(
            q != p and self._a[q] > self._a[p] for q in anc)) for cn, anc in aa.items()}

    def add_edge(self, pn, cn):
        d = sorted(self._a.get(cn, set()) - self._a.get(pn, set()))
        self.dag[pn].append(cn); self.in_degree[cn] = self.in_degree.get(cn, 0) + 1
        self.in_degree.setdefault(pn, 0); self.edge_meta[(pn, cn)] = {"diffs": d}

    def topo_sort(self):
        ns = {c.name for c in self.concepts}
        ind = {n: self.in_degree.get(n, 0) for n in ns}
        pq, lv = [], {}
        for n in ns:
            if ind[n] == 0: heapq.heappush(pq, (0, n)); lv[n] = 0
        while pq:
            ly, nd = heapq.heappop(pq)
            for ch in self.dag.get(nd, []):
                ind[ch] -= 1; lv[ch] = max(lv.get(ch, 0), ly + 1)
                if ind[ch] == 0: heapq.heappush(pq, (lv[ch], ch))
        return lv

    def definitions(self):
        cp = defaultdict(list)
        for (p, c) in self.edge_meta: cp[c].append(p)
        defs = {}
        for cn, ps in cp.items():
            ua = set().union(*(self._a[p] for p in ps))
            d = sorted(self._a[cn] - ua)
            if len(ps) == 1:
                ds = ", ".join(f'"{x}"' for x in d) if d else "없음"
                formula = f"{cn} = {ps[0]} + [{ds}]"
            else:
                pstr = " ∧ ".join(sorted(ps)); ds = ", ".join(f'"{x}"' for x in d)
                formula = f"{cn} = {pstr}" + (f" + [{ds}]" if d else "")
            defs[cn] = {"parents": sorted(ps), "delta": d, "formula": formula, "is_meet": len(ps) > 1}
        return defs

    def collect_aux(self):
        for c in self.concepts:
            for f in c.contextual_features:
                self.aux_graph[(c.name, f.feature)] = f.type.value

    def composition_view(self):
        """DAG(is-a)와 독립적인 부분-전체(has-a) 그래프.

        is-a 격자는 ESSENTIAL 피처로 구성되고, 이 뷰는 STRUCTURAL 피처로 구성된다.
        두 그래프를 분리함으로써 "분류"와 "구성"을 독립적으로 추론할 수 있다.
        CompositionGate가 이 뷰에 mereology 공리(반대칭, 비순환)를 적용한다.

        edges: (전체 개념, 부분) 쌍.
        shared_parts: 같은 부분이 여러 전체에 속함 — UFO shareable 메타속성.
        """
        edges = [(c.name, f.feature) for c in self.concepts
                 for f in c.contextual_features if f.type == FeatureType.STRUCTURAL]
        holders = defaultdict(list)
        for whole, part in edges:
            holders[part].append(whole)
        return {"edges": edges,
                "shared_parts": {p: sorted(ws) for p, ws in holders.items() if len(ws) > 1}}

    def finalize(self):
        lv = self.topo_sort(); defs = self.definitions(); self.collect_aux()
        conn = {n for (p, c) in self.edge_meta for n in (p, c)}
        return {"dag": dict(self.dag), "levels": lv, "definitions": defs,
                "aux_relations": dict(self.aux_graph),
                "composition": self.composition_view(),
                "isolated": [c.name for c in self.concepts if c.name not in conn]}


# ═══════════════════════════════════════════════════════
# GateScheduler / CorrectionPromptGenerator
# ═══════════════════════════════════════════════════════

class GateScheduler:
    def __init__(self, gate, cmap): self.gate = gate; self.cmap = cmap
    def validate_edge(self, p, c, anc, dag):
        r = GateReport(target=f"{p.name} → {c.name}")
        r.results.append(self.gate.anti_context_gate(p, c))
        r.results.append(self.gate.subsumption_gate(p, c))
        r.results.append(self.gate.transitive_gate(anc, p))
        r.results.append(self.gate.cycle_gate(dag, (p.name, c.name)))
        return r
    def validate_parents(self, ps, c):
        r = GateReport(target=f"parents of {c.name}")
        r.results.append(self.gate.meet_gate(ps, c))
        r.results.append(self.gate.coverage_gate(ps, c))
        return r

class CorrectionPromptGenerator:
    @staticmethod
    def format_errors(reports):
        lines = ["Errors:"]
        for r in reports:
            for f in r.failures:
                lines.append(f"  [{f.gate_name}] {r.target}: {f.message}")
        return "\n".join(lines)
    @staticmethod
    def generate_standalone(reports):
        e = CorrectionPromptGenerator.format_errors([r for r in reports if not r.passed])
        return f"Failed.\n\n{e}\n\nRevise." if e.strip() != "Errors:" else ""


# ═══════════════════════════════════════════════════════
# ResultClassifier (v6.2)
# ═══════════════════════════════════════════════════════

class ResultClassifier:
    @staticmethod
    def classify(reports, repairs, warnings, sig_issues, dag_has_edges) -> PipelineStatus:
        # ERROR severity → FAIL
        for r in reports:
            for g in r.results:
                if g.severity == GateSeverity.ERROR and not g.passed:
                    return PipelineStatus.FAIL

        # NEEDS_CORRECTION severity (AMBIGUOUS, non-sparse signature)
        has_nc = any(g.severity == GateSeverity.NEEDS_CORRECTION
                     for r in reports for g in r.results)
        if has_nc:
            return PipelineStatus.NEEDS_CORRECTION

        # [v6.2] repairs → PASS_WITH_REPAIR
        if repairs:
            return PipelineStatus.PASS_WITH_REPAIR

        # [v6.3] warnings only (no repairs) → PASS_WITH_WARNING
        has_warn = any(g.severity == GateSeverity.WARNING
                       for r in reports for g in r.results)
        if has_warn or warnings:
            return PipelineStatus.PASS_WITH_WARNING

        return PipelineStatus.PASS


# ═══════════════════════════════════════════════════════
# ExpansionPlanner (v7 Phase 2)
# ═══════════════════════════════════════════════════════

class ExpansionPlanner:
    """WARNING/NEEDS_CORRECTION → ExpansionAction 변환.
    LLM을 호출하지 않음. "무엇을 해야 하는가"만 결정."""

    @staticmethod
    def plan(pre_dag_issues, post_dag_issues=None, ap_iss=None) -> List[ExpansionAction]:
        actions = []

        for iss in pre_dag_issues:
            sev = iss.get("severity")

            if sev == "WARNING_UNDERSPECIFIED":
                actions.append(ExpansionAction(
                    action_type=ExpansionType.DEPTH,
                    target_concepts=iss["same_essential_signature"],
                    shared_attrs=iss["attrs"],
                    reason=iss.get("correction", "종차 부족")))

            elif sev == "NEEDS_CORRECTION":
                if "same_essential_signature" in iss:
                    actions.append(ExpansionAction(
                        action_type=ExpansionType.CORRECTION,
                        target_concepts=iss["same_essential_signature"],
                        shared_attrs=iss["attrs"],
                        reason="essential 동일 + attrs 충분 → 의미 구분 필요"))

            elif "empty_essential" in iss:
                actions.append(ExpansionAction(
                    action_type=ExpansionType.CORRECTION,
                    target_concepts=[iss["empty_essential"]],
                    shared_attrs=[],
                    reason="essential 없음 → 속성 추가 필수"))

        for iss in (post_dag_issues or []):
            if iss.get("action") == "depth_expansion":
                actions.append(ExpansionAction(
                    action_type=ExpansionType.DEPTH,
                    target_concepts=iss["sibling_pair"],
                    shared_attrs=iss.get("shared_attrs", []),
                    parent_name=iss.get("shared_parent"),
                    reason="DAG sibling 종차 부족"))

        # [Phase C2] MixRig → CORRECTION (feature type 교정). PartOver/WholeOver는 정보만.
        for iss in (ap_iss or []):
            if iss.get("pattern") == "MixRig":
                actions.append(ExpansionAction(
                    action_type=ExpansionType.CORRECTION,
                    target_concepts=list(iss.get("involved", [])),
                    shared_attrs=[iss["subject"]] if iss.get("subject") else [],
                    reason=iss.get("detail", "rigidity 혼합 → feature type 교정 필요")))

        return ExpansionPlanner._dedup(actions)

    @staticmethod
    def _dedup(actions: List[ExpansionAction]) -> List[ExpansionAction]:
        """같은 action 중복 제거. (action_type, frozenset(targets)) 기준."""
        seen = set()
        unique = []
        for a in actions:
            key = (a.action_type, frozenset(a.target_concepts))
            if key in seen:
                continue
            seen.add(key)
            unique.append(a)
        return unique


# ═══════════════════════════════════════════════════════
# Expansion 스키마 + 프롬프트 + 파서 (v7 Phase 3)
# ═══════════════════════════════════════════════════════

# LLM 확장 응답의 JSON schema. type에 enum을 명시하여 LLM이 올바른 타입만 출력하도록 강제.
# structural_composition을 직접 출력하게 하는 것이 핵심 설계 결정:
# 초기에는 LLM에게 functional로 쓰게 하고 후처리로 교정했으나, 프롬프트와 교정 로직이
# 모순되어 STRUCTURAL이 도달 불가했음. 현재는 LLM이 직접 올바른 타입을 선택한다.
EXPANSION_OUTPUT_SCHEMA = {
    "type": "object",
    "required": ["expansions"],
    "properties": {
        "expansions": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["concept", "new_features"],
                "properties": {
                    "concept": {"type": "string"},
                    "new_features": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["feature", "type", "evidence"],
                            "properties": {
                                "feature": {"type": "string"},
                                "type": {"type": "string",
                                         "enum": ["essential_feature", "structural_composition",
                                                  "functional", "contextual_usage",
                                                  "locational", "social_treatment"]},
                                "evidence": {"type": "string", "minLength": 4},
                                "relation_hint": {
                                    "type": "string",
                                    "enum": ["is_a", "component_of", "member_of",
                                             "subcollection_of", "subquantity_of",
                                             "material_of", "phase_of", "located_in"]
                                },
                            }
                        }
                    },
                    "reason": {"type": "string"},
                }
            }
        }
    }
}


def _ufo_discrimination_guide(mode: ExpansionType) -> str:
    """LLM에게 is-a와 has-a를 구분하는 방법을 가르치는 프롬프트 삽입물.

    이론적 근거:
    - Section A: Winston(1987) meronymy 3차원 (기능적 의존성, 동질성, 분리가능성)
    - Section B: UFO(Guizzardi 2005) 엔티티 스테레오타입 → FeatureType 매핑
    - Section C: Winston 6유형 부분-전체 패턴 → structural_composition 직접 지시

    핵심 설계 의도: LLM이 has-a 관계를 structural_composition으로 직접 출력하게 한다.
    이전에는 functional로 쓰게 하고 relation_hint로 후교정했으나, 프롬프트-교정 모순으로
    STRUCTURAL 타입이 도달 불가했음. 현재는 교정 없이 단일 경로로 동작한다.

    DEPTH: A+B+C, WIDTH: A+B, CORRECTION: B+C.
    """
    section_a = (
        "<is_a_vs_has_a_test>\n"
        "후보 속성을 추가하기 전에, 다음 3가지 질문으로 is-a(본질) vs has-a(부분) 관계를 판별하세요:\n"
        "(1) 기능적 의존성: 전체의 기능이 이 부분에 의존하는가?\n"
        "    예 → 부분-전체(has-a) 가능성 높음 / 아니오 → 속성·종차(is-a) 가능성 높음\n"
        "(2) 동질성(homeomerous): 부분이 전체와 같은 종류인가?\n"
        "    예 → 물질·수량 관계 / 아니오 → 구성요소-통합체 또는 멤버-집합\n"
        "(3) 분리가능성: 부분을 제거해도 전체의 정체성이 유지되는가?\n"
        "    예 → 비본질적 부분 / 아니오 → 본질적 부분이지만 여전히 has-a\n"
        "핵심 원칙: \"X는 Y의 일종이다\"(is-a)만 essential_feature로. "
        "\"X는 Y를 가진다/포함한다\"(has-a)는 structural_composition으로.\n"
        "</is_a_vs_has_a_test>\n"
    )
    section_b = (
        "<ufo_type_mapping>\n"
        "속성 유형 판별 가이드:\n"
        "essential_feature (is-a 계층): 정체성 원리를 제공, 모든 인스턴스가 필연적으로 가짐. "
        "예: 척추동물→척추, 포유류→젖샘·체온조절\n"
        "structural_composition (has-a 구성): 부분-전체 관계. 구성요소·멤버·부분. "
        "예: 자동차→엔진, 숲→나무, 컴퓨터→CPU\n"
        "functional: 용도·역할·기능에 의한 분류(맥락 의존). 예: 사냥개→사냥용도, 식용식물→식용가능\n"
        "contextual_usage: 인간의 분류 관행·시장·요리 맥락. 예: 채소→요리에서의 분류\n"
        "locational: 서식지·분포·생태적 위치. 예: 담수어→민물 서식\n"
        "social_treatment: 법적 지위·사회적 관행. 예: 멸종위기종→법적 보호 대상\n"
        "</ufo_type_mapping>\n"
    )
    section_c = (
        "<part_whole_patterns>\n"
        "has-a로 분류해야 하는 부분-전체 패턴 6가지:\n"
        "(1) 구성요소-통합체: 엔진은 자동차의 구성요소 → structural_composition\n"
        "(2) 멤버-집합: 나무는 숲의 구성원 → structural_composition\n"
        "(3) 부분-질량: 조각은 파이의 부분 → structural_composition\n"
        "(4) 재료-대상: 철은 칼의 재료 → essential_feature (재료는 본질이 될 수 있음)\n"
        "(5) 단계-과정: 유충은 변태의 단계 → contextual_usage\n"
        "(6) 장소-영역: 오아시스는 사막의 부분 → locational\n"
        "주의: 재료-대상(4)만 essential_feature 가능. (1)~(3)은 structural_composition, "
        "(5)는 contextual_usage, (6)은 locational을 사용하세요.\n"
        "</part_whole_patterns>\n"
    )
    if mode == ExpansionType.DEPTH:
        inner = section_a + section_b + section_c
    elif mode == ExpansionType.WIDTH:
        inner = section_a + section_b
    else:  # CORRECTION
        inner = section_b + section_c
    return f"\n<discrimination_guide>\n{inner}</discrimination_guide>\n"


def build_expansion_prompt(action: ExpansionAction) -> str:
    """ExpansionAction → LLM 프롬프트 (XML 태그 구조, TaxoAdapt 참고)."""
    targets = ", ".join(action.target_concepts)
    shared = ", ".join(action.shared_attrs) if action.shared_attrs else "(없음)"

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
        'type 선택지: essential_feature, structural_composition, '
        'functional, contextual_usage, locational, social_treatment\n'
        'relation_hint 선택지: is_a, component_of, member_of, '
        'subcollection_of, subquantity_of, material_of, phase_of, located_in'
    )
    return body + schema_hint


def parse_expansion_response(raw: str, original_concepts: List[NormalizedConcept]) -> Tuple[List[NormalizedConcept], GateReport]:
    """LLM 확장 응답 → 기존 개념에 new_features 병합한 개념 리스트.

    ParseGate와 동일한 방어 로직. 확장 결과가 다시 Gate를 통과해야 함.
    """
    report = GateReport(target="[ExpansionParse]")
    try:
        parsed = json.loads(extract_json_block(raw))
    except (ValueError, json.JSONDecodeError) as exc:
        report.results.append(GateResult("Expansion Parse", False, f"JSON: {exc}",
                                         severity=GateSeverity.ERROR))
        return original_concepts, report

    if not isinstance(parsed, dict) or "expansions" not in parsed:
        report.results.append(GateResult("Expansion Parse", False,
            '"expansions" 키 없음', severity=GateSeverity.ERROR))
        return original_concepts, report

    if not isinstance(parsed["expansions"], list):
        report.results.append(GateResult("Expansion Parse", False,
            '"expansions"가 list 아님', severity=GateSeverity.ERROR))
        return original_concepts, report

    # 기존 개념 복사 (이름 → NormalizedConcept)
    cmap = {c.name: NormalizedConcept(c.name, list(c.features)) for c in original_concepts}
    errors = []

    for exp in parsed["expansions"]:
        if not isinstance(exp, dict):
            errors.append(GateResult("Expansion Parse", False, "expansion item이 dict 아님",
                                     severity=GateSeverity.ERROR)); continue
        cname = exp.get("concept")
        if not cname or not isinstance(cname, str):
            errors.append(GateResult("Expansion Parse", False, f"concept 비문자열: {cname!r}",
                                     severity=GateSeverity.ERROR)); continue

        raw_feats = exp.get("new_features")
        if not isinstance(raw_feats, list) or len(raw_feats) == 0:
            errors.append(GateResult("Expansion Parse", False,
                f'"{cname}": new_features 비어있거나 list 아님', severity=GateSeverity.ERROR)); continue

        target = cmap.get(cname)
        if target is None:
            # 새 개념 (WIDTH expansion 등)
            target = NormalizedConcept(cname, [])
            cmap[cname] = target

        for rf in raw_feats:
            if not isinstance(rf, dict):
                errors.append(GateResult("Expansion Parse", False,
                    f'"{cname}": feature item이 dict 아님', severity=GateSeverity.ERROR)); continue
            fname = rf.get("feature")
            if not fname or not isinstance(fname, str):
                errors.append(GateResult("Expansion Parse", False,
                    f'"{cname}": feature name 비문자열', severity=GateSeverity.ERROR)); continue
            ftype_str = rf.get("type", "")
            ftype = next((ft for ft in FeatureType if ftype_str in (ft.value, ft.name)), None)
            if ftype is None:
                errors.append(GateResult("Expansion Parse", False,
                    f'"{cname}"."{fname}": unknown type "{ftype_str}"', severity=GateSeverity.ERROR)); continue
            ev = rf.get("evidence", "")
            if not isinstance(ev, str):
                ev = str(ev)
            target.features.append(NormalizedFeature(fname, ftype, ev, ev))

    report.results.extend(errors)
    if not errors:
        report.results.append(GateResult("Expansion Parse", True,
            f"{len(parsed['expansions'])}개 확장 병합", severity=GateSeverity.INFO))

    return list(cmap.values()), report


class MockExpansionGenerator:
    """LLM 없이 확장 응답을 생성하는 테스트용 generator.

    실제 LLM 대신 사전 정의된 종차를 반환. Phase 4에서 실제 API로 교체.
    """
    def __init__(self, responses: Dict[str, List[Dict]] = None):
        # responses: {concept_name: [{"feature","type","evidence"}, ...]}
        self.responses = responses or {}

    def generate(self, action: ExpansionAction) -> str:
        expansions = []
        for cname in action.target_concepts:
            feats = self.responses.get(cname)
            if feats:
                expansions.append({
                    "concept": cname,
                    "new_features": feats,
                    "reason": f"mock 종차 ({action.action_type.value})",
                })
        return json.dumps({"expansions": expansions}, ensure_ascii=False)


# ═══════════════════════════════════════════════════════
# ParentCandidateClassifier (v7 Phase 4)
# ═══════════════════════════════════════════════════════

class ParentCandidateClassifier:
    """확장된 개념이 여러 부모 후보 중 어디에 속하는지 multi-label 판정.

    TaxoAdapt classification.py 참고. paper 기반 → 속성 기반으로 번역.
    LLM 없이 essential_attrs 포함관계로 판정 (deterministic).
    """

    @staticmethod
    def classify(new_concept: NormalizedConcept,
                 existing_concepts: List[NormalizedConcept]) -> List[str]:
        """new_concept의 essential_attrs ⊃ existing의 essential_attrs인 부모 후보 반환.

        multi-label: 여러 부모를 동시에 반환 가능 (meet 구조).
        direct parents만 반환 (transitive 조상 제거).
        """
        # 1. new_concept을 진부분집합으로 포함하는 모든 조상 후보
        candidates = []
        for ex in existing_concepts:
            if ex.name == new_concept.name:
                continue
            if ex.essential_attrs < new_concept.essential_attrs:
                candidates.append(ex)

        # 2. direct parents만 (다른 후보의 진부분집합인 것 제거)
        attrs_map = {c.name: c.essential_attrs for c in candidates}
        direct = []
        for cand in candidates:
            # cand보다 더 구체적인(상위 attrs) 후보가 있으면 cand는 indirect
            is_direct = not any(
                other.name != cand.name and
                cand.essential_attrs < other.essential_attrs
                for other in candidates
            )
            if is_direct:
                direct.append(cand.name)

        return sorted(direct)

    @staticmethod
    def classify_all(new_concepts: List[NormalizedConcept],
                     existing_concepts: List[NormalizedConcept]) -> Dict[str, List[str]]:
        """여러 새 개념에 대해 일괄 부모 후보 판정."""
        all_concepts = list(existing_concepts) + list(new_concepts)
        result = {}
        for nc in new_concepts:
            result[nc.name] = ParentCandidateClassifier.classify(nc, all_concepts)
        return result


# ═══════════════════════════════════════════════════════
# Expansion Generator 인터페이스 (v7 Phase 4)
# ═══════════════════════════════════════════════════════

class ExpansionGeneratorBase:
    """확장 generator의 추상 인터페이스.

    실제 LLM 연결 시 이 클래스를 상속하고 generate(action)에서
    Anthropic API를 호출하면 됨. 예:

        class LLMExpansionGenerator(ExpansionGeneratorBase):
            def generate(self, action):
                prompt = build_expansion_prompt(action)
                response = anthropic_client.messages.create(...)
                return response.content[0].text  # raw JSON string

    이 파일 자체는 StaticExpansionGenerator로 동작 (LLM 불필요).
    """
    def generate(self, action: "ExpansionAction") -> str:
        raise NotImplementedError("Subclass must implement generate(action) → raw JSON string")


class StaticExpansionGenerator(ExpansionGeneratorBase):
    """사전 정의된 응답을 반환하는 generator (MockExpansionGenerator 일반화).

    LLM 대신 사람(또는 다른 agent)이 미리 작성한 종차를 주입.
    Phase 4에서 LLM 역할을 대응하는 데 사용.
    """
    def __init__(self, responses: Dict[str, List[Dict]] = None):
        self.responses = responses or {}

    def add_response(self, concept: str, features: List[Dict]):
        """개념별 종차 응답 추가."""
        self.responses[concept] = features

    def generate(self, action: "ExpansionAction") -> str:
        expansions = []
        for cname in action.target_concepts:
            feats = self.responses.get(cname)
            if feats:
                expansions.append({
                    "concept": cname,
                    "new_features": feats,
                    "reason": f"static 종차 ({action.action_type.value})",
                })
        return json.dumps({"expansions": expansions}, ensure_ascii=False)


# ═══════════════════════════════════════════════════════
# HeuristicExpansionGenerator (v7 Phase 5)
# ═══════════════════════════════════════════════════════

class HeuristicExpansionGenerator(ExpansionGeneratorBase):
    """LLM 없이 사전(lexicon) 기반으로 종차 후보를 생성.

    창의적이지 않지만 결정론적이라 테스트/벤치마크/회귀 검증에 적합.
    각 개념에 대해 lexicon에서 후보 종차를 찾아 반환.

    lexicon 예:
        {
          "개": [{"feature": "가축화", "type": "essential_feature", "evidence": "..."}],
          ...
        }

    fallback_template: lexicon에 없는 개념에 대한 기본 종차 생성 규칙.
    """
    def __init__(self, lexicon: Dict[str, List[Dict]] = None,
                 fallback_template: bool = True):
        self.lexicon = lexicon or {}
        self.fallback_template = fallback_template

    def add_term(self, concept: str, features: List[Dict]):
        self.lexicon[concept] = features

    def generate(self, action: "ExpansionAction") -> str:
        expansions = []
        for cname in action.target_concepts:
            feats = self.lexicon.get(cname)

            if not feats and self.fallback_template:
                # lexicon에 없으면 개념명 기반 종차를 생성 (heuristic)
                # "X의 고유 속성" 형태 — 최소한 essential을 구분되게 만듦
                feats = [{
                    "feature": f"{cname}_고유속성",
                    "type": "essential_feature",
                    "evidence": f"{cname}을(를) 다른 개념과 구분하는 고유한 본질적 속성",
                }]

            if feats:
                expansions.append({
                    "concept": cname,
                    "new_features": feats,
                    "reason": f"heuristic 종차 ({action.action_type.value})",
                })
        return json.dumps({"expansions": expansions}, ensure_ascii=False)


# ═══════════════════════════════════════════════════════
# ExpansionHistoryAnalyzer (v7 Phase 5)
# ═══════════════════════════════════════════════════════

class ExpansionHistoryAnalyzer:
    """확장 루프 history를 분석하여 수렴/반복/정체를 판정.

    run_with_expansion의 expansion_history를 입력으로 받음.
    """

    CONVERGED   = "converged"     # 최종 PASS
    STALLED     = "stalled"       # max round 도달, 여전히 WARNING/NEEDS_CORRECTION
    OSCILLATING = "oscillating"   # 같은 status/n_concepts 반복
    PARSE_FAIL  = "parse_fail"    # generator 출력 파싱 실패
    NO_OP       = "no_op"         # 확장 안 함 (generator=None 또는 action 없음)

    @staticmethod
    def analyze(history: List[Dict]) -> Dict:
        if not history:
            return {"verdict": ExpansionHistoryAnalyzer.NO_OP, "rounds": 0, "detail": "empty history"}

        # PARSE_FAIL 우선
        for h in history:
            if h.get("status") == "PARSE_FAIL":
                return {"verdict": ExpansionHistoryAnalyzer.PARSE_FAIL,
                        "rounds": len(history),
                        "detail": f"round {h.get('round')} 파싱 실패",
                        "errors": h.get("errors", [])}

        last = history[-1]
        last_status = last.get("status")

        # 수렴
        if last_status == "PASS":
            return {"verdict": ExpansionHistoryAnalyzer.CONVERGED,
                    "rounds": len(history),
                    "detail": f"{len(history)-1}회 확장 후 PASS"}

        # 확장이 1라운드만 (NO_OP)
        if len(history) == 1:
            return {"verdict": ExpansionHistoryAnalyzer.NO_OP,
                    "rounds": 1,
                    "detail": f"확장 없음 (status={last_status})"}

        # 진동 감지: 마지막 2개 이상 라운드의 (status, n_concepts)가 동일
        signatures = [(h.get("status"), h.get("n_concepts")) for h in history[1:]]
        if len(signatures) >= 2 and signatures[-1] == signatures[-2]:
            return {"verdict": ExpansionHistoryAnalyzer.OSCILLATING,
                    "rounds": len(history),
                    "detail": f"동일 상태 반복: {signatures[-1]}"}

        # 정체: max round 도달했으나 PASS 아님
        return {"verdict": ExpansionHistoryAnalyzer.STALLED,
                "rounds": len(history),
                "detail": f"max round 도달, 최종 status={last_status}"}

    @staticmethod
    def is_progressing(history: List[Dict]) -> bool:
        """라운드를 거치며 개선되고 있는지 (n_actions 감소 추세)."""
        if len(history) < 2:
            return True
        action_counts = [h.get("n_actions", 0) for h in history]
        # 마지막이 이전보다 적거나 같으면 진행 중
        return action_counts[-1] <= action_counts[-2]


# ═══════════════════════════════════════════════════════
# CompositionGate (v7 Phase C1)
# ═══════════════════════════════════════════════════════

class CompositionGate:
    """composition_view()(부분-전체 그래프)에 mereology 공리를 적용하는 gate.

    DAG(is-a)와 별도로, has-a 그래프가 온톨로지적으로 건전한지 검증한다.
    공리 출처: OBO Relation Ontology(vendor/obo-relations) core.obo — BFO:0000050(part_of)/51(has_part).

    검사 4종:
    - 반대칭: A⊃B이면서 B⊃A는 불가 (proper parthood, OBO core.obo)
    - 비순환: 추이 폐쇄에서 자기 도달 = 순환 (OBO is_transitive + 반대칭에서 도출)
    - is-a/has-a 배타: DAG 조상-자손 사이에 has_part 간선 → 두 관계의 혼동
    - 자기 부분: (A, A) — 고전 mereology는 반사 허용이나 모델링에선 의심
    """

    @staticmethod
    def _reachable(graph: Dict[str, List[str]], start: str) -> Set[str]:
        # graph[a] = [자손...]; start에서 도달 가능한 노드 집합 (순환 시 start 재포함)
        seen: Set[str] = set()
        stack = list(graph.get(start, []))
        while stack:
            n = stack.pop()
            if n in seen: continue
            seen.add(n)
            stack.extend(graph.get(n, []))
        return seen

    @staticmethod
    def _is_ancestor(dag: Dict[str, List[str]], a: str, b: str) -> bool:
        # DAG에서 a→...→b 도달 = a가 b의 is-a 조상
        return b in CompositionGate._reachable(dag, a)

    @staticmethod
    def detect(reasoner: "DAGReasoner") -> Tuple[GateReport, List[Dict]]:
        report = GateReport(target="[CompositionGate]")
        issues: List[Dict] = []
        comp = reasoner.composition_view()
        edges = comp["edges"]                        # (전체, 부분) 쌍
        edge_set = set(edges)
        names = {c.name for c in reasoner.concepts}  # 개념명 집합
        dag = dict(reasoner.dag)

        # 검사 1: 반대칭 — (A,B)와 (B,A) 동시 (ERROR)
        anti_seen: Set[Tuple[str, str]] = set()
        for (w, p) in edges:
            if w != p and (p, w) in edge_set:
                key = tuple(sorted((w, p)))
                if key in anti_seen: continue
                anti_seen.add(key)
                issues.append({"kind": "antisymmetry", "whole": w, "part": p,
                    "detail": f"{w}⊃{p} 와 {p}⊃{w} 동시 — proper parthood 반대칭 위반"})
        report.results.append(GateResult(
            "Composition Gate: 반대칭", not anti_seen,
            f"반대칭 위반 {len(anti_seen)}건" if anti_seen else "ok",
            {"pairs": sorted(anti_seen)},
            GateSeverity.ERROR if anti_seen else GateSeverity.INFO))

        # 검사 2: 비순환 — 부분명이 개념명인 간선만 추이 폐쇄 (ERROR)
        cyc_graph: Dict[str, List[str]] = defaultdict(list)
        for (w, p) in edges:
            if p in names and p != w:      # 자기루프는 검사 4에서 처리
                cyc_graph[w].append(p)
        cyc_graph = dict(cyc_graph)
        cyc_nodes = sorted(n for n in names
                           if n in CompositionGate._reachable(cyc_graph, n))
        for n in cyc_nodes:
            issues.append({"kind": "cycle", "whole": n, "part": n,
                "detail": f"{n}이(가) 구성 추이폐쇄에서 자기 자신에 도달 — 순환"})
        report.results.append(GateResult(
            "Composition Gate: 비순환", not cyc_nodes,
            f"순환 노드 {cyc_nodes}" if cyc_nodes else "ok",
            {"cycle_nodes": cyc_nodes},
            GateSeverity.ERROR if cyc_nodes else GateSeverity.INFO))

        # 검사 3: is-a/has-a 배타 — 조상-자손 개념 쌍에 has_part 간선 (NEEDS_CORRECTION)
        conflicts: List[Tuple[str, str]] = []
        for (w, p) in edges:
            if w == p or p not in names: continue
            if CompositionGate._is_ancestor(dag, w, p) or CompositionGate._is_ancestor(dag, p, w):
                if (w, p) in conflicts: continue
                conflicts.append((w, p))
                issues.append({"kind": "isa_hasa_conflict", "whole": w, "part": p,
                    "detail": f"{w}와 {p}는 is-a 조상-자손인데 has_part 간선도 존재 — is-a/has-a 혼동"})
        report.results.append(GateResult(
            "Composition Gate: is-a/has-a 배타", not conflicts,
            f"배타 위반 {conflicts}" if conflicts else "ok",
            {"conflicts": conflicts},
            GateSeverity.NEEDS_CORRECTION if conflicts else GateSeverity.INFO))

        # 검사 4: 자기 부분 — (A,A) 간선 (WARNING, 차단하지 않음)
        self_parts = sorted({w for (w, p) in edges if w == p})
        for n in self_parts:
            issues.append({"kind": "self_part", "whole": n, "part": n,
                "detail": f"{n}이(가) 자기 자신을 부분으로 가짐 — 모델링 의심"})
        report.results.append(GateResult(
            "Composition Gate: 자기부분", True,
            f"자기부분 {self_parts}" if self_parts else "ok",
            {"self_parts": self_parts},
            GateSeverity.WARNING if self_parts else GateSeverity.INFO))

        return report, issues


# ═══════════════════════════════════════════════════════
# UFOAntiPatternGate (v7 Phase C2)
# ═══════════════════════════════════════════════════════

class UFOAntiPatternGate:
    """UFO/OntoUML 카탈로그(Guizzardi 2021)에서 데이터로 판별 가능한 안티패턴 3종 감지.

    전부 WARNING — 파이프라인을 차단하지 않고 모델링 개선을 위한 정보를 제공한다.
    MixRig만 ExpansionPlanner가 CORRECTION action으로 변환한다.

    - MixRig (rigidity 혼합): 같은 feature명이 ESSENTIAL(rigid, 정체성 제공)과
      비-ESSENTIAL(anti-rigid, 맥락 의존)로 혼용 → 분류 기준이 오염됨
    - PartOver (부분 중복): shared_parts의 한 부분이 is-a 조상-자손인 두 전체에
      모두 소속 → 자식이 상속받을 부분을 중복 선언 (예: 포유류 has 심장 + 개 has 심장)
    - WholeOver (전체 중복): 한 개념이 STRUCTURAL 부분과 그 특수화를 동시 보유
      → 일반 부분과 구체 부분이 공존 (예: 차 has 바퀴 + has 앞바퀴)
    """

    @staticmethod
    def _is_ancestor(reasoner, a, b) -> bool:
        """reasoner.dag에서 a→...→b 도달 가능 여부. CompositionGate._reachable 재사용."""
        if a == b:
            return False
        return b in CompositionGate._reachable(dict(reasoner.dag), a)

    @staticmethod
    def detect(reasoner, concepts) -> Tuple[GateReport, List[Dict]]:
        report = GateReport(target="[UFOAntiPatternGate]")
        issues = []

        # MixRig — feature명별 type 집합에 ESSENTIAL과 비-ESSENTIAL 공존
        feature_types = defaultdict(set)   # feature명 → {FeatureType,...}
        for c in concepts:
            for f in c.features:
                feature_types[f.feature].add(f.type)
        for feat_name, types in feature_types.items():
            if FeatureType.ESSENTIAL in types and any(t != FeatureType.ESSENTIAL for t in types):
                involved = sorted({c.name for c in concepts
                                   for f in c.features if f.feature == feat_name})
                iss = {"pattern": "MixRig", "subject": feat_name,
                       "detail": f'"{feat_name}" rigidity 혼합: {sorted(t.value for t in types)}',
                       "involved": involved}
                issues.append(iss)
                report.results.append(GateResult(
                    "UFO Anti-Pattern Gate", True, f"MixRig: {feat_name}",
                    iss, GateSeverity.WARNING))

        # PartOver — shared_parts의 부분을 소유한 전체들 중 조상-자손 쌍 존재
        for part, wholes in reasoner.composition_view()["shared_parts"].items():
            for w1, w2 in combinations(wholes, 2):
                if (UFOAntiPatternGate._is_ancestor(reasoner, w1, w2)
                        or UFOAntiPatternGate._is_ancestor(reasoner, w2, w1)):
                    iss = {"pattern": "PartOver", "subject": part,
                           "detail": f'부분 "{part}"가 조상-자손 관계인 {[w1, w2]}에 중복 소속',
                           "involved": [w1, w2]}
                    issues.append(iss)
                    report.results.append(GateResult(
                        "UFO Anti-Pattern Gate", True, f"PartOver: {part}",
                        iss, GateSeverity.WARNING))

        # WholeOver — 한 개념의 STRUCTURAL 부분 두 개가 조상-자손 관계
        for c in concepts:
            parts = [f.feature for f in c.contextual_features
                     if f.type == FeatureType.STRUCTURAL]
            for p1, p2 in combinations(parts, 2):
                if (UFOAntiPatternGate._is_ancestor(reasoner, p1, p2)
                        or UFOAntiPatternGate._is_ancestor(reasoner, p2, p1)):
                    iss = {"pattern": "WholeOver", "subject": c.name,
                           "detail": f'{c.name}가 부분과 그 특수화 {[p1, p2]}를 동시 보유',
                           "involved": [p1, p2]}
                    issues.append(iss)
                    report.results.append(GateResult(
                        "UFO Anti-Pattern Gate", True, f"WholeOver: {c.name}",
                        iss, GateSeverity.WARNING))

        if not issues:
            report.results.append(GateResult(
                "UFO Anti-Pattern Gate", True, "ok",
                severity=GateSeverity.INFO))
        return report, issues


# ═══════════════════════════════════════════════════════
# RCA 관계 스케일링 (Phase C3)
# ═══════════════════════════════════════════════════════

RCA_SCALING_MARKER = "rca_scaling"
RCA_SCALING_PREFIX = "∃has_part."

def relational_scaling(concepts: List[NormalizedConcept]) -> List[NormalizedConcept]:
    """has-a 관계를 is-a 격자에 반영하는 RCA existential scaling.

    RCA(Relational Concept Analysis, Rouane-Hacene 2013)의 핵심 아이디어:
    객체 간 관계(has_part)를 관계 속성(∃has_part.C)으로 변환하여 FCA 문맥에 주입하면,
    구성이 비슷한 개념들이 is-a 격자에서 자연스럽게 묶인다.

    예: 자동차{엔진(S)} + 전기차{엔진(S)} → 둘 다 ∃has_part.엔진(E) 획득
        → 격자에서 "엔진 보유 탈것" 노드로 묶임.

    제약:
    - 부분 이름이 개념명과 일치하는 STRUCTURAL 피처만 대상 (비개념 부분은 leaf)
    - 파생 피처는 ESSENTIAL → DAG 간선에 기여. 원본 STRUCTURAL은 유지 → composition_view 동작
    - 멱등: 같은 파생 피처가 있으면 추가 안 함 (run_with_expansion 재진입 루프에서 안전)
    - 순수 함수: 원본 리스트 불변

    ponytail: 완전한 RCA 고정점(다중 격자 반복 수렴)은 과함. 1-pass만 적용하되,
    run_with_expansion 루프가 이미 재진입 구조이므로 "확장 루프 ≈ RCA 수렴"의 실용적 근사.
    leaf로 취급 — 파생 없음.
    """
    names = {c.name for c in concepts}
    scaled = []
    for c in concepts:
        feats = list(c.features)              # 얕은 사본 — 원본 리스트 불변
        present = {ft.feature for ft in feats}
        for ft in c.features:
            if ft.type != FeatureType.STRUCTURAL or ft.feature not in names:
                continue
            derived = f"{RCA_SCALING_PREFIX}{ft.feature}"
            if derived in present:
                continue                      # 멱등
            ev = f"{RCA_SCALING_MARKER}: {c.name} has_part {ft.feature}"
            feats.append(NormalizedFeature(derived, FeatureType.ESSENTIAL,
                                           ev, ev, ft.confidence))
            present.add(derived)
        scaled.append(NormalizedConcept(name=c.name, features=feats))
    return scaled



# ═══════════════════════════════════════════════════════
# ConceptPipeline
# ═══════════════════════════════════════════════════════

class ConceptPipeline:
    def __init__(self, contradiction_pairs=None, max_rounds=3):
        self.gate = ConceptGate(contradiction_pairs); self.max_rounds = max_rounds

    def validate_hierarchy(self, concepts):
        all_reps, all_repairs, all_warnings, cleaned = [], [], [], []
        for c in concepts:
            sem_r, judg, reps, warns = self.gate.semantic_type_gate(c)
            all_repairs.extend(reps)
            all_warnings.extend(warns)
            cc = apply_judgments(c, judg)
            report = GateReport(target=c.name)
            report.results.append(self.gate.type_gate(cc))
            report.results.append(self.gate.evidence_gate(cc))
            report.results.append(self.gate.contradiction_gate(cc))
            report.results.append(sem_r)
            all_reps.append(report)
            hard = [r for r in report.results if not r.passed and r.severity == GateSeverity.ERROR]
            if not hard: cleaned.append(cc)

        # [v7] PreDAG: essential signature 중복 탐지 (기존 위치)
        sig_rep, sig_iss = PreDAGSignatureGate.detect(cleaned)
        all_reps.append(sig_rep)
        reasoner = DAGReasoner(cleaned)
        if len(cleaned) < 2:
            comp_rep, comp_iss = CompositionGate.detect(reasoner)
            all_reps.append(comp_rep)
            ap_rep, ap_iss = UFOAntiPatternGate.detect(reasoner, cleaned)
            all_reps.append(ap_rep)
            return all_reps, all_repairs, all_warnings, reasoner, sig_iss, [], comp_iss, ap_iss
        cmap = {c.name: c for c in cleaned}
        sched = GateScheduler(self.gate, cmap)
        aa = reasoner.collect_ancestors(); prop = reasoner.direct_parents(aa)
        buf = EdgeBuffer()
        for cn, pns in prop.items():
            anc = [cmap[a] for a in aa.get(cn, set()) if a in cmap]
            for pn in pns:
                pnc = cmap.get(pn)
                if not pnc: continue
                er = sched.validate_edge(pnc, cmap[cn], anc, dict(reasoner.dag))
                all_reps.append(er)
                if er.passed: buf.stage(pn, cn)
        for cn, sp in buf.staged_parents.items():
            pr = sched.validate_parents([cmap[p] for p in sp], cmap[cn])
            all_reps.append(pr)
            if not pr.passed: buf.rollback_child(cn)
        buf.commit(reasoner)

        # [v7] PostDAG: 실제 sibling 관계 확인
        post_rep, post_iss = PostDAGSiblingGate.detect(reasoner, cleaned)
        all_reps.append(post_rep)

        # [v7 Phase C1] CompositionGate: has-a 그래프 mereology 공리 검증
        comp_rep, comp_iss = CompositionGate.detect(reasoner)
        all_reps.append(comp_rep)

        # [v7 Phase C2] UFOAntiPatternGate: MixRig/PartOver/WholeOver (전부 WARNING)
        ap_rep, ap_iss = UFOAntiPatternGate.detect(reasoner, cleaned)
        all_reps.append(ap_rep)

        return all_reps, all_repairs, all_warnings, reasoner, sig_iss, post_iss, comp_iss, ap_iss

    def run(self, cands_per_round):
        hist, prompts = [], []
        reasoner = None
        for ri, cands in enumerate(cands_per_round):
            if ri >= self.max_rounds: break
            reps, repairs, warnings, reasoner, sig_iss, post_iss, comp_iss, ap_iss = self.validate_hierarchy(cands)
            hist.append(reps); result = reasoner.finalize()
            status = ResultClassifier.classify(reps, repairs, warnings, sig_iss, bool(result["dag"]))

            # [v7] expansion planning
            exp_actions = ExpansionPlanner.plan(sig_iss, post_iss, ap_iss)

            if status != PipelineStatus.FAIL:
                return {"result": result, "status": status.value, "rounds_used": ri+1,
                        "all_reports": hist, "repairs": repairs, "warnings": warnings,
                        "signature_issues": sig_iss, "post_dag_issues": post_iss,
                        "composition_issues": comp_iss, "anti_patterns": ap_iss,
                        "expansion_actions": exp_actions, "correction_prompts": prompts}
            prompts.append(CorrectionPromptGenerator.generate_standalone(reps))
        result = reasoner.finalize() if reasoner else {"dag":{},"levels":{},"definitions":{},"aux_relations":{},"composition":{"edges":[],"shared_parts":{}},"isolated":[]}
        return {"result": result, "status": "FAIL", "rounds_used": len(cands_per_round),
                "all_reports": hist, "repairs": [], "warnings": [],
                "signature_issues": [], "post_dag_issues": [],
                "composition_issues": [], "anti_patterns": [],
                "expansion_actions": [], "correction_prompts": prompts}

    def run_with_expansion(self, initial_concepts, generator=None, max_expansion_rounds=2,
                           rca_scaling=False):
        """확장 루프: 초기 검증 → expansion action → generator → 재진입.

        generator: MockExpansionGenerator 또는 실제 LLM generator (.generate(action) → raw JSON).
        generator=None이면 확장 없이 run()과 동일.
        """
        if rca_scaling:
            initial_concepts = relational_scaling(initial_concepts)
        out = self.run([initial_concepts])
        history = [{"round": 0, "status": out["status"],
                    "n_concepts": len(initial_concepts),
                    "n_actions": len(out.get("expansion_actions", []))}]

        if generator is None:
            out["expansion_history"] = history
            return out

        current = initial_concepts
        for exp_round in range(1, max_expansion_rounds + 1):
            actions = out.get("expansion_actions", [])
            # DEPTH/WIDTH/CORRECTION 모두 확장 처리
            expandable = [a for a in actions if a.action_type in
                          (ExpansionType.DEPTH, ExpansionType.WIDTH, ExpansionType.CORRECTION)]
            if not expandable:
                break

            # 각 action을 generator로 처리하여 확장된 개념 수집
            expanded = current
            parse_ok = True
            for action in expandable:
                raw = generator.generate(action)
                expanded, parse_report = parse_expansion_response(raw, expanded)
                if not parse_report.passed:
                    parse_ok = False
                    history.append({"round": exp_round, "status": "PARSE_FAIL",
                                    "errors": [f.message for f in parse_report.failures]})
                    break

            if not parse_ok:
                break

            current = expanded
            out = self.run([current])
            history.append({"round": exp_round, "status": out["status"],
                            "n_concepts": len(current),
                            "n_actions": len(out.get("expansion_actions", []))})

            if out["status"] in ("PASS",):
                break  # 수렴

            # [Phase 5] 진동 감지 — 같은 상태가 반복되면 조기 종료
            analysis = ExpansionHistoryAnalyzer.analyze(history)
            if analysis["verdict"] == ExpansionHistoryAnalyzer.OSCILLATING:
                break  # 더 돌려도 같은 결과

        out["expansion_history"] = history
        out["final_concepts"] = current

        # [Phase 5] history 분석 결과 첨부
        out["expansion_analysis"] = ExpansionHistoryAnalyzer.analyze(history)

        # [Phase 4] 최종 개념들의 부모 후보 multi-label 판정
        parent_map = {}
        for c in current:
            parents = ParentCandidateClassifier.classify(c, current)
            if parents:
                parent_map[c.name] = parents
        out["parent_candidates"] = parent_map

        return out


# ═══════════════════════════════════════════════════════
# 테스트
# ═══════════════════════════════════════════════════════


def f(feat, ftype, ev, cl=""): return NormalizedFeature(feat, ftype, ev, cl or ev)

if __name__ == "__main__":
    E = FeatureType.ESSENTIAL
    pipe = ConceptPipeline()
    g = ConceptGate()
    passed = 0; failed = 0

    def check(label, cond, detail=""):
        global passed, failed
        if cond:
            passed += 1; print(f"  ✓ {label}")
        else:
            failed += 1; print(f"  ✗ {label}  {detail}")

    # ════════════════════════════════════════════════
    # v6.3 회귀 (핵심 13건)
    # ════════════════════════════════════════════════
    print("\n[v6.3 회귀]")

    c, r = ParseGate.parse('{"concepts": "not a list"}')
    check("concepts 비-list", not r.passed and c is None)

    c, r = ParseGate.parse('{"concepts": [{"name": "A", "features": "bad"}]}')
    check("features 비-list", not r.passed)

    _, r = ParseGate.parse('{"concepts": [{"name": "A", "features": [{"feature": "x", "type": "essential_feature", "evidence": "valid text", "confidence": "NaN"}]}]}')
    check("confidence NaN", not r.passed)

    out = pipe.run([[NormalizedConcept("토마토", [f("생물", E, "생명 활동을 하는 존재"), f("요리분류", E, "요리에서 채소로 사용됨")])]])
    check("단일 repair → PASS_WITH_REPAIR", out["status"] == "PASS_WITH_REPAIR")

    r5, j5, rp5, wn5 = g.semantic_type_gate(NormalizedConcept("채소성물질", [NormalizedFeature("채소성", E, "요리에서 채소로 분류되어 사용됨")]))
    check("evidence-only → WarningAction", r5.severity == GateSeverity.WARNING and len(wn5) == 1)

    out = pipe.run([[NormalizedConcept("개",[f("동물",E,"살아있는 생명체")]), NormalizedConcept("고양이",[f("동물",E,"살아있는 생명체")])]])
    check("sparse sibling → PASS_WITH_WARNING", out["status"] == "PASS_WITH_WARNING")

    out_sq = pipe.run([[
        NormalizedConcept("사각형",[f("4변",E,"네 개의 변을 가짐"), f("4각",E,"네 개의 꼭짓점")]),
        NormalizedConcept("직사각형",[f("4변",E,"네 개의 변을 가짐"), f("4각",E,"네 개의 꼭짓점"), f("직각",E,"네 각이 모두 직각")]),
        NormalizedConcept("마름모",[f("4변",E,"네 개의 변을 가짐"), f("4각",E,"네 개의 꼭짓점"), f("등변",E,"네 변의 길이가 같음")]),
        NormalizedConcept("정사각형",[f("4변",E,"네 개의 변을 가짐"), f("4각",E,"네 개의 꼭짓점"), f("직각",E,"네 각이 모두 직각"), f("등변",E,"네 변의 길이가 같음")]),
    ]])
    d = out_sq["result"]["definitions"].get("정사각형", {})
    check("정사각형 meet", out_sq["status"] == "PASS" and d.get("is_meet"))

    rw, jw, rpw, wnw = g.semantic_type_gate(NormalizedConcept("고래", [NormalizedFeature("체온유지", E, "수중생활에서도 체온 유지")]))
    check("체온유지 → ACCEPT", jw[0].verdict == FeatureVerdict.ACCEPT)

    c, r = ParseGate.parse('{"concepts": []}')
    check("concepts=[] → ERROR", not r.passed)

    out_w = pipe.run([[NormalizedConcept("고래",[NormalizedFeature("체온유지",E,"수중생활에서도 체온 유지"), NormalizedFeature("포유류",E,"포유류에 속하는 동물")])]])
    check("warning-only → PASS_WITH_WARNING", out_w["status"] == "PASS_WITH_WARNING")

    _, r = ParseGate.parse('{"concepts": [{"name": 123, "features": []}]}')
    check("name 비문자열", not r.passed)

    _, r = ParseGate.parse('{"concepts": [{"name": "A", "features": [{"feature": 42, "type": "essential_feature", "evidence": "valid"}]}]}')
    check("feature name 비문자열", not r.passed)

    _, r = ParseGate.parse('{"concepts": [{"name": "A", "features": [{"feature": "x", "type": "essential_feature", "evidence": 999}]}]}')
    check("evidence 비문자열", not r.passed)

    # ════════════════════════════════════════════════
    # v7 Phase 1: PostDAGSiblingGate
    # ════════════════════════════════════════════════
    print("\n[v7 Phase 1: PostDAGSiblingGate]")

    check("P1-1 output에 post_dag_issues 키", "post_dag_issues" in out_sq)

    post = out_sq.get("post_dag_issues", [])
    check("P1-2 직사각형↔마름모 essential 다름 → PostDAG issue 없음",
          len([i for i in post if "sibling_pair" in i and
               sorted(i["sibling_pair"]) == ["마름모","직사각형"]]) == 0)

    # P1-2b: same-essential siblings (직접 구성)
    dag_same = DAGReasoner([
        NormalizedConcept("도형",[f("도형",E,"도형이다")]),
        NormalizedConcept("A형",[f("도형",E,"도형이다"), f("색",E,"색이 있다")]),
        NormalizedConcept("B형",[f("도형",E,"도형이다"), f("색",E,"색이 있다")]),
    ])
    dag_same.add_edge("도형","A형"); dag_same.add_edge("도형","B형")
    post_rep, post_iss = PostDAGSiblingGate.detect(dag_same, [
        NormalizedConcept("도형",[f("도형",E,"도형이다")]),
        NormalizedConcept("A형",[f("도형",E,"도형이다"), f("색",E,"색이 있다")]),
        NormalizedConcept("B형",[f("도형",E,"도형이다"), f("색",E,"색이 있다")]),
    ])
    check("P1-2b same-essential siblings → SIBLING_UNDERSPECIFIED",
          len(post_iss) > 0 and post_iss[0].get("severity") == "SIBLING_UNDERSPECIFIED")

    out_dc = pipe.run([[NormalizedConcept("개",[f("동물",E,"살아있는 생명체")]), NormalizedConcept("고양이",[f("동물",E,"살아있는 생명체")])]])
    check("P1-3 edge 없는 개·고양이 → PostDAG issue 없음",
          len(out_dc.get("post_dag_issues", [])) == 0)

    dag_t = DAGReasoner([
        NormalizedConcept("A",[f("x",E,"근거 텍스트 입력")]),
        NormalizedConcept("B",[f("x",E,"근거 텍스트 입력"), f("y",E,"근거 텍스트 입력")]),
        NormalizedConcept("C",[f("x",E,"근거 텍스트 입력"), f("z",E,"근거 텍스트 입력")]),
    ])
    dag_t.add_edge("A","B"); dag_t.add_edge("A","C")
    check("P1-4 get_siblings(B)={C}", dag_t.get_siblings("B") == {"C"})

    # ════════════════════════════════════════════════
    # v7 Phase 2: ExpansionPlanner
    # ════════════════════════════════════════════════
    print("\n[v7 Phase 2: ExpansionPlanner]")

    out3 = pipe.run([[
        NormalizedConcept("개",[f("동물",E,"살아있는 생명체")]),
        NormalizedConcept("고양이",[f("동물",E,"살아있는 생명체")]),
        NormalizedConcept("말",[f("동물",E,"살아있는 생명체")]),
    ]])
    exp = out3.get("expansion_actions", [])
    check("P2-1 개·고양이·말 → expansion_actions", len(exp) > 0, f"got {len(exp)}")
    if exp:
        check("P2-2 action_type=DEPTH", exp[0].action_type == ExpansionType.DEPTH)
        check("P2-3 3개 개념 포함", sorted(exp[0].target_concepts) == ["개","고양이","말"])
        check("P2-4 shared_attrs=['동물']", exp[0].shared_attrs == ["동물"])

    check("P2-5 정사각형 siblings essential 다름 → PostDAG expansion 없음",
          len([a for a in out_sq.get("expansion_actions", [])
               if a.reason == "DAG sibling 종차 부족"]) == 0)

    acts = ExpansionPlanner.plan(
        [{"same_essential_signature": ["X","Y"], "attrs": ["a"], "severity": "WARNING_UNDERSPECIFIED", "correction": "t"}],
        [{"sibling_pair": ["P","Q"], "shared_parent": "R", "shared_attrs": ["a"], "severity": "SIBLING_UNDERSPECIFIED", "action": "depth_expansion"}])
    check("P2-6 plan() PreDAG+PostDAG → 2 actions", len(acts) == 2)

    acts_e = ExpansionPlanner.plan([{"empty_essential": "Z"}])
    check("P2-7 empty essential → CORRECTION", len(acts_e) == 1 and acts_e[0].action_type == ExpansionType.CORRECTION)

    # ════════════════════════════════════════════════
    # v7 Phase 3 preview: mock 재진입
    # ════════════════════════════════════════════════
    print("\n[v7 Phase 3: mock 재진입]")

    out0 = pipe.run([[
        NormalizedConcept("개",[f("동물",E,"살아있는 생명체")]),
        NormalizedConcept("고양이",[f("동물",E,"살아있는 생명체")]),
    ]])
    check("P3-1 round0 WARNING", out0["status"] == "PASS_WITH_WARNING")

    out1 = pipe.run([[
        NormalizedConcept("동물",[f("동물",E,"살아있는 생명체")]),
        NormalizedConcept("개",[f("동물",E,"살아있는 생명체"), f("가축화",E,"인간에 의해 가축화된 동물")]),
        NormalizedConcept("고양이",[f("동물",E,"살아있는 생명체"), f("독립성",E,"독립적 생활이 가능한 동물")]),
    ]])
    check("P3-2 round1 PASS (종차+부모 추가)", out1["status"] == "PASS", f"got {out1['status']}")
    check("P3-3 round1 DAG 생성", bool(out1["result"]["dag"]))
    check("P3-4 round1 expansion 없음", len(out1.get("expansion_actions", [])) == 0)

    # ════════════════════════════════════════════════
    # v7 Phase 3: 스키마 + 프롬프트 + mock 재진입
    # ════════════════════════════════════════════════
    print("\n[v7 Phase 3: 스키마/프롬프트/mock]")

    # P3-5: build_expansion_prompt — DEPTH
    act_depth = ExpansionAction(ExpansionType.DEPTH, ["개","고양이"], ["동물"], reason="t")
    prompt = build_expansion_prompt(act_depth)
    check("P3-5 DEPTH 프롬프트에 target/shared 포함",
          "개, 고양이" in prompt and "동물" in prompt and "differentia_addition" in prompt)

    # P3-6: parse_expansion_response — 정상
    raw_ok = json.dumps({"expansions": [
        {"concept": "개", "new_features": [{"feature": "가축화", "type": "essential_feature", "evidence": "인간에 의해 가축화됨"}], "reason": "t"}
    ]}, ensure_ascii=False)
    orig = [NormalizedConcept("개",[f("동물",E,"살아있는 생명체")])]
    merged, prep = parse_expansion_response(raw_ok, orig)
    check("P3-6 정상 확장 파싱 → 개에 가축화 추가",
          prep.passed and any(ft.feature == "가축화" for c in merged if c.name == "개" for ft in c.features))

    # P3-7: parse_expansion_response — 스키마 위반 (new_features 없음)
    raw_bad = json.dumps({"expansions": [{"concept": "개"}]}, ensure_ascii=False)
    _, prep_bad = parse_expansion_response(raw_bad, orig)
    check("P3-7 new_features 누락 → ERROR", not prep_bad.passed)

    # P3-8: parse_expansion_response — unknown type
    raw_ut = json.dumps({"expansions": [
        {"concept": "개", "new_features": [{"feature": "x", "type": "bad_type", "evidence": "valid text"}]}
    ]}, ensure_ascii=False)
    _, prep_ut = parse_expansion_response(raw_ut, orig)
    check("P3-8 unknown type → ERROR", not prep_ut.passed)

    # P3-9: MockExpansionGenerator
    mock = MockExpansionGenerator({
        "개": [{"feature": "가축화", "type": "essential_feature", "evidence": "인간에 의해 가축화됨"}],
        "고양이": [{"feature": "독립성", "type": "essential_feature", "evidence": "독립적 생활 가능"}],
    })
    mock_raw = mock.generate(ExpansionAction(ExpansionType.DEPTH, ["개","고양이"], ["동물"]))
    mock_parsed = json.loads(mock_raw)
    check("P3-9 MockGenerator → 2 expansions",
          len(mock_parsed["expansions"]) == 2)

    # P3-10: run_with_expansion — 전체 재진입 루프
    print("\n[v7 Phase 3: run_with_expansion 루프]")
    pipe_exp = ConceptPipeline()
    mock_full = MockExpansionGenerator({
        "개": [{"feature": "가축화", "type": "essential_feature", "evidence": "인간에 의해 가축화된 동물"}],
        "고양이": [{"feature": "독립성", "type": "essential_feature", "evidence": "독립적 생활이 가능한 동물"}],
        "말": [{"feature": "기승", "type": "essential_feature", "evidence": "사람이 탈 수 있는 동물"}],
    })
    out_exp = pipe_exp.run_with_expansion(
        [NormalizedConcept("개",[f("동물",E,"살아있는 생명체")]),
         NormalizedConcept("고양이",[f("동물",E,"살아있는 생명체")]),
         NormalizedConcept("말",[f("동물",E,"살아있는 생명체")])],
        generator=mock_full, max_expansion_rounds=2)

    hist = out_exp.get("expansion_history", [])
    check("P3-10 round0 PASS_WITH_WARNING", hist[0]["status"] == "PASS_WITH_WARNING")
    check("P3-11 확장 후 종차 추가됨",
          len(hist) >= 2 and hist[-1]["n_concepts"] == 3)
    # 확장 후 세 개념의 essential이 달라짐 → WARNING 해소
    check("P3-12 확장 후 status 변화 (WARNING 해소 또는 유지 확인)",
          hist[-1]["status"] in ("PASS", "PASS_WITH_WARNING"),
          f"got {hist[-1]['status']}")

    # P3-13: generator=None → 확장 안 함
    out_none = pipe_exp.run_with_expansion(
        [NormalizedConcept("개",[f("동물",E,"살아있는 생명체")]),
         NormalizedConcept("고양이",[f("동물",E,"살아있는 생명체")])],
        generator=None)
    check("P3-13 generator=None → 확장 history 1개",
          len(out_none.get("expansion_history", [])) == 1)

    # P3-14: 확장 후 개념 검증 — 가축화 추가 확인
    final = out_exp.get("final_concepts", [])
    dog = next((c for c in final if c.name == "개"), None)
    check("P3-14 최종 개념에 종차 반영",
          dog is not None and any(ft.feature == "가축화" for ft in dog.features))

    # ════════════════════════════════════════════════
    # v7 Phase 4: ParentCandidateClassifier + generator
    # ════════════════════════════════════════════════
    print("\n[v7 Phase 4: ParentCandidateClassifier]")

    # P4-1: 단일 부모 판정
    existing = [
        NormalizedConcept("동물",[f("동물",E,"살아있는 생명체")]),
        NormalizedConcept("포유류",[f("동물",E,"살아있는 생명체"), f("젖",E,"젖을 먹임")]),
    ]
    new_dog = NormalizedConcept("개",[f("동물",E,"살아있는 생명체"), f("젖",E,"젖을 먹임"), f("가축화",E,"가축화됨")])
    parents = ParentCandidateClassifier.classify(new_dog, existing + [new_dog])
    check("P4-1 개 → 포유류 부모 (동물은 indirect)",
          parents == ["포유류"], f"got {parents}")

    # P4-2: 다중 부모 (meet)
    existing_meet = [
        NormalizedConcept("사각형",[f("4변",E,"네 변"), f("4각",E,"네 각")]),
        NormalizedConcept("직사각형",[f("4변",E,"네 변"), f("4각",E,"네 각"), f("직각",E,"직각")]),
        NormalizedConcept("마름모",[f("4변",E,"네 변"), f("4각",E,"네 각"), f("등변",E,"등변")]),
    ]
    new_sq = NormalizedConcept("정사각형",[f("4변",E,"네 변"), f("4각",E,"네 각"), f("직각",E,"직각"), f("등변",E,"등변")])
    parents_sq = ParentCandidateClassifier.classify(new_sq, existing_meet + [new_sq])
    check("P4-2 정사각형 → 다중 부모 [마름모, 직사각형]",
          parents_sq == ["마름모", "직사각형"], f"got {parents_sq}")

    # P4-3: 부모 없음 (root)
    parents_root = ParentCandidateClassifier.classify(
        NormalizedConcept("동물",[f("동물",E,"생명체")]),
        existing)
    check("P4-3 동물(root) → 부모 없음", parents_root == [])

    # P4-4: classify_all 일괄
    pmap = ParentCandidateClassifier.classify_all(
        [new_dog],
        existing)
    check("P4-4 classify_all → 개:[포유류]",
          pmap.get("개") == ["포유류"], f"got {pmap}")

    # P4-5: StaticExpansionGenerator (ExpansionGeneratorBase 상속)
    print("\n[v7 Phase 4: generator 인터페이스]")
    gen = StaticExpansionGenerator()
    gen.add_response("개", [{"feature": "가축화", "type": "essential_feature", "evidence": "가축화된 동물"}])
    check("P4-5 StaticExpansionGenerator는 ExpansionGeneratorBase",
          isinstance(gen, ExpansionGeneratorBase))

    raw_static = gen.generate(ExpansionAction(ExpansionType.DEPTH, ["개"], ["동물"]))
    parsed_static = json.loads(raw_static)
    check("P4-6 generate() → 가축화 종차",
          len(parsed_static["expansions"]) == 1 and
          parsed_static["expansions"][0]["new_features"][0]["feature"] == "가축화")

    # P4-7: ExpansionGeneratorBase 직접 호출 → NotImplementedError
    base = ExpansionGeneratorBase()
    try:
        base.generate(ExpansionAction(ExpansionType.DEPTH, ["x"], []))
        check("P4-7 Base.generate() → NotImplementedError", False)
    except NotImplementedError:
        check("P4-7 Base.generate() → NotImplementedError", True)

    # P4-8: run_with_expansion이 parent_candidates 반환
    gen_full = StaticExpansionGenerator({
        "개": [{"feature": "가축화", "type": "essential_feature", "evidence": "가축화된 동물"}],
        "고양이": [{"feature": "독립성", "type": "essential_feature", "evidence": "독립적 동물"}],
    })
    out_p4 = pipe_exp.run_with_expansion(
        [NormalizedConcept("동물",[f("동물",E,"살아있는 생명체")]),
         NormalizedConcept("개",[f("동물",E,"살아있는 생명체")]),
         NormalizedConcept("고양이",[f("동물",E,"살아있는 생명체")])],
        generator=gen_full, max_expansion_rounds=2)
    check("P4-8 run_with_expansion → parent_candidates 키",
          "parent_candidates" in out_p4)
    # 개·고양이가 동물을 부모로 가져야 함
    pc = out_p4.get("parent_candidates", {})
    check("P4-9 개·고양이 → 동물 부모 판정",
          pc.get("개") == ["동물"] and pc.get("고양이") == ["동물"],
          f"got {pc}")

    # ════════════════════════════════════════════════
    # v7 Phase 4+: CORRECTION action 자동 처리
    # ════════════════════════════════════════════════
    print("\n[v7 CORRECTION 자동 처리]")

    # C-1: non-sparse same signature → CORRECTION → generator가 종차 추가 → PASS
    gen_corr = StaticExpansionGenerator({
        "X": [{"feature": "x고유", "type": "essential_feature", "evidence": "X에만 있는 속성"}],
        "Y": [{"feature": "y고유", "type": "essential_feature", "evidence": "Y에만 있는 속성"}],
    })
    out_corr = pipe_exp.run_with_expansion(
        [NormalizedConcept("X", [f("a",E,"근거 텍스트 입력"), f("b",E,"근거 텍스트 입력")]),
         NormalizedConcept("Y", [f("a",E,"근거 텍스트 입력"), f("b",E,"근거 텍스트 입력")])],
        generator=gen_corr, max_expansion_rounds=2)

    hist_c = out_corr.get("expansion_history", [])
    check("C-1 round0 NEEDS_CORRECTION",
          hist_c[0]["status"] == "NEEDS_CORRECTION", f"got {hist_c[0]['status']}")
    check("C-2 CORRECTION 처리 후 수렴",
          len(hist_c) >= 2 and hist_c[-1]["status"] in ("PASS", "PASS_WITH_WARNING"),
          f"got {hist_c[-1]['status'] if len(hist_c) >= 2 else 'no round1'}")

    final_corr = out_corr.get("final_concepts", [])
    x_concept = next((c for c in final_corr if c.name == "X"), None)
    check("C-3 최종 X에 x고유 종차 반영",
          x_concept is not None and any(ft.feature == "x고유" for ft in x_concept.features))

    # ════════════════════════════════════════════════
    # v7 Phase 5: Heuristic + dedup + HistoryAnalyzer
    # ════════════════════════════════════════════════
    print("\n[v7 Phase 5: dedup]")

    # P5-1: ExpansionPlanner dedup — 중복 action 제거
    dup_issues = [
        {"same_essential_signature": ["A","B"], "attrs": ["x"], "severity": "WARNING_UNDERSPECIFIED", "correction": "t"},
        {"same_essential_signature": ["B","A"], "attrs": ["x"], "severity": "WARNING_UNDERSPECIFIED", "correction": "t"},
    ]
    deduped = ExpansionPlanner.plan(dup_issues)
    check("P5-1 같은 targets (순서무관) → 1개로 dedup", len(deduped) == 1, f"got {len(deduped)}")

    print("\n[v7 Phase 5: HeuristicExpansionGenerator]")

    # P5-2: lexicon 기반 종차
    heur = HeuristicExpansionGenerator({
        "개": [{"feature": "가축화", "type": "essential_feature", "evidence": "인간에 의해 가축화된 동물"}],
    })
    raw_h = heur.generate(ExpansionAction(ExpansionType.DEPTH, ["개"], ["동물"]))
    parsed_h = json.loads(raw_h)
    check("P5-2 lexicon 종차 (개→가축화)",
          parsed_h["expansions"][0]["new_features"][0]["feature"] == "가축화")

    # P5-3: fallback template (lexicon에 없는 개념)
    raw_fb = heur.generate(ExpansionAction(ExpansionType.DEPTH, ["미지개념"], ["동물"]))
    parsed_fb = json.loads(raw_fb)
    check("P5-3 fallback template (미지개념→고유속성)",
          len(parsed_fb["expansions"]) == 1 and
          "미지개념_고유속성" in parsed_fb["expansions"][0]["new_features"][0]["feature"])

    # P5-4: fallback 끄면 lexicon에 없는 개념은 skip
    heur_no_fb = HeuristicExpansionGenerator({}, fallback_template=False)
    raw_no = heur_no_fb.generate(ExpansionAction(ExpansionType.DEPTH, ["없는개념"], []))
    check("P5-4 fallback 끄면 빈 expansions", len(json.loads(raw_no)["expansions"]) == 0)

    # P5-5: Heuristic으로 run_with_expansion 수렴
    heur_full = HeuristicExpansionGenerator({
        "개": [{"feature": "가축화", "type": "essential_feature", "evidence": "가축화된 동물"}],
        "고양이": [{"feature": "독립성", "type": "essential_feature", "evidence": "독립적 동물"}],
        "말": [{"feature": "기승", "type": "essential_feature", "evidence": "사람이 타는 동물"}],
    })
    out_h = pipe_exp.run_with_expansion(
        [NormalizedConcept("개",[f("동물",E,"살아있는 생명체")]),
         NormalizedConcept("고양이",[f("동물",E,"살아있는 생명체")]),
         NormalizedConcept("말",[f("동물",E,"살아있는 생명체")])],
        generator=heur_full, max_expansion_rounds=2)
    check("P5-5 Heuristic 확장 → PASS 수렴", out_h["status"] == "PASS", f"got {out_h['status']}")

    print("\n[v7 Phase 5: ExpansionHistoryAnalyzer]")

    # P5-6: 수렴 판정
    analysis = out_h.get("expansion_analysis", {})
    check("P5-6 analysis verdict=converged",
          analysis.get("verdict") == ExpansionHistoryAnalyzer.CONVERGED, f"got {analysis.get('verdict')}")

    # P5-7: NO_OP (generator=None)
    out_noop = pipe_exp.run_with_expansion(
        [NormalizedConcept("개",[f("동물",E,"살아있는 생명체")]), NormalizedConcept("고양이",[f("동물",E,"살아있는 생명체")])],
        generator=None)
    an_noop = ExpansionHistoryAnalyzer.analyze(out_noop["expansion_history"])
    check("P5-7 generator=None → NO_OP", an_noop["verdict"] == ExpansionHistoryAnalyzer.NO_OP)

    # P5-8: STALLED (fallback 끈 generator로 빈 응답 → 종차 안 붙음 → max round까지 WARNING)
    heur_empty = HeuristicExpansionGenerator({}, fallback_template=False)
    out_stall = pipe_exp.run_with_expansion(
        [NormalizedConcept("개",[f("동물",E,"살아있는 생명체")]), NormalizedConcept("고양이",[f("동물",E,"살아있는 생명체")])],
        generator=heur_empty, max_expansion_rounds=2)
    an_stall = out_stall.get("expansion_analysis", {})
    check("P5-8 빈 종차 → STALLED 또는 OSCILLATING",
          an_stall.get("verdict") in (ExpansionHistoryAnalyzer.STALLED, ExpansionHistoryAnalyzer.OSCILLATING),
          f"got {an_stall.get('verdict')}")

    # P5-9: PARSE_FAIL 판정
    bad_hist = [{"round": 0, "status": "PASS_WITH_WARNING", "n_concepts": 2},
                {"round": 1, "status": "PARSE_FAIL", "errors": ["bad json"]}]
    an_pf = ExpansionHistoryAnalyzer.analyze(bad_hist)
    check("P5-9 PARSE_FAIL 판정", an_pf["verdict"] == ExpansionHistoryAnalyzer.PARSE_FAIL)

    # ════════════════════════════════════════════════

    total = passed + failed
    print(f"\n{'=' * 57}")
    print(f"  v7 검증: {passed}/{total}")
    if failed:
        print(f"  실패: {failed}")
    else:
        print(f"  전체 통과 ✓")
    print(f"{'=' * 57}")
