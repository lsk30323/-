# ConceptGate Taxonomy

Developer: 탁재현 (goodand/concept-gate-taxonomy)

## Code Philosophy: Ponytail Rules

Before writing any code, traverse this decision ladder top-down. Stop at the first rung that solves the problem.

1. **YAGNI**: Does this need to exist at all? If not, skip it.
2. **Codebase reuse**: Already in this codebase? Reuse it.
3. **Standard library**: stdlib solves it? Use stdlib.
4. **Native platform**: Native feature covers it? Use it.
5. **Installed dependency**: Already-installed dep solves it? Use it.
6. **One-liner**: Can it be one line? Make it one line.
7. **Minimum code**: Only then write the minimum code that works.

The ladder runs AFTER you understand the problem, not instead of it. Read the code fully and trace the real flow before picking a rung.

### Safety (never cut)
- Input validation at trust boundaries
- Error handling that prevents data loss
- Security
- Accessibility
- Explicit user requests

### Intentional simplifications
Mark with `ponytail:` comments that name the ceiling and upgrade path:
```python
# ponytail: O(n^2) scan; upgrade to index if n > 1000
```

### Principles
- Deletion > Addition
- Boring > Clever
- Fewest files possible
- Shortest working diff wins
- No abstraction unless explicitly requested
- Bug fixes target root cause, not symptom

## Subtree Assembly

When writing code, prefer bringing in existing code as **git subtrees** and assembling from reusable parts.

- Before creating new modules, search for existing open-source implementations that can be added as subtrees
- When a feature maps to a well-known library/repo, `git subtree add` it rather than reimplementing
- Keep subtree boundaries clean: don't modify subtree code directly, wrap/adapt in project code
- Track subtree origins in this file under "Subtree Registry" below

### Subtree Registry

| Prefix | Remote | Branch | Purpose |
|--------|--------|--------|---------|
| `vendor/obo-relations` | oborel/obo-relations | master | part_of (BFO:0000050) / has_part (BFO:0000051) 표준 공리. Phase B `relation_hint` 검증. 핵심 파일: `core.obo` |

Subtree 갱신: `git subtree pull --prefix vendor/obo-relations https://github.com/oborel/obo-relations.git master --squash`

## Project Structure

- `concept_gate_v7.py` -- Core FCA-based concept lattice reasoner
- `cg_partwhole.py` -- Part-whole adapter assembling vocabulary from vendor/obo-relations subtree
- `files/server.py` -- MCP server (FastMCP adapter)
- `files/concept_gate_v7.py`, `files/cg_partwhole.py` -- Deployment copies (keep in sync with root)
- `qa_v7.py` -- QA test suite (89 tests)
- `vendor/` -- git subtrees (see Subtree Registry)
- `docs/` -- Implementation packets and documentation

## Key Architecture

- `FeatureType`: ESSENTIAL, CONTEXTUAL, LOCATIONAL, FUNCTIONAL, SOCIAL, STRUCTURAL(has-a)
- `ISA_ALLOWED_TYPES = {FeatureType.ESSENTIAL}` -- only ESSENTIAL creates DAG edges
- `DAGReasoner.composition_view()` -- separate has-a graph (STRUCTURAL edges + UFO shareable detection)
- `relation_hint` (LLM output) -- UFO vocabulary corrected via `cg_partwhole.hint_to_feature_type()`
- `SemanticTypeInference` -- Korean-language keyword heuristic for feature type classification
- `build_expansion_prompt()` -- LLM prompt generator for concept expansion
- `parse_expansion_response()` -- LLM response parser
- `DAGReasoner` -- builds DAG from essential_attrs subset inclusion

## Git

- Do NOT commit without explicit permission
- Branch: `claude/enable-remote-control-Lh6Di` (current working branch)
- Target repo: `goodand/concept-gate-taxonomy` (will be registered separately)
