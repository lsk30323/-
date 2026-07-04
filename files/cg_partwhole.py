"""Part-whole 어댑터 — obo-relations subtree에서 조립.

vendor/obo-relations/core.obo의 관계 정의(part of / has part / member of ...)를
읽어 has-a(구성적) 관계 어휘를 제공한다. subtree를 직접 수정하지 않고 여기서 wrap.

핵심 용도:
  1. LLM의 relation_hint(UFO 어휘) → ConceptGate FeatureType 매핑
  2. OBO 표준 part-whole 관계 집합/추이성 노출 (Phase C DAG 추론 대비)

stdlib만 사용. core.obo가 없으면 내장 상수로 graceful fallback.
"""

from __future__ import annotations
import os
import re
from typing import Dict, Optional


# ── UFO relation_hint → FeatureType.value 매핑 (Phase A 판별 가이드와 일치) ──
# is_a/material_of만 is-a 계층(essential). 나머지는 비-essential.
RELATION_HINT_TYPE: Dict[str, str] = {
    "is_a":            "essential_feature",       # 분류적 (C ⊑ D)
    "material_of":     "essential_feature",       # Winston: 재료-대상은 본질 가능
    "component_of":    "structural_composition",  # 구성요소-통합체 (has-a)
    "member_of":       "structural_composition",  # 멤버-집합
    "subcollection_of":"structural_composition",  # 집합-집합
    "subquantity_of":  "structural_composition",  # 수량-수량
    "phase_of":        "contextual_usage",        # UFO Phase (anti-rigid)
    "located_in":      "locational",              # 장소-영역
}

# core.obo를 못 읽을 때 쓰는 내장 fallback (BFO id → 이름)
_FALLBACK_OBO_PARTWHOLE: Dict[str, str] = {
    "BFO:0000050": "part of",
    "BFO:0000051": "has part",
    "RO:0002350":  "member of",
    "RO:0002351":  "has member",
}

# core.obo에서 part-whole/구성 계열로 취급할 이름 (정확 일치, 역할/성질 계열 제외)
_PARTWHOLE_NAMES = frozenset({
    "part of", "has part", "member of", "has member",
    "constituted of", "contains process",
})


def hint_to_feature_type(relation_hint: Optional[str]) -> Optional[str]:
    """relation_hint(UFO 어휘) → FeatureType.value. 미지/None이면 None."""
    if not relation_hint or not isinstance(relation_hint, str):
        return None
    return RELATION_HINT_TYPE.get(relation_hint.strip().lower())


def is_has_a(relation_hint: Optional[str]) -> bool:
    """relation_hint가 구성적(has-a, structural) 관계인지."""
    return hint_to_feature_type(relation_hint) == "structural_composition"


def _default_obo_path() -> str:
    """cg_partwhole.py 기준으로 core.obo 후보 경로 탐색 (root / files/ 양쪽)."""
    here = os.path.dirname(os.path.abspath(__file__))
    for rel in ("vendor/obo-relations/core.obo",
                "../vendor/obo-relations/core.obo"):
        p = os.path.join(here, rel)
        if os.path.exists(p):
            return p
    return os.path.join(here, "vendor/obo-relations/core.obo")


def load_obo_partwhole(path: Optional[str] = None) -> Dict[str, Dict]:
    """core.obo의 part-whole Typedef를 파싱.

    반환: {relation_id: {"name", "transitive"(bool), "inverse_of"(str|None)}}
    파일이 없거나 파싱 실패 시 내장 fallback 사용 (never raise).
    """
    path = path or _default_obo_path()
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return {rid: {"name": nm, "transitive": True, "inverse_of": None}
                for rid, nm in _FALLBACK_OBO_PARTWHOLE.items()}

    out: Dict[str, Dict] = {}
    for block in text.split("[Typedef]"):
        m_id = re.search(r"^id:\s*(\S+)", block, re.MULTILINE)
        m_nm = re.search(r"^name:\s*(.+)$", block, re.MULTILINE)
        if not m_id or not m_nm:
            continue
        name = m_nm.group(1).strip()
        if name not in _PARTWHOLE_NAMES:
            continue
        m_inv = re.search(r"^inverse_of:\s*(\S+)", block, re.MULTILINE)
        out[m_id.group(1)] = {
            "name": name,
            "transitive": bool(re.search(r"^is_transitive:\s*true", block, re.MULTILINE)),
            "inverse_of": m_inv.group(1) if m_inv else None,
        }
    return out or {rid: {"name": nm, "transitive": True, "inverse_of": None}
                   for rid, nm in _FALLBACK_OBO_PARTWHOLE.items()}


if __name__ == "__main__":
    rels = load_obo_partwhole()
    print(f"obo part-whole 관계 {len(rels)}개:")
    for rid, meta in sorted(rels.items()):
        t = "transitive" if meta["transitive"] else "-"
        print(f"  {rid:14} {meta['name']:14} [{t}]")
    print("\nrelation_hint 매핑:")
    for h, t in RELATION_HINT_TYPE.items():
        print(f"  {h:18} → {t}")
