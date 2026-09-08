# 数理化自学丛书（电子书重建版）

本仓库保存《数理化自学丛书》17 册的原始扫描 PDF、语义化 Markdown、扫描插图资源和可复现 EPUB3 构建工具。

## 电子书处理交流群

新建了一个电子书处理交流群，欢迎感兴趣的朋友加入，一起交流、学习和分享电子书及扫描版 PDF 的数字化处理经验：

**Telegram：** https://t.me/dzscl

群内会定期更新和发布扫描版 PDF 处理的数字工序、工具与相关镜像。也欢迎提供赞助 Token 或计算资源；赞助商名单会写入制作的作品，并在合适的位置进行介绍和推广。

## 赞助

本项目计算资源由 **交易猫实验室（TradeCat Labs）** 赞助。

**CA：** https://dexscreener.com/bsc/0x8a99b8d53eff6bc331af529af74ad267f3167777

## 收录书目

- 代数（第一至第四册）
- 平面三角
- 平面几何（第一、第二册）
- 平面解析几何
- 立体几何
- 化学（第一至第四册）
- 物理（第一至第四册）

作者元数据统一为“数理化自学丛书编委会”，电子书语言统一为 `zh-CN`。

## 仓库结构

```text
.
├── books/               # 电子书源文件区
│   ├── *.md             # 17 册规范正文源
│   └── assets/          # 4,875 个正文图片资源
├── raw/                 # 17 册原始扫描 PDF、导入哈希和资料说明
├── catalog.json         # 书目、合订分组、语言和稳定 UUID
├── epub/                # EPUB 样式、Lua 过滤器及 Pandoc 本地化数据
├── tex/                 # PDF 模板、合订封面与 TeX 宏包清单
├── scripts/             # 源文件审计、EPUB3 与 PDF 构建工具
├── docs/                # 来源、维护与已知问题说明
├── reports/             # 动态审计报告（JSON 不纳入版本控制）
└── dist/                # 构建出的 EPUB 与 PDF（不纳入版本控制）
```

Markdown 与 `books/assets/` 保持在同一源文件区，因此正文中的 `assets/...` 相对引用可直接解析；仓库根目录不放置单册电子书源文件。

## 构建

依赖：

- Python 3.10+
- Pandoc 3.1+
- GNU Make（可选）

原始 PDF 深度审计额外需要 PyPDF2 3.x、qpdf、Poppler（`pdfinfo`、`pdfdetach`、`pdfsig`、`pdftotext`）和 ExifTool。

重建 PDF 额外需要 XeLaTeX（TeX Live 2024 或 TinyTeX，含 ctex/fandol）以及合订装订用的 PyPDF2 3.x。首次可运行 `make tex-deps` 补齐宏包。

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

仅构建 EPUB：

```bash
make epub
```

构建 17 册分册 PDF 及三本学科合订 PDF：

```bash
make pdf
```

验证已有 EPUB：

```bash
make verify
```

验证已有重建 PDF：

```bash
make pdf-verify
```

构建单册：

```bash
python3 scripts/build_epubs.py --book '代数（第一册）'
python3 scripts/build_pdfs.py --book '代数（第一册）'
```

输出位于 `dist/`，报告位于 `reports/`。EPUB 构建器会检查 ZIP、XML、元数据、内部链接、图片替代文本、MathML 数量以及 EPUB3 nav/EPUB2 NCX 同步状态。同一源文件、同一 Pandoc 版本和同一 `SOURCE_DATE_EPOCH` 下，EPUB 输出字节可复现。PDF 使用 `ctexbook` + Fandol，同一 TeX Live 与同一 `SOURCE_DATE_EPOCH` 下内容稳定；跨 TeX 版本不保证字节级一致。

## Release 发布策略

从 `v2.0.0` 起，GitHub Release 只发布学科合订本，不再上传17本独立分册。当前合订产物为 EPUB 与重建 PDF：

- 数学（合订本）
- 物理学（合订本）
- 化学（合订本）

17册 Markdown、原始扫描 PDF、资源和单册 EPUB/PDF 构建能力继续保留在仓库中，作为合订本的可审计来源。既有 `v1.0.0`、`v1.1.0` Release 保留，不追溯删除。

## 发布前隐私审计

```bash
make privacy
make pre-push
```

推送门禁覆盖 Git 候选文件、路径跨平台兼容性、PNG 完整性与元数据、生成 EPUB、常见秘密格式、本机路径以及 Git 历史身份信息。详见 [`docs/PRIVACY.md`](docs/PRIVACY.md)。

## 当前源资产状态

- 原始扫描 PDF：17 册、5,927 页
- 规范 Markdown：17 册
- 图片资源：4,875 个
- 图片引用：4,878 次
- 缺失或孤立资源：0
- 已验证 EPUB MathML：88,653 个
- 空图片替代文本：0

《立体几何》原扫描第 49、50、55、56 页仍为空白；Markdown 和 EPUB 已依据另一份扫描逐页核对恢复，`raw/` 原字节未改动。详见 [`docs/KNOWN_ISSUES.md`](docs/KNOWN_ISSUES.md)。

## 权利说明

本仓库不对原著文字、版式或扫描图像授予新的版权许可。使用或再分发前，请自行确认适用地区的版权状态和授权条件。重建文件主要用于文献保存、校勘和个人研究。
