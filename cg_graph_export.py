"""ConceptGate GraphExporter (v7 Phase 5)

DAG/levels/definitions/signature_issues/warnings를 JSON, GraphML, Mermaid로 내보냄.

concept_gate_v7.py와 분리된 별도 모듈 (코어 stdlib-only 유지).
ConceptPipeline.run() 또는 run_with_expansion()의 출력 dict를 입력으로 받음.

사용:
    from cg_graph_export import GraphExporter
    out = pipe.run([concepts])
    print(GraphExporter.to_mermaid(out))
    print(GraphExporter.to_json(out))
    print(GraphExporter.to_graphml(out))

의존성: Python 표준 라이브러리만 (json, xml.etree).
"""

import json
import xml.etree.ElementTree as ET
from typing import Dict, List


class GraphExporter:
    """파이프라인 출력 → 그래프 포맷 변환."""

    # ─────────────────────────────────────────────
    # JSON
    # ─────────────────────────────────────────────
    @staticmethod
    def to_json(pipeline_output: Dict, indent: int = 2) -> str:
        """전체 그래프 상태를 JSON으로. round-trip 가능한 구조."""
        result = pipeline_output.get("result", {})
        dag = result.get("dag", {})

        nodes = []
        levels = result.get("levels", {})
        definitions = result.get("definitions", {})
        for name in sorted(set(list(levels.keys()) + list(dag.keys()) +
                               [c for children in dag.values() for c in children])):
            node = {"id": name, "level": levels.get(name)}
            if name in definitions:
                d = definitions[name]
                node["is_meet"] = d.get("is_meet", False)
                node["parents"] = d.get("parents", [])
                node["formula"] = d.get("formula", "")
            nodes.append(node)

        edges = []
        for parent, children in dag.items():
            for child in children:
                edges.append({"from": parent, "to": child, "relation": "is_a"})

        payload = {
            "status": pipeline_output.get("status"),
            "nodes": nodes,
            "edges": edges,
            "isolated": result.get("isolated", []),
            "aux_relations": result.get("aux_relations", {}),
            "signature_issues": pipeline_output.get("signature_issues", []),
            "post_dag_issues": pipeline_output.get("post_dag_issues", []),
            "warnings": [
                {"concept": w.concept, "feature": w.feature, "reason": w.reason}
                for w in pipeline_output.get("warnings", [])
            ],
        }
        return json.dumps(payload, ensure_ascii=False, indent=indent)

    # ─────────────────────────────────────────────
    # Mermaid (graph TD)
    # ─────────────────────────────────────────────
    @staticmethod
    def to_mermaid(pipeline_output: Dict) -> str:
        """Mermaid flowchart (graph TD). is-a 엣지 + meet 노드 강조."""
        result = pipeline_output.get("result", {})
        dag = result.get("dag", {})
        definitions = result.get("definitions", {})
        isolated = result.get("isolated", [])

        lines = ["graph TD"]

        # 노드 ID 안전화 (Mermaid는 한글 ID 가능하나 공백/특수문자 회피)
        def nid(name):
            return "n_" + "".join(c if c.isalnum() else f"_{ord(c)}_" for c in name)

        # 엣지
        seen_nodes = set()
        for parent, children in dag.items():
            for child in children:
                lines.append(f'    {nid(parent)}["{parent}"] --> {nid(child)}["{child}"]')
                seen_nodes.add(parent); seen_nodes.add(child)

        # meet 노드 강조 (스타일)
        for name, d in definitions.items():
            if d.get("is_meet") and name in seen_nodes:
                lines.append(f'    style {nid(name)} fill:#EEEDFE,stroke:#534AB7')

        # 고립 노드
        for name in isolated:
            if name not in seen_nodes:
                lines.append(f'    {nid(name)}["{name}"]')
                lines.append(f'    style {nid(name)} fill:#FAEEDA,stroke:#854F0B')

        return "\n".join(lines)

    # ─────────────────────────────────────────────
    # GraphML (XML)
    # ─────────────────────────────────────────────
    @staticmethod
    def to_graphml(pipeline_output: Dict) -> str:
        """GraphML (yEd/Gephi 호환). 노드 level + meet 속성 포함."""
        result = pipeline_output.get("result", {})
        dag = result.get("dag", {})
        levels = result.get("levels", {})
        definitions = result.get("definitions", {})

        ns = "http://graphml.graphdrawing.org/xmlns"
        ET.register_namespace("", ns)
        root = ET.Element(f"{{{ns}}}graphml")

        # key 정의
        k_level = ET.SubElement(root, f"{{{ns}}}key",
                                {"id": "level", "for": "node", "attr.name": "level", "attr.type": "int"})
        k_meet = ET.SubElement(root, f"{{{ns}}}key",
                               {"id": "meet", "for": "node", "attr.name": "is_meet", "attr.type": "boolean"})
        k_rel = ET.SubElement(root, f"{{{ns}}}key",
                              {"id": "relation", "for": "edge", "attr.name": "relation", "attr.type": "string"})

        graph = ET.SubElement(root, f"{{{ns}}}graph", {"id": "G", "edgedefault": "directed"})

        all_nodes = set(levels.keys()) | set(dag.keys())
        for children in dag.values():
            all_nodes.update(children)
        all_nodes.update(result.get("isolated", []))

        for name in sorted(all_nodes):
            n = ET.SubElement(graph, f"{{{ns}}}node", {"id": name})
            if name in levels and levels[name] is not None:
                d = ET.SubElement(n, f"{{{ns}}}data", {"key": "level"})
                d.text = str(levels[name])
            if name in definitions:
                dm = ET.SubElement(n, f"{{{ns}}}data", {"key": "meet"})
                dm.text = "true" if definitions[name].get("is_meet") else "false"

        eid = 0
        for parent, children in dag.items():
            for child in children:
                e = ET.SubElement(graph, f"{{{ns}}}edge",
                                  {"id": f"e{eid}", "source": parent, "target": child})
                dr = ET.SubElement(e, f"{{{ns}}}data", {"key": "relation"})
                dr.text = "is_a"
                eid += 1

        return ET.tostring(root, encoding="unicode")

    # ─────────────────────────────────────────────
    # 요약 통계
    # ─────────────────────────────────────────────
    @staticmethod
    def summary(pipeline_output: Dict) -> Dict:
        """그래프 통계 요약."""
        result = pipeline_output.get("result", {})
        dag = result.get("dag", {})
        edge_count = sum(len(ch) for ch in dag.values())
        meet_count = sum(1 for d in result.get("definitions", {}).values() if d.get("is_meet"))
        return {
            "status": pipeline_output.get("status"),
            "node_count": len(set(list(result.get("levels", {}).keys()))),
            "edge_count": edge_count,
            "meet_count": meet_count,
            "isolated_count": len(result.get("isolated", [])),
            "max_level": max(result.get("levels", {}).values(), default=0),
            "warning_count": len(pipeline_output.get("warnings", [])),
            "signature_issue_count": len(pipeline_output.get("signature_issues", [])),
        }


