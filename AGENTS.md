# 仓库维护约定（TeX 规范源分支）

本分支名固定为 `master`，推送到独立仓库 `origin`（`kenyon-wong/shulihua-tex`）。`upstream` 是 tradecatlabs 的 Markdown/EPUB 仓库，只允许 `git fetch`，禁止 push、发 PR、改其默认分支。不要在本地或 `origin` 保留 `main`；对照上游时用 `upstream/main`。不要把 `upstream/main` 合并进 `master`。详见 `docs/GIT.md`。

- 规范正文源是 `tex/books/` 下与 `catalog.json` 17 册题名对应的内容 `.tex`（不含 `\documentclass`）。版式只放在 `tex/style/`。`books/*.md` 保留作上游对照，不以 Markdown 出书，也不用 Pandoc 转 TeX。
- `raw/` 只保存 17 册原始扫描 PDF 及 `SHA256SUMS.txt`，保持导入原字节，不改写。`raw/*.pdf` 必须走 Git LFS（见 `docs/GIT.md`）；不要把 PNG 或 `.tex` 配进 LFS。
- `books/assets/` 中的 PNG 在被 TikZ/SVG/`tabular` 替换并通过对照验收之前必须保留；不得在替换完成前删除。
- 图的验收对照 `raw/` 印刷版面：标注、拓扑和比例一致即可。不要追求与扫描 PNG 像素级一致。PDF 成品不再用扫描 PNG；照片/网纹改为示意图或插画；原 PNG 留在 books/assets 作对照。
- 不凭空补写原扫描缺失内容；证据不足时保留透明校注。
- 公式内容不得经过会破坏 LaTeX 的全角标点替换。
- 批量修改前先在仓库外建立备份；不得执行破坏工作区或 Git 历史的操作。
- 提交前运行 `make audit` 和 `make tex-audit`；构建 PDF 用 `make pdf`（GNU Make + XeLaTeX，不经 Python/Pandoc）。单册：`make dist/代数（第一册）.pdf`。
- `dist/`、`.build/` 和动态 JSON 报告属于生成物，不纳入版本控制。
- 本分支不维护 EPUB，不保留 `epub/` 与 `scripts/build_epubs.py`。
