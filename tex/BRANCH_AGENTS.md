# 仓库维护约定（TeX 规范源分支）

本分支名固定为 `master`。GitHub 默认分支仍是 `main`；不要把 `master` 设为默认分支，不要 force-push `main`。

- 规范正文源是 `tex/books/` 下与 `catalog.json` 17 册题名对应的 `.tex` 文件。`books/*.md` 保留，仅作对照 `main` / 上游更新的镜像，不以 Markdown 出书。上游 Markdown 有更新时，在本分支运行 `make md-to-tex` 再审阅 TeX。
- `raw/` 只保存 17 册原始扫描 PDF 及 `SHA256SUMS.txt`，保持导入原字节，不改写。
- `books/assets/` 中的 PNG 在被 TikZ/SVG/`tabular` 替换并通过对照验收之前必须保留；不得在替换完成前删除。
- 图的验收对照 `raw/` 印刷版面：标注、拓扑和比例一致即可。不要追求与扫描 PNG 像素级一致。照片、网纹图和复杂阴影图保持 PNG。
- 不凭空补写原扫描缺失内容；证据不足时保留透明校注。
- 公式内容不得经过会破坏 LaTeX 的全角标点替换。
- 批量修改前先在仓库外建立备份；不得执行破坏 `main` 工作区或 Git 历史的操作。
- 提交前运行 `make audit` 和 `make tex-audit`；构建 PDF 用 `make pdf`（从 TeX 源）。
- `dist/`、`.build/` 和动态 JSON 报告属于生成物，不纳入版本控制。
- 本分支不维护 EPUB，不保留 `epub/` 与 `scripts/build_epubs.py`。