# ═══════════════════════════════════════════════════════
# 인라인 테스트
# ═══════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import concept_gate_v7 as cg

    E = cg.FeatureType.ESSENTIAL
    f = lambda n, e: cg.NormalizedFeature(n, E, e, e)

    passed = 0; failed = 0
    def check(label, cond, detail=""):
        global passed, failed
        if cond:
            passed += 1; print(f"  ✓ {label}")
        else:
            failed += 1; print(f"  ✗ {label}  {detail}")

    pipe = cg.ConceptPipeline()
    out = pipe.run([[
        cg.NormalizedConcept("사각형",[f("4변","네 개의 변을 가짐"),f("4각","네 개의 꼭짓점")]),
        cg.NormalizedConcept("직사각형",[f("4변","네 개의 변을 가짐"),f("4각","네 개의 꼭짓점"),f("직각","네 각이 모두 직각")]),
        cg.NormalizedConcept("마름모",[f("4변","네 개의 변을 가짐"),f("4각","네 개의 꼭짓점"),f("등변","네 변의 길이가 같음")]),
        cg.NormalizedConcept("정사각형",[f("4변","네 개의 변을 가짐"),f("4각","네 개의 꼭짓점"),f("직각","네 각이 모두 직각"),f("등변","네 변의 길이가 같음")]),
    ]])

    print("\n[GraphExporter]")

    # JSON
    j = GraphExporter.to_json(out)
    parsed = json.loads(j)
    check("to_json: 파싱 가능 + nodes/edges 키",
          "nodes" in parsed and "edges" in parsed)
    check("to_json: 정사각형 edge 2개 (마름모, 직사각형 → 정사각형)",
          sum(1 for e in parsed["edges"] if e["to"] == "정사각형") == 2)
    check("to_json: 정사각형 is_meet=True",
          any(n["id"] == "정사각형" and n.get("is_meet") for n in parsed["nodes"]))

    # Mermaid
    m = GraphExporter.to_mermaid(out)
    check("to_mermaid: graph TD 시작", m.startswith("graph TD"))
    check("to_mermaid: 엣지 화살표 포함", "-->" in m)
    check("to_mermaid: meet 노드 style", "style" in m and "#EEEDFE" in m)

    # GraphML
    g = GraphExporter.to_graphml(out)
    check("to_graphml: XML 파싱 가능", ET.fromstring(g) is not None)
    check("to_graphml: graphml 루트", "graphml" in g)
    check("to_graphml: edge relation=is_a", "is_a" in g)

    # summary
    s = GraphExporter.summary(out)
    check("summary: edge_count=4", s["edge_count"] == 4, f"got {s['edge_count']}")
    check("summary: meet_count=1", s["meet_count"] == 1, f"got {s['meet_count']}")
    check("summary: max_level=2", s["max_level"] == 2, f"got {s['max_level']}")

    print(f"\n{'=' * 50}")
    print(f"  GraphExporter: {passed}/{passed+failed}")
    print("  전체 통과 ✓" if failed == 0 else f"  실패: {failed}")
    print(f"{'=' * 50}")
    sys.exit(1 if failed else 0)
