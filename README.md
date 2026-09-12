# 数理化自学丛书

本仓库以 TeX 为规范正文源，用 XeLaTeX 重排《数理化自学丛书》17 册，并保留原始扫描 PDF、Markdown 对照稿和扫描插图。

Markdown 正文最初来自 [tradecatlabs/shulihuazixuecongshu](https://github.com/tradecatlabs/shulihuazixuecongshu)。本仓库独立维护 TeX 与 PDF，不是该仓库的 fork，也不发布 EPUB。

> **尚未严格校对。** 当前 TeX 正文和由它生成的 PDF 仍可能含有转写、公式和版式错误。阅读、引用或教学时，建议优先使用 [`raw/`](raw/) 目录中的原始扫描 PDF。

## 收录书目

- 代数（第一至第四册）
- 平面三角
- 平面几何（第一、第二册）
- 平面解析几何
- 立体几何
- 化学（第一至第四册）
- 物理（第一至第四册）

作者元数据统一为“数理化自学丛书编委会”，语言统一为 `zh-CN`。

## 仓库结构

```text
.
├── tex/style/           # 版式：preamble 与分册 driver
├── tex/books/           # 17 册规范 TeX 正文（不含 documentclass）
├── tex/collections/     # 数学/物理学/化学合订本
├── tex/vendor/          # 构建检索路径上的宏包（如 multirow）
├── books/               # Markdown 对照稿（追踪上游）与插图
│   ├── *.md
│   └── assets/          # 4,875 个正文图片资源
├── raw/                 # 17 册原始扫描 PDF（优先阅读；Git LFS）、导入哈希和资料说明
├── catalog.json         # 书目、合订分组、语言和稳定 UUID
├── scripts/             # 源文件与隐私审计
├── docs/                # 来源、维护与已知问题说明
├── reports/             # 本地审计 JSON（不入库，运行 make audit 后出现）
└── dist/                # 构建出的 PDF（不入库）
```

规范正文在 `tex/books/`，版式在 `tex/style/`。`books/*.md` 仅用于对照上游 Markdown，不经 Pandoc 转写。图片由 TeX 通过 `books/assets/` 引用。

## 构建

依赖：

- GNU Make
- XeLaTeX / CTeX（TeX Live 或 TinyTeX，含 fandol）

源文件与隐私审计仍用 Python 3.10+。原始 PDF 深度审计额外需要 PyPDF2 3.x。首次可运行 `make tex-deps` 补齐宏包。

完整审计并构建：

```bash
make all
```

仅审计源文件：

```bash
make audit
```

审计17份原始扫描 PDF 的哈希、结构、附件、主动内容和隐私元数据：

```bash
make pdf-audit
```

从 TeX 源构建 17 册分册 PDF 及三本学科合订 PDF：

```bash
make pdf
```

验证已有重建 PDF：

```bash
make pdf-verify
```

构建单册：

```bash
make dist/代数（第一册）.pdf
```

输出位于 `dist/`。PDF 使用 `ctexbook` + Fandol。合订本由 `tex/collections/` 经 XeLaTeX 编译，页码连续。

## Release 发布策略

默认分支为 `master`。GitHub Release 只发布数学、物理学、化学三本学科合订 PDF，不上传 17 本独立分册。本仓库不构建、不发布 EPUB。

## 发布前隐私审计

```bash
make privacy
make pre-push
```

推送门禁覆盖 Git 候选文件、路径跨平台兼容性、PNG 完整性与元数据、常见秘密格式、本机路径以及 Git 历史身份信息。详见 [`docs/PRIVACY.md`](docs/PRIVACY.md)。

## 当前源资产状态

- 原始扫描 PDF：17 册、5,927 页
- 规范 TeX：17 册
- Markdown 对照稿：17 册
- 图片资源：4,875 个
- 图片引用：4,878 次
- 缺失或孤立资源：0
- 空图片替代文本：0

《立体几何》原扫描第 49、50、55、56 页仍为空白；对照用 Markdown 已依据另一份扫描逐页核对恢复，`raw/` 原字节未改动。详见 [`docs/KNOWN_ISSUES.md`](docs/KNOWN_ISSUES.md)。

## 权利说明

本仓库不对原著文字、版式或扫描图像授予新的版权许可。使用或再分发前，请自行确认适用地区的版权状态和授权条件。重建文件主要用于文献保存、校勘和个人研究。
