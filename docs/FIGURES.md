# 插图替换（四轨）

本任务要把 `tex/books` 里仍通过 `\includegraphics` 引用的扫描 PNG 全部换掉，直到这些正文不再包含 `books/assets` 下的 PNG。四条轨并行，T 优先。本文和 `docs/figures-inventory.tsv` 只是开工清单，不是终审；不要把某一轨当成已经对照 `raw/` 验收过。

原扫描 PNG 留在 `books/assets/` 作对照，永不删除，也不要把重绘结果写回该目录。

## 四轨

- **T**：改成 TikZ、`tabular` 或正文散文，写进该书 `tex/books/*.tex`。优先做这一轨。
- **V**：独立矢量 PDF，放在 `tex/figures/<asset_dir>/`，文件名主干与原 PNG 相同。正文仍用 `\fitfig{\includegraphics...}`。
- **R**：重绘插画，PDF 或新 PNG，放在 `tex/figures/`，不要写回 `books/assets`。
- **P**：照片或网纹，重画成教学示意图，通常最后落到 V 或 R。不要对原照片做超分辨率。

## 引用约定（唯一）

Makefile 在仓库根目录启动 XeLaTeX，工作目录是仓库根，不是 `.build/`：

```text
xelatex -output-directory=.build/pdf/<书名> .build/pdf/<书名>/book.tex
```

`tex/style/driver.tex` 先 `\input{tex/style/preamble.tex}`，再 `\input` 对应的 `tex/books/<书名>.tex`。当前 `preamble.tex` 只有 `\graphicspath{{books/}}`，所以正文里的 `assets/<asset_dir>/<file>.png` 解析为 `books/assets/<asset_dir>/<file>.png`。本任务不改 preamble。

V/R/P 成品只放这里：

```text
tex/figures/<asset_dir>/<stem>.pdf
```

`<asset_dir>` 与 `books/assets` 下的目录名相同（如 `plane-geometry-1`）。`<stem>` 与原文件名去掉扩展名后相同（如 `fig-p0011-01`）。R 若暂时仍是栅格，用同目录 `<stem>.png`，引用方式相同。

扫描 PNG 继续写 `assets/<asset_dir>/<file>.png`。V/R/P 正文仍包在 `\fitfig` 里，引用写成不含 `assets/` 的目录名：

```tex
\fitfig{\includegraphics[keepaspectratio,alt={...}]{<asset_dir>/<stem>.pdf}}
```

`{{books/}}` 现在找不到 `tex/figures/`。首张 V 图落地时，再把检索路径加上 `tex/figures/`（不要在此之前改 preamble）：

```tex
\graphicspath{{books/}{tex/figures/}}
```

这样 `<asset_dir>/<stem>.pdf` 先试 `books/<asset_dir>/...`（没有），再命中 `tex/figures/<asset_dir>/<stem>.pdf`。扫描 PNG 仍命中 `books/assets/`。不要用 `../tex/figures/...`，也不要另写一套相对 `.build/pdf/<书名>/` 的路径。

## 验收

对照 `raw/` 印刷页：页码标注、拓扑和比例一致即可。不要求与扫描 PNG 像素级一致。

## 清单

`docs/figures-inventory.tsv` 由 `scripts/classify_figures.py` 生成。`track` 是初分，不是定论，对照 `raw/` 后可以改轨。`status` 只用：

- `pending`：尚未替换
- `replaced`：已替换，且不再引用该扫描 PNG
- `failed`：试过但未通过对照
- `deferred`：仅在有用户书面同意时使用

不要声称这些图已经严格校对。
