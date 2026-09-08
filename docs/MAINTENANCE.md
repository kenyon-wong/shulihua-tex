# 维护流程

## 修改正文或资源

1. 在仓库外建立带时间戳的备份。
2. 只做可由扫描、上下文、量纲或书后答案支持的高置信修正。
3. 新增或替换图片时提供真实描述性的替代文本。
4. 不移动 `books/assets/`，除非同步更新所有 Markdown 引用。
5. 运行 `make audit`。
6. 运行 `make audit` 与 `make tex-audit`。
7. 运行 `make pdf` 与 `make pdf-verify`。

图片疑似为习题标题、练习标题、页眉或其他纯文字卡片时，不得直接删除；先对照 `raw/` 原扫描相邻页和正文上下文再决定。

中文繁简或异体修订不得整库盲转。必须先生成仓库外候选，保留公式、HTML、链接目标和图片引用；低频或上下文相关字形应对照原PDF。`make audit` 中的 `audit_chinese_variants.py` 用于阻止已确认繁体、日文新字形、旧异体和“反覆”回归。

## 原始 PDF

`raw/*.pdf` 是校勘来源资料，不是规范正文，由 Git LFS 存储。新增或替换时：

1. 先在仓库外备份，并确认书名与 `catalog.json` 一致；
2. 保持导入原字节，不用办公软件另存；
3. 确认本机已 `git lfs install`，再 `git add` 该 PDF（应生成 LFS 指针，而不是把整份 PDF 当普通 blob）；
4. 更新 `raw/SHA256SUMS.txt`；
5. 运行 `make pdf-audit`，确认 qpdf、附件、主动内容、元数据和隐私门禁17/17通过；
6. 运行 `make repository privacy`，复核 GitHub 文件大小及公开候选范围。

细则见 [`GIT.md`](GIT.md)。

## 元数据

书目顺序、题名、语言和稳定 UUID 统一维护在 `catalog.json`。不要因普通正文修订更换 UUID；只有确认电子书身份发生变化时才调整。

## 公式

本分支 PDF 由 GNU Make 调用 XeLaTeX/CTeX（TinyTeX）从 `tex/style` + `tex/books` 构建，不经过 Pandoc 或 Python。不要对公式区域执行全角标点替换。修改公式后抽检对应 PDF 页。Markdown 只作对照，上游更新应手工或按章并入 TeX 正文。

## PDF

规范正文是 `tex/books/`，版式是 `tex/style/`。

1. 分册：`make dist/代数（第一册）.pdf` 或 `make volumes`；
2. 合订本：`make collections`，用 Ghostscript 按 Makefile 中的书目顺序装订，页码按册重起；
3. 中文字体固定为 TeX Live / TinyTeX 自带的 Fandol，不要改用本机系统字体；
4. 缺少宏包时运行 `make tex-deps`。

## Release 发布

从 `v2.0.0` 起执行以下固定策略：

1. Release 只上传数学、物理学、化学三本学科合订 PDF，不上传 17 本独立分册；
2. 本仓库不构建、不发布 EPUB；
3. 允许同时上传 `SHA256SUMS.txt`、发布清单等验证附件；
4. 发布前必须通过 `make audit`、`make tex-audit`、`make pdf-verify` 和 `make privacy`；
5. 既有 Release 保留，不覆盖、不追溯删除。

## 生成物

- `.build/`：XeLaTeX 工作目录
- `dist/`：PDF 输出
- `reports/*.json`：动态审计结果

以上内容均由脚本重建，不纳入版本控制。
