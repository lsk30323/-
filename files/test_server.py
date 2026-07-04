"""ConceptGate MCP 서버 단위 테스트.

두 레벨로 검증:
  PART 1. 함수 직접 호출 — server.run_pipeline([...]) 등 (MCP 프로토콜 우회)
  PART 2. FastMCP Client in-memory — 실제 MCP 프로토콜 레벨 (tools/resources/prompts)

실행: .venv/bin/python test_server.py
"""

import asyncio
import json
import sys

import server
from fastmcp import Client


passed = 0
failed = 0


def check(label, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✓ {label}")
    else:
        failed += 1
        print(f"  ✗ {label}  {detail}")


# 표준 입력 데이터
DOG_CAT = [
    {"name": "개", "features": [{"feature": "동물", "type": "essential_feature", "evidence": "살아있는 생명체"}]},
    {"name": "고양이", "features": [{"feature": "동물", "type": "essential_feature", "evidence": "살아있는 생명체"}]},
]

SQUARE = [
    {"name": "사각형", "features": [
        {"feature": "4변", "type": "essential_feature", "evidence": "네 개의 변을 가짐"},
        {"feature": "4각", "type": "essential_feature", "evidence": "네 개의 꼭짓점"}]},
    {"name": "직사각형", "features": [
        {"feature": "4변", "type": "essential_feature", "evidence": "네 개의 변을 가짐"},
        {"feature": "4각", "type": "essential_feature", "evidence": "네 개의 꼭짓점"},
        {"feature": "직각", "type": "essential_feature", "evidence": "네 각이 모두 직각"}]},
    {"name": "마름모", "features": [
        {"feature": "4변", "type": "essential_feature", "evidence": "네 개의 변을 가짐"},
        {"feature": "4각", "type": "essential_feature", "evidence": "네 개의 꼭짓점"},
        {"feature": "등변", "type": "essential_feature", "evidence": "네 변의 길이가 같음"}]},
    {"name": "정사각형", "features": [
        {"feature": "4변", "type": "essential_feature", "evidence": "네 개의 변을 가짐"},
        {"feature": "4각", "type": "essential_feature", "evidence": "네 개의 꼭짓점"},
        {"feature": "직각", "type": "essential_feature", "evidence": "네 각이 모두 직각"},
        {"feature": "등변", "type": "essential_feature", "evidence": "네 변의 길이가 같음"}]},
]

TOMATO = [
    {"name": "토마토", "features": [
        {"feature": "생물", "type": "essential_feature", "evidence": "생명 활동을 하는 존재"},
        {"feature": "요리분류", "type": "essential_feature", "evidence": "요리에서 채소로 사용됨"}]},
]


# ═══════════════════════════════════════════════════════
# PART 1. 함수 직접 호출
# ═══════════════════════════════════════════════════════

def test_direct():
    print("\n[PART 1] 함수 직접 호출")

    # 1-1. run_pipeline 정상
    out = server.run_pipeline(DOG_CAT)
    check("1-1 개·고양이 → PASS_WITH_WARNING", out["status"] == "PASS_WITH_WARNING")
    check("1-2 expansion_actions 존재", len(out["expansion_actions"]) > 0)
    check("1-3 출력 JSON 직렬화 가능", _json_ok(out))

    # 1-4. ParseGate 경유 — 비정상 입력 거부
    bad = server.run_pipeline([{"name": "x", "features": [{"feature": "a", "type": "essential_feature", "evidence": 999}]}])
    check("1-4 evidence 비문자열 → FAIL", bad["status"] == "FAIL" and "errors" in bad)
    check("1-5 에러 구조화 (gate/message)",
          all("gate" in e and "message" in e for e in bad["errors"]))

    # 1-6. 정사각형 meet
    sq = server.run_pipeline(SQUARE)
    check("1-6 정사각형 → PASS", sq["status"] == "PASS")
    sq_def = sq["definitions"].get("정사각형", {})
    check("1-7 정사각형 is_meet + parents",
          sq_def.get("is_meet") and sorted(sq_def.get("parents", [])) == ["마름모", "직사각형"])

    # 1-8. aux_relations 직렬화 (tuple key → list)
    tom = server.run_pipeline(TOMATO)
    check("1-8 토마토 aux_relations는 list",
          isinstance(tom["aux_relations"], list))
    check("1-9 토마토 repairs 직렬화", _json_ok(tom) and isinstance(tom["repairs"], list))

    # 1-10. expand — 종차 추가 → 수렴
    exp = server.expand(DOG_CAT, [
        {"concept": "개", "new_features": [{"feature": "가축화", "type": "essential_feature", "evidence": "인간에 의해 가축화된 동물"}]},
        {"concept": "고양이", "new_features": [{"feature": "독립성", "type": "essential_feature", "evidence": "독립적 생활이 가능한 동물"}]},
    ])
    check("1-10 expand 종차 추가 → PASS", exp["status"] == "PASS", f"got {exp['status']}")

    # 1-11. expand — 스키마 위반
    bad_exp = server.expand(DOG_CAT, [{"concept": "개"}])  # new_features 없음
    check("1-11 expand new_features 누락 → PARSE_FAIL", bad_exp["status"] == "PARSE_FAIL")
    check("1-12 PARSE_FAIL 에러 구조화",
          "errors" in bad_exp and all("gate" in e for e in bad_exp["errors"]))

    # 1-13. classify_parents
    cp = server.classify_parents(SQUARE)
    check("1-13 정사각형 → [마름모, 직사각형]",
          cp["parent_candidates"].get("정사각형") == ["마름모", "직사각형"],
          f"got {cp['parent_candidates'].get('정사각형')}")

    # 1-14. export_graph 4종
    m = server.export_graph(SQUARE, "mermaid")
    check("1-14 export mermaid", m["format"] == "mermaid" and m["content"].startswith("graph TD"))
    j = server.export_graph(SQUARE, "json")
    check("1-15 export json (파싱 가능)", json.loads(j["content"]) is not None)
    g = server.export_graph(SQUARE, "graphml")
    check("1-16 export graphml", "graphml" in g["content"])
    s = server.export_graph(SQUARE, "summary")
    check("1-17 export summary (edge=4)", s["content"]["edge_count"] == 4)
    bad_fmt = server.export_graph(SQUARE, "xml")
    check("1-18 export 잘못된 format → error", "error" in bad_fmt)

    # 1-19. analyze_expansion
    an = server.analyze_expansion([
        {"round": 0, "status": "PASS_WITH_WARNING", "n_concepts": 3, "n_actions": 1},
        {"round": 1, "status": "PASS", "n_concepts": 3, "n_actions": 0},
    ])
    check("1-19 analyze → converged", an["verdict"] == "converged")


def _json_ok(obj):
    try:
        json.dumps(obj, ensure_ascii=False)
        return True
    except (TypeError, ValueError):
        return False


# ═══════════════════════════════════════════════════════
# PART 2. FastMCP Client in-memory (실제 MCP 프로토콜)
# ═══════════════════════════════════════════════════════

async def test_mcp_protocol():
    print("\n[PART 2] FastMCP Client in-memory (MCP 프로토콜)")

    async with Client(server.mcp) as client:
        # 2-1. 도구 목록
        tools = await client.list_tools()
        tool_names = {t.name for t in tools}
        check("2-1 도구 5개 등록",
              {"run_pipeline", "expand", "classify_parents", "export_graph", "analyze_expansion"} <= tool_names,
              f"got {tool_names}")

        # 2-2. 리소스 목록
        resources = await client.list_resources()
        res_uris = {str(r.uri) for r in resources}
        check("2-2 리소스 2개 등록",
              {"conceptgate://expansion-schema", "conceptgate://pipeline-status-codes"} <= res_uris,
              f"got {res_uris}")

        # 2-3. 프롬프트 목록
        prompts = await client.list_prompts()
        prompt_names = {p.name for p in prompts}
        check("2-3 프롬프트 1개 등록", "expansion_prompt" in prompt_names, f"got {prompt_names}")

        # 2-4. run_pipeline 호출 (프로토콜 경유)
        result = await client.call_tool("run_pipeline", {"concepts": DOG_CAT})
        data = result.data
        check("2-4 run_pipeline 프로토콜 호출 → PASS_WITH_WARNING",
              data["status"] == "PASS_WITH_WARNING", f"got {data['status']}")

        # 2-5. expand 호출 (프로토콜 경유)
        result2 = await client.call_tool("expand", {
            "original_concepts": DOG_CAT,
            "expansions": [
                {"concept": "개", "new_features": [{"feature": "가축화", "type": "essential_feature", "evidence": "인간에 의해 가축화된 동물"}]},
                {"concept": "고양이", "new_features": [{"feature": "독립성", "type": "essential_feature", "evidence": "독립적 생활이 가능한 동물"}]},
            ],
        })
        check("2-5 expand 프로토콜 호출 → PASS", result2.data["status"] == "PASS", f"got {result2.data['status']}")

        # 2-6. classify_parents 호출
        result3 = await client.call_tool("classify_parents", {"concepts": SQUARE})
        check("2-6 classify_parents 프로토콜 → 정사각형 meet",
              result3.data["parent_candidates"].get("정사각형") == ["마름모", "직사각형"])

        # 2-7. export_graph 호출
        result4 = await client.call_tool("export_graph", {"concepts": SQUARE, "format": "mermaid"})
        check("2-7 export_graph 프로토콜 → mermaid",
              result4.data["content"].startswith("graph TD"))

        # 2-8. 리소스 읽기
        schema_res = await client.read_resource("conceptgate://expansion-schema")
        schema_text = schema_res[0].text
        check("2-8 expansion-schema 리소스 읽기",
              "expansions" in schema_text)

        status_res = await client.read_resource("conceptgate://pipeline-status-codes")
        check("2-9 pipeline-status-codes 리소스 읽기",
              "PASS_WITH_WARNING" in status_res[0].text)

        # 2-10. 프롬프트 호출
        prompt_result = await client.get_prompt("expansion_prompt", {
            "action_type": "depth",
            "target_concepts": "개,고양이",
            "shared_attrs": "동물",
        })
        prompt_text = prompt_result.messages[0].content.text
        check("2-10 expansion_prompt 호출",
              "개" in prompt_text and "고양이" in prompt_text)

        # 2-11. 비정상 입력도 프로토콜 통해 FAIL 반환 (예외 아님)
        bad_result = await client.call_tool("run_pipeline", {
            "concepts": [{"name": "x", "features": [{"feature": "a", "type": "essential_feature", "evidence": 999}]}],
        })
        check("2-11 비정상 입력 → FAIL (예외 없이)",
              bad_result.data["status"] == "FAIL")


# ═══════════════════════════════════════════════════════
# 실행
# ═══════════════════════════════════════════════════════

if __name__ == "__main__":
    test_direct()
    asyncio.run(test_mcp_protocol())

    total = passed + failed
    print(f"\n{'=' * 57}")
    print(f"  통과: {passed}/{total}")
    if failed:
        print(f"  실패: {failed}")
        print(f"{'=' * 57}")
        sys.exit(1)
    else:
        print(f"  전체 통과 ✓")
        print(f"{'=' * 57}")
        sys.exit(0)
