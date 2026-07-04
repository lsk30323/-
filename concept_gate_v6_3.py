"""정규화-검증형 개념 격자 추론기 v6.3

v6.2 → v6.3 변경 5건:

  [1] concepts=[] 통과 방지 — ParseGate에서 빈 concepts list → ERROR
  [2] PASS_WITH_WARNING 상태 추가 — WARNING만 있고 repair 없을 때
  [3] WarningAction / RepairAction 분리 — weak warning은 WarningAction
  [4] feature/evidence/name 비문자열 검사 — isinstance(x, str) 강제
  [5] TaxoAdapt get_siblings() 이식 — DAGReasoner에 형제 노드 수집

  + v6.2의 6건 유지 (GateSeverity, ParseGate schema, ResultClassifier,
    SignatureGate WARNING, WEAK_CONTEXT_WARNING, 테스트 8건)
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
    ]
    SINGLE_STRONG = {
        "서식지": FeatureType.LOCATIONAL, "수중생활": FeatureType.LOCATIONAL,
        "해양생활": FeatureType.LOCATIONAL, "착용용도": FeatureType.FUNCTIONAL,
    }
    ESSENTIAL_EXCEPTIONS = {
        "분류학", "생물학적 분류", "계통분류", "계통적 분류", "형태학적", "해부학적",
    }

    @classmethod
    def _scan(cls, text):
        for m, ft in cls.SINGLE_STRONG.items():
            if m in text: return ft, [m]
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
        pu = parent.all_attrs - child.all_attrs
        cx = {f.feature for f in parent.features if f.type not in ISA_ALLOWED_TYPES and f.feature in pu}
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
# SignatureGate (v6.2: WARNING vs NEEDS_CORRECTION)
# ═══════════════════════════════════════════════════════

class SignatureGate:
    MIN_ESSENTIAL_FOR_LEAF = 2

    @staticmethod
    def detect(concepts) -> Tuple[GateReport, List[Dict]]:
        report = GateReport(target="[SignatureGate]")
        issues = []
        sig_map = defaultdict(list)
        for c in concepts: sig_map[frozenset(c.essential_attrs)].append(c.name)

        for sig, names in sig_map.items():
            if not sig:
                for nm in names:
                    issues.append({"empty_essential": nm})
                    report.results.append(GateResult("Signature Gate", False,
                        f'"{nm}": essential 없음',
                        {"concept": nm}, GateSeverity.NEEDS_CORRECTION))
            elif len(names) > 1:
                # [v6.2] sparse → WARNING, otherwise NEEDS_CORRECTION
                if len(sig) < SignatureGate.MIN_ESSENTIAL_FOR_LEAF:
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
                report.results.append(GateResult("Signature Gate",
                    sev == GateSeverity.WARNING,  # WARNING은 passed=True
                    f'{tag}: {sorted(names)}', issue, sev))

        if not issues:
            report.results.append(GateResult("Signature Gate", True, "ok",
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

    def finalize(self):
        lv = self.topo_sort(); defs = self.definitions(); self.collect_aux()
        conn = {n for (p, c) in self.edge_meta for n in (p, c)}
        return {"dag": dict(self.dag), "levels": lv, "definitions": defs,
                "aux_relations": dict(self.aux_graph),
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

        sig_rep, sig_iss = SignatureGate.detect(cleaned)
        all_reps.append(sig_rep)
        reasoner = DAGReasoner(cleaned)
        if len(cleaned) < 2: return all_reps, all_repairs, all_warnings, reasoner, sig_iss
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
        return all_reps, all_repairs, all_warnings, reasoner, sig_iss

    def run(self, cands_per_round):
        hist, prompts = [], []
        reasoner = None
        for ri, cands in enumerate(cands_per_round):
            if ri >= self.max_rounds: break
            reps, repairs, warnings, reasoner, sig_iss = self.validate_hierarchy(cands)
            hist.append(reps); result = reasoner.finalize()
            status = ResultClassifier.classify(reps, repairs, warnings, sig_iss, bool(result["dag"]))
            if status != PipelineStatus.FAIL:
                return {"result": result, "status": status.value, "rounds_used": ri+1,
                        "all_reports": hist, "repairs": repairs, "warnings": warnings,
                        "signature_issues": sig_iss, "correction_prompts": prompts}
            prompts.append(CorrectionPromptGenerator.generate_standalone(reps))
        result = reasoner.finalize() if reasoner else {"dag":{},"levels":{},"definitions":{},"aux_relations":{},"isolated":[]}
        return {"result": result, "status": "FAIL", "rounds_used": len(cands_per_round),
                "all_reports": hist, "repairs": [], "warnings": [],
                "signature_issues": [], "correction_prompts": prompts}


# ═══════════════════════════════════════════════════════
# 테스트
# ═══════════════════════════════════════════════════════

def f(feat, ftype, ev, cl=""): return NormalizedFeature(feat, ftype, ev, cl or ev)

if __name__ == "__main__":
    E = FeatureType.ESSENTIAL
    pipe = ConceptPipeline()
    g = ConceptGate()

    # ════════════════════════════════════════════════
    # v6.2 기존 8건 (회귀 방지)
    # ════════════════════════════════════════════════

    print("[v6.2-1: concepts not list]")
    c1, r1 = ParseGate.parse('{"concepts": "not a list"}')
    assert not r1.passed and c1 is None
    print(f"  {r1.failures[0].message}")
    print("✓\n")

    print("[v6.2-2: features not list]")
    c2, r2 = ParseGate.parse('{"concepts": [{"name": "A", "features": "bad"}]}')
    assert not r2.passed
    print(f"  {r2.failures[0].message}")
    print("✓\n")

    print("[v6.2-3: confidence NaN/inf]")
    c3, r3 = ParseGate.parse('{"concepts": [{"name": "A", "features": [{"feature": "x", "type": "essential_feature", "evidence": "valid text", "confidence": "NaN"}]}]}')
    assert not r3.passed
    c3b, r3b = ParseGate.parse('{"concepts": [{"name": "B", "features": [{"feature": "y", "type": "essential_feature", "evidence": "valid text", "confidence": "Infinity"}]}]}')
    assert not r3b.passed
    print("✓\n")

    print("[v6.2-4: single concept repair → PASS_WITH_REPAIR]")
    out4 = pipe.run([[
        NormalizedConcept("토마토", [
            f("생물", E, "생명 활동을 하는 존재"),
            f("요리분류", E, "요리에서 채소로 사용됨"),
        ]),
    ]])
    assert out4["status"] == "PASS_WITH_REPAIR", f"FAIL: {out4['status']}"
    assert len(out4["repairs"]) > 0
    assert len(out4["warnings"]) == 0  # demote는 repair, warning 아님
    print(f"  status={out4['status']}, repairs={len(out4['repairs'])}, warnings={len(out4['warnings'])}")
    print("✓\n")

    print("[v6.2-5: evidence-only contextual → WEAK_CONTEXT_WARNING]")
    c5 = NormalizedConcept("채소성물질", [
        NormalizedFeature("채소성", E, "요리에서 채소로 분류되어 사용됨")])
    r5, j5, rp5, wn5 = g.semantic_type_gate(c5)
    assert r5.severity == GateSeverity.WARNING
    assert "WEAK_CONTEXT_WARNING" in r5.message
    assert j5[0].verdict == FeatureVerdict.ACCEPT
    assert len(rp5) == 0  # v6.3: 더 이상 repairs에 안 들어감
    assert len(wn5) > 0   # v6.3: warnings에 들어감
    assert isinstance(wn5[0], WarningAction)
    print(f"  severity={r5.severity}, repairs={len(rp5)}, warnings={len(wn5)}")
    print("✓\n")

    print("[v6.2-6: sparse sibling → WARNING_UNDERSPECIFIED]")
    out6 = pipe.run([[
        NormalizedConcept("개", [f("동물", E, "살아있는 생명체")]),
        NormalizedConcept("고양이", [f("동물", E, "살아있는 생명체")]),
    ]])
    assert out6["status"] == "PASS_WITH_WARNING", f"FAIL: {out6['status']}"
    sig_warns = [i for i in out6["signature_issues"] if i.get("severity") == "WARNING_UNDERSPECIFIED"]
    assert len(sig_warns) > 0
    print(f"  status={out6['status']}")
    print("✓\n")

    print("[회귀: 정사각형 meet]")
    out_sq = pipe.run([[
        NormalizedConcept("사각형", [f("4변", E, "네 개의 변을 가짐"), f("4각", E, "네 개의 꼭짓점")]),
        NormalizedConcept("직사각형", [f("4변", E, "네 개의 변을 가짐"), f("4각", E, "네 개의 꼭짓점"),
                                     f("직각", E, "네 각이 모두 직각")]),
        NormalizedConcept("마름모", [f("4변", E, "네 개의 변을 가짐"), f("4각", E, "네 개의 꼭짓점"),
                                   f("등변", E, "네 변의 길이가 같음")]),
        NormalizedConcept("정사각형", [f("4변", E, "네 개의 변을 가짐"), f("4각", E, "네 개의 꼭짓점"),
                                     f("직각", E, "네 각이 모두 직각"), f("등변", E, "네 변의 길이가 같음")]),
    ]])
    assert out_sq["status"] == "PASS"
    d = out_sq["result"]["definitions"]["정사각형"]
    assert d["is_meet"] and sorted(d["parents"]) == ["마름모", "직사각형"]
    print("✓\n")

    print("[회귀: 체온유지 evidence noise → ESSENTIAL 유지]")
    c_w = NormalizedConcept("고래", [NormalizedFeature("체온유지", E, "수중생활에서도 체온 유지")])
    rw, jw, rpw, wnw = g.semantic_type_gate(c_w)
    assert jw[0].verdict == FeatureVerdict.ACCEPT
    assert rw.severity == GateSeverity.WARNING
    assert len(rpw) == 0 and len(wnw) > 0
    print(f"  verdict={jw[0].verdict}, repairs={len(rpw)}, warnings={len(wnw)}")
    print("✓\n")

    # ════════════════════════════════════════════════
    # v6.3 신규 6건
    # ════════════════════════════════════════════════

    print("[v6.3-1: concepts=[] → ERROR]")
    c_empty, r_empty = ParseGate.parse('{"concepts": []}')
    assert not r_empty.passed and c_empty is None
    assert "빈 리스트" in r_empty.failures[0].message
    print(f"  {r_empty.failures[0].message}")
    print("✓\n")

    print("[v6.3-2: PASS_WITH_WARNING (warning only, no repair)]")
    out_warn = pipe.run([[
        NormalizedConcept("고래", [
            NormalizedFeature("체온유지", E, "수중생활에서도 체온 유지"),
            NormalizedFeature("포유류", E, "포유류에 속하는 동물"),
        ]),
    ]])
    assert out_warn["status"] == "PASS_WITH_WARNING", f"FAIL: {out_warn['status']}"
    assert len(out_warn["repairs"]) == 0
    assert len(out_warn["warnings"]) > 0
    print(f"  status={out_warn['status']}, warnings={len(out_warn['warnings'])}")
    print("✓\n")

    print("[v6.3-3: name 비문자열 → ERROR]")
    c_nn, r_nn = ParseGate.parse('{"concepts": [{"name": 123, "features": []}]}')
    assert not r_nn.passed
    assert "비문자열" in r_nn.failures[0].message
    print(f"  {r_nn.failures[0].message}")
    print("✓\n")

    print("[v6.3-4: feature name 비문자열 → ERROR]")
    c_fn, r_fn = ParseGate.parse('{"concepts": [{"name": "A", "features": [{"feature": 42, "type": "essential_feature", "evidence": "valid"}]}]}')
    assert not r_fn.passed
    assert "비문자열" in r_fn.failures[0].message
    print(f"  {r_fn.failures[0].message}")
    print("✓\n")

    print("[v6.3-5: evidence 비문자열 → ERROR]")
    c_ev, r_ev = ParseGate.parse('{"concepts": [{"name": "A", "features": [{"feature": "x", "type": "essential_feature", "evidence": 999}]}]}')
    assert not r_ev.passed
    assert "비문자열" in r_ev.failures[0].message
    print(f"  {r_ev.failures[0].message}")
    print("✓\n")

    print("[v6.3-6: TaxoAdapt get_siblings()]")
    out_sib = pipe.run([[
        NormalizedConcept("사각형", [f("4변", E, "네 개의 변을 가짐"), f("4각", E, "네 개의 꼭짓점")]),
        NormalizedConcept("직사각형", [f("4변", E, "네 개의 변을 가짐"), f("4각", E, "네 개의 꼭짓점"),
                                     f("직각", E, "네 각이 모두 직각")]),
        NormalizedConcept("마름모", [f("4변", E, "네 개의 변을 가짐"), f("4각", E, "네 개의 꼭짓점"),
                                   f("등변", E, "네 변의 길이가 같음")]),
    ]])
    # DAGReasoner를 직접 재구성하여 get_siblings 테스트
    concepts_sib = [
        NormalizedConcept("사각형", [f("4변", E, "네 개의 변을 가짐"), f("4각", E, "네 개의 꼭짓점")]),
        NormalizedConcept("직사각형", [f("4변", E, "네 개의 변을 가짐"), f("4각", E, "네 개의 꼭짓점"),
                                     f("직각", E, "네 각이 모두 직각")]),
        NormalizedConcept("마름모", [f("4변", E, "네 개의 변을 가짐"), f("4각", E, "네 개의 꼭짓점"),
                                   f("등변", E, "네 변의 길이가 같음")]),
    ]
    dag_sib = DAGReasoner(concepts_sib)
    dag_sib.add_edge("사각형", "직사각형")
    dag_sib.add_edge("사각형", "마름모")
    siblings = dag_sib.get_siblings("직사각형")
    assert "마름모" in siblings and "직사각형" not in siblings
    assert "사각형" not in siblings  # parent, not sibling
    print(f"  직사각형의 siblings: {siblings}")
    print("✓\n")

    print("=" * 57)
    print("  v6.3 모든 검증 통과 ✓  (v6.2 8건 + v6.3 6건 = 14건)")
    print("=" * 57)
