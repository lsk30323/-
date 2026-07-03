# h2p → goodand/html-to-editable-pptx Integration Packet

Date: 2026-07-03 · All four validation gates GREEN in a fresh Ubuntu 24.04 container.
Full analysis & instructions: `h2p_integration_work_order_v0.1.md` (English).

이 세션은 `goodand/html-to-editable-pptx`에 push 권한이 없어(계정 `lsk30323`),
통합 결과를 이 패킷으로 전달합니다. 아래 두 방법 중 하나로 적용하세요.

## Apply (owner of goodand/html-to-editable-pptx)

```bash
git clone https://github.com/goodand/html-to-editable-pptx.git && cd html-to-editable-pptx

# Option 1 — bundle (exact history incl. dom-to-pptx subtree merge, recommended)
git fetch ../path/to/h2p-integration.bundle \
  feat/h2p-bootstrap-implementation:feat/h2p-bootstrap-implementation
git push -u origin feat/h2p-bootstrap-implementation
# then open the PR:
#   feat: port h2p working pipeline (IR v1.2.0, 4-layer validation, all gates green)

# Option 2 — patches (subtree step must be re-run first; format-patch cannot
# carry merge commits)
git checkout -b feat/h2p-bootstrap-implementation main
git subtree add --prefix=third_party/subtrees/dom-to-pptx \
  https://github.com/atharva9167j/dom-to-pptx.git master --squash
git am patches/*.patch
```

## Contents

| Path | Meaning |
|---|---|
| `h2p-integration.bundle` | branch `feat/h2p-bootstrap-implementation` (6 commits: subtree ×2 + port/fixtures/fix/docs) |
| `patches/000{1..4}-*.patch` | the 4 logical commits (apply after subtree add) |
| `h2p_integration_work_order_v0.1.md` | semantic comparison, structural set analysis, executed steps, verification, roadmap |
| `reports/deck.ab.json` | Layer A+B — pass, jaccard 1.0 ×3, media 1/1 |
| `reports/deck.d.json` | Layer D — pass, 19/19 ok, worstIoU 0.996 |
| `reports/deck.mapreport.json` | editabilityScore 1, 19 native / 0 fallback |
| `reports/deck.ir.json` / `deck.masks.json` | IR v1.2.0 instance + chart masks |
| `reports/deck.pptx` | final editable deliverable (normalizer-passed) |
| `reports/deck_diff-{1,2,3}.png` | Layer C pixel-diff evidence — 3.10 / 1.19 / 1.26 % (<5% gate) |

## Environment requirements (verified)

`pip3 install weasyprint` (69.0) · `npm ci` ·
`apt-get update && apt-get install -y poppler-utils fonts-noto-cjk libreoffice-impress`
(주의: `libreoffice-core`만으로는 pptx 로드 불가 — `-impress` 필수. apt 인덱스가
오래되면 404 → `update` 먼저.)

Smoke test: `bash run.sh fixtures/deck.html`
