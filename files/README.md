# ConceptGate MCP Server

FCA(형식개념분석) 기반 개념 계층 분류기 ConceptGate v7을 MCP 도구로 노출하는 서버.

## 핵심 원칙

이 서버는 LLM을 호출하지 않는다. MCP client(Codex CLI, Claude Desktop,
Claude Code 등)가 LLM reasoning layer 역할을 하며, `expansion_actions`를
해석하여 종차를 생성한 뒤 `expand` 도구에 제공한다.

```
client → run_pipeline → WARNING + expansion_actions
       → client가 종차 생성 → expand → PASS → export_graph
```

## 파일 구성

```
conceptgate-mcp/
├── server.py              MCP 서버 (FastMCP)
├── concept_gate_v7.py     ConceptGate 코어 (수정 없음, import만)
├── cg_partwhole.py        part-whole 어휘 어댑터 (참조용 배포 복사본)
├── cg_graph_export.py     GraphExporter (수정 없음, import만)
├── test_server.py         단위 테스트 (직접 호출 19 + MCP 프로토콜 11)
├── pyproject.toml
├── README.md
├── codex_config.toml      Codex CLI MCP 설정 예시
├── claude_desktop_config.json  Claude Desktop MCP 설정 예시
└── sample_concepts.json   도구 입력 예시
```

## 설치

파일을 다운로드한 뒤 디렉토리 구조를 유지해야 합니다:

```
conceptgate-mcp/
├── server.py              ← 반드시 concept_gate_v7.py와 같은 디렉토리
├── concept_gate_v7.py
├── cg_partwhole.py
├── cg_graph_export.py
├── test_server.py
├── pyproject.toml
├── README.md
├── codex_config.toml      ← 설정 파일 참고용 (런타임에 불필요)
├── claude_desktop_config.json
└── sample_concepts.json
```

uv 사용 (권장 — 시스템 Python 충돌 회피):

```bash
cd conceptgate-mcp
uv venv --python 3.12
uv pip install fastmcp
```

또는 패키지로 설치:

```bash
uv pip install -e .
```

## 검증

```bash
.venv/bin/python test_server.py
```

30/30 통과해야 정상. PART 1은 함수 직접 호출, PART 2는 FastMCP Client
in-memory로 실제 MCP 프로토콜(tools/resources/prompts)을 검증한다.

## 도구 (Tools)

| 도구 | 역할 |
|---|---|
| `run_pipeline` | 개념 리스트 → DAG 생성 + 검증. 핵심 엔트리포인트 |
| `expand` | 기존 개념에 종차 병합 + 재실행. client가 종차 생성 후 호출 |
| `classify_parents` | 개념별 부모 후보 multi-label 판정 (meet 지원) |
| `export_graph` | 결과를 mermaid/json/graphml/summary로 변환 |
| `analyze_expansion` | 확장 루프 history 수렴/정체/진동 판정 |

## 리소스 (Resources)

- `conceptgate://expansion-schema` — 종차 생성 시 따라야 할 JSON 스키마
- `conceptgate://pipeline-status-codes` — 5단계 status + 권장 행동

## 프롬프트 (Prompts)

- `expansion_prompt` — 종차 생성용 구조화 프롬프트 (선택적 helper)

## 입력 형식

```json
{
  "concepts": [
    {
      "name": "개",
      "features": [
        {"feature": "동물", "type": "essential_feature", "evidence": "살아있는 생명체"}
      ]
    }
  ]
}
```

type은 essential_feature / structural_composition / contextual_usage /
locational / functional / social_treatment 중 하나. evidence는 최소 4자.
입력은 반드시 ParseGate를 경유하므로 잘못된 형식은
`{"status": "FAIL", "errors": [...]}`로 거부된다.

### is-a vs has-a

- `essential_feature` → is-a DAG 간선 (분류 계층). `dag`/`definitions`로 반환.
- `structural_composition` → has-a 구성 그래프 (부분-전체). `composition` 필드로
  별도 반환: `{"edges": [[전체, 부분], ...], "shared_parts": {부분: [전체들]}}`.

선택 필드 `relation_hint`(UFO 어휘)로 관계 맥락을 명시할 수 있다:
is_a, component_of, member_of, subcollection_of, subquantity_of,
material_of, phase_of, located_in.

```json
{"feature": "엔진", "type": "structural_composition",
 "evidence": "자동차는 엔진을 동력원으로 가진다", "relation_hint": "component_of"}
```

### 검증 출력 (Phase C)

- `composition_issues` — mereology 공리 위반: 반대칭(antisymmetry),
  순환(cycle), is-a/has-a 혼동(isa_hasa_conflict), 자기부분(self_part)
- `anti_patterns` — UFO 안티패턴 (WARNING, 차단 안 함):
  - **MixRig**: 같은 feature가 essential과 비-essential로 혼용
  - **PartOver**: is-a 조상-자손이 같은 부분을 중복 선언
  - **WholeOver**: 한 개념이 부분과 그 특수화를 동시 보유

## 연결

### Codex CLI

config.toml에 등록 (`codex_config.toml` 참조):

```toml
[mcp_servers.conceptgate]
command = "/absolute/path/to/conceptgate-mcp/.venv/bin/python"
args = ["/absolute/path/to/conceptgate-mcp/server.py"]
```

### Claude Desktop

설정 파일에 등록 (`claude_desktop_config.json` 참조):

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "conceptgate": {
      "command": "/absolute/path/to/.venv/bin/python",
      "args": ["/absolute/path/to/server.py"]
    }
  }
}
```

### Claude Code

`.claude/settings.json`:

```json
{
  "mcpServers": {
    "conceptgate": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "server.py"],
      "cwd": "/path/to/conceptgate-mcp"
    }
  }
}
```

## 로컬 디버깅

MCP Inspector:

```bash
uv run fastmcp dev server.py
```

## 대화 흐름 예시

```
사용자: "개, 고양이, 말을 분류해줘"
client: [run_pipeline] → PASS_WITH_WARNING, expansion_actions=[{depth, [개,고양이,말], [동물]}]
client: (종차 생성) [expand] → PASS
client: [export_graph mermaid] → 다이어그램
```
