# h2p Integration Work Order v0.1

| 항목 | 값 |
|---|---|
| Document kind | content document (`_vx.x` rule) + executable work order |
| Date | 2026-07-03 |
| Source | `h2p` working pipeline (3 sessions, docs/HANDOFF.md) → this repository |
| Status | **EXECUTED** — all steps below were performed on branch `feat/h2p-bootstrap-implementation`; all four validation gates GREEN in a fresh Ubuntu 24.04 container |
| Authority | implementation record; does not amend ULTIMATE_GOAL / GOAL_PROBLEM consensus docs |

## 0. Purpose

Merge the fully working, rule-based HTML→editable-PPTX pipeline (`h2p`) into
`goodand/html-to-editable-pptx`, which at merge time contained planning docs,
skills, and third-party manifests but no implementation (`src/` did not exist).

Both codebases are two phases of the same project:

- this repo = bootstrap phase (mission, architecture, reuse policy, subtree decisions)
- h2p = implementation phase (extractor, IR, mapper, 4-layer validation — all gates green)

## 1. Semantic comparison

| Axis | this repo (bootstrap) | h2p (implemented) | resolution |
|---|---|---|---|
| Mission | editability-first HTML→PPTX | same | none needed |
| Render engine | Playwright (architecture_v0.1) | **WeasyPrint** — deterministic, container-safe (lessons #3) | WeasyPrint is the v0.1 implementation; Playwright stays on the roadmap |
| IR | `src/ir/schema.ts` recommended placeholder | IR v1.2.0, invariants I1–I9 + runtime validator | h2p schema adopted verbatim |
| Chart recovery | ChartDetective reference-only (React UI) | working 2-tier rule ladder: `data-*` attrs → SVG mark/axis reverse-engineering | h2p fills the gap; matches README's recommended order (source data first, marks second, asset fallback) |
| Table extraction | Table Transformer reference-only (PyTorch) | WeasyPrint `grid_x/colspan/rowspan` native attrs | h2p fills the semantic-HTML-table slot; fake-table detection still open |
| Validation | pixel diff + editability score (planned) | 4 layers A/B/C/D + editabilityScore, all green | h2p system adopted; extends the plan with Layer D (IR-vs-OOXML IoU) |
| Reuse policy | 2 npm deps + transplant with attribution (reuse_report) | 5 npm deps + one vendor file imported verbatim | dom-to-pptx now a real `git subtree` per `third_party/subtrees.toml` |

GOAL_PROBLEM module slots now implemented: #2 renderQueue→IR (schema.ts), #3 text
run collector, #4 shape mapper, #5 semantic table extractor, #6 image mapper,
#7 bbox JSON schema, #8 PPTX output+validation. Slot #1 is implemented via
WeasyPrint box measurement instead of getBoundingClientRect (same page-absolute
px contract).

## 2. Structural set analysis

**Intersection** (already shared): mission & priorities, `src/ir|extract|validate`
layout, PptxGenJS 4.0.1 + pixelmatch as the two adopted runtime backends,
fallbackRegion concept (I6), editability score, dom-to-pptx as primary donor.

**h2p − repo** (imported by this work order):

```
src/ir/schema.ts src/ir/validate.js
src/extract/weasy_extract.py
src/mapper/ir_to_pptx.mjs
src/validate/{validate_ab.py, pixel_c.mjs, layout_d.py}
run.sh setup_mac.sh package.json package-lock.json
fixtures/{deck.html, slide13.html, logo.png}
docs/{lessons.md, HANDOFF.md}
```

**repo − h2p** (untouched planning assets): all `docs/*_v0.x.md` consensus and
evaluation documents, `docs/git_*`/`*_task*` packets, `skills/**`, `tests/**`,
`scripts/clone_repos*`, `third_party/repositories.toml` + manifests.

**Conflicts resolved**:

| Conflict | Resolution applied |
|---|---|
| h2p `src/map/` vs repo convention `src/mapper/` | renamed to `src/mapper/`; `run.sh` stage 2 updated |
| h2p `vendor/dom-to-pptx/` (1 file + LICENSE) vs `third_party/subtrees.toml` decision `adopt_subtree, whole_repo` | real `git subtree add --prefix=third_party/subtrees/dom-to-pptx … master --squash` executed; mapper imports `third_party/subtrees/dom-to-pptx/src/pptx-normalizer.js`. The h2p-verified normalizer proved **byte-identical** to upstream master — zero behavioral risk |
| Playwright pipeline (docs) vs WeasyPrint (code) | reconciliation notes added in `src/extract/README.md`; architecture docs unmodified |
| repo `.gitignore` minimal | appended `node_modules/`, `out/`, `third_party/repos/` |
| `extract-text` CLI (h2p container tool) absent in generic environments | stdlib fallback (zipfile+regex over `<a:t>` runs, same `## Slide N` format) added inside `validate_ab.py`, clearly marked, in its own commit |

**Runtime dependency graph**:

```
fixtures/*.html ─ weasy_extract.py (python: weasyprint 69) ─▶ out/*.ir.json + *.masks.json
out/*.ir.json ─ ir_to_pptx.mjs (node: pptxgenjs 4.0.1, jszip, @xmldom/xmldom;
                imports subtree pptx-normalizer verbatim via DOMParser polyfill) ─▶ out/*.pptx
Validation:  validate_ab.py (stdlib; optional extract-text CLI)          → Layer A+B
             weasyprint→pdf + soffice(pptx→pdf) + pdftoppm → pixel_c.mjs → Layer C
             layout_d.py (stdlib zipfile/regex over OOXML xfrm)          → Layer D
System deps: pango (weasyprint), libreoffice-impress, poppler-utils, fonts-noto-cjk
```

## 3. Executed steps (reproducible)

1. `git checkout -b feat/h2p-bootstrap-implementation`
2. `git subtree add --prefix=third_party/subtrees/dom-to-pptx https://github.com/atharva9167j/dom-to-pptx.git master --squash`
   — handoff v0.2 §4 verification checklist passed (package.json, bin/cli.js, skills/ present).
3. Copy h2p files per the mapping in §2, with the two path adaptations
   (`src/mapper/`, subtree import path).
4. Regenerate `fixtures/logo.png` (the original binary was not recoverable from
   the handoff packet): deterministic 64×64 PNG, teal `#4ECCA3`, black X
   diagonals, stdlib `zlib+struct` writer. Layer B hashes source↔embedded of the
   same file, so the gate is unaffected; historical md5 `efe5d80b…` in archived
   IR reports differs from the new asset — expected.
5. Add module READMEs (`src/extract|mapper|validate/README.md`), extend
   `.gitignore`, append README.md implementation-status section.
6. Environment (Ubuntu 24.04 container):
   `apt-get update && apt-get install -y poppler-utils fonts-noto-cjk libreoffice-impress`
   (stale apt index causes 404s without `update`; **`libreoffice-core` alone
   cannot load pptx — `-impress` is required**), `pip3 install weasyprint
   --break-system-packages` (installs 69.0), `npm ci`.
7. `bash run.sh fixtures/deck.html`

## 4. Verification results (this container, 2026-07-03)

| Gate | Criterion | Result |
|---|---|---|
| Layer A semantic | missing=0 per slide | **pass** — jaccard 1.0 / 1.0 / 1.0, sourceLines 19/14/3 |
| Layer B media | all source assets matched | **pass** — 1/1 (md5) |
| Layer C visual | diffPct < 5 per slide | **pass** — 3.10% / 1.19% / 1.26% (slide 3: 294,400 chart px masked) |
| Layer D geometric | no critical, worstIoU > 0.90 | **pass** — 19/19 ok, worstIoU 0.996 |
| Editability | score 1, fallback 0 | **pass** — 19 native / 0 fallback (text 10, image 1, shape 4, table 2, chart 2) |

Numbers match the original h2p run to within 0.01pp (slide 1: 3.09→3.10%, the
regenerated logo). The pipeline is deterministic per its rule-based-only policy.

## 5. Owner actions — push & PR (this session had no write access)

Executed from a clone that has these commits (or after `git bundle`/patch apply):

```bash
git push -u origin feat/h2p-bootstrap-implementation
# PR title:
#   feat: port h2p working pipeline (IR v1.2.0, 4-layer validation, all gates green)
# PR body: link this document; include §4 results table; note the dom-to-pptx
# subtree import commit is upstream code (MIT) squashed per subtrees.toml.
```

Transport options (packet ships both). The bundle is primary — the subtree
import is a **merge commit**, which `format-patch` cannot represent:

```bash
# Option 1 — bundle (exact history, recommended)
git fetch h2p-integration.bundle feat/h2p-bootstrap-implementation:feat/h2p-bootstrap-implementation
git push -u origin feat/h2p-bootstrap-implementation

# Option 2 — patches (4 logical commits only; re-run the subtree step first)
git checkout -b feat/h2p-bootstrap-implementation main
git subtree add --prefix=third_party/subtrees/dom-to-pptx \
  https://github.com/atharva9167j/dom-to-pptx.git master --squash
git am patches/*.patch
```

## 6. Roadmap after merge (from HANDOFF §7, still valid)

1. Render-environment pinning (Docker: fonts-noto-cjk + soffice version) → then tighten Layer C gate below 5% (cross-renderer floor ≈ 2.85%).
2. CSS z-index composite sort key (dom-to-pptx `sortKey` idea).
3. Border-radius clipping (clip stack is rectangular today).
4. Chart breadth: line/pie, multi-series, legends — keep the two-tier ladder.
5. Crop-fallback image for unrecoverable SVG regions.
6. Playwright extraction path as an alternative front-end producing the same IR (reconciles architecture_v0.1 §2 with the WeasyPrint implementation).
7. Fake-table detection (bbox clustering per reuse_report bootstrap task #6) — unaddressed by h2p.
