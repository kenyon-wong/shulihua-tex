# 校对管线

本仓库的校对分三层：**自动格式门禁**（构建日志）、**自动对照信号**（TeX vs 上游
Markdown / 图号连续性）、**人工内容校对**（对照 `raw/` 印刷页）。三层共用
`proof/ledger/` 台账跟踪状态；`reports/` 下的 JSON 是一次性审计输出，不入库。

## 1. 构建日志审计（格式层）

```sh
make pdf          # 产出 .build/pdf/*/book.log
make log-audit    # 解析日志，报告写入 reports/build-log-audit.json
```

分级（`--warn-pt` / `--error-pt` 可覆盖，默认 2 / 10）：

| 信号 | 级别 | 说明 |
| --- | --- | --- |
| Overfull ≥ 10pt | 错误 | 版心外出血，须修（压表、断行、缩排） |
| Overfull 2–10pt | 警告 | 酌情修 |
| Missing character | 错误 | 缺字：正文字体或 nullfont 中排入了不存在的字符 |
| 未定义引用 / 重复标签 / 重复锚点 | 错误 | 交叉引用问题 |
| 日志早于 TeX 源 | 警告 | 先 `make pdf` 再审 |

合订本日志会聚合各分册内容，行号仍相对分册源文件，报告里已注明。
合订本是否陈旧只对照该合订所含分册和版式，不拿 17 册全集。

定位技巧：`Missing character` 找不到出处时，在 `.build/pdf/<册>/book.tex`
的 `\input{tex/style/driver.tex}` 前加一行 `\tracinglostchars=3` 重编，
缺字会升级为带源文件行号的错误。

版式手段（不改公式内容）：

- 跨页表：把过宽的 `l` 列改成 `p{…}`，必要时 `\small` 收 `\tabcolsep`。
  `longtable` 要 XeLaTeX 三遍后才稳定；头脚行在第一遍常虚报 Overflow。
- 单页宽盒/宽公式：用 preamble 的 `\fitblock{…}`（只按栏宽缩小）。
  `longtable` 不能放进盒子，勿套 `\fitblock`。

## 2. 结构对照（信号层）

```sh
make crosscheck   # 报告写入 reports/crosscheck-audit.json
```

- **章节目次**：`tex/books/*.tex` 的 `\chapter/\section/\subsection` 与
  `books/*.md` 的 `##/###/####` 按 difflib 对齐，归一化 LaTeX 记号
  （`------`→`——`、`` ``…'' ``→`“…”`、`\texorpdfstring`、脚注标记等）。
- **图号**：按册提取 `\caption{图X·Y}`，检查重号、章内跳号；正文引用的
  连接符与该册体例（`·` 或 `.`）不一致时给出行号。
- 已知豁免：`audit_crosscheck.py` 内 `KNOWN_FIG_GAPS`（如《立体几何》
  原扫描缺页恢复区的编号缺口）。

**本层只产生 WARN，不当门禁**：Markdown 是上游 OCR 产物，自身有错漏；
一切内容疑点以 `raw/` 印刷页为准。`--strict` 可临时升为门禁。

## 3. 人工内容校对（内容层）

逐册逐章执行，每章一轮：

1. 打开 `raw/<册名>.pdf` 找到对应印刷页区间（以章首页码为准）。
2. 与 `make dist/<册名>.pdf` 的成品页逐项核对：
   - 段落完整性（有无漏段、并段、重复段）；
   - 公式的系数、符号、上下标；
   - 题号顺序与分段（`enumerate` 的 `start`）；
   - 图号、图题与图形的标注/拓扑（不要求像素级一致）；
   - 答案数值（书后习题答案章）。
3. 每个疑点在台账立行，状态只能取：`待核`、`已修`、`误报`、`存疑校注`、`不修`。
4. 修正遵守 [MAINTENANCE.md](MAINTENANCE.md)：先在仓库外备份；只做扫描、
   上下文、量纲或书后答案支持的高置信修正；证据不足时用 quote 透明校注，
   不凭空补写。
5. 修完跑 `make audit && make tex-audit && make log-audit`，重建该册 PDF
   复审对应页，再提交并在台账回填 commit。

## 4. 台账 `proof/ledger/`

TSV 格式（内容含中文逗号，故用制表符分隔），**入版本控制**：

| 列 | 说明 |
| --- | --- |
| id | `册名-序号`，全局唯一 |
| 册 | catalog.json 题名 |
| 章 | 章名或章号 |
| raw页 | `raw/` 印刷页码或页区间 |
| tex行 | `tex/books/<册>.tex` 行号（或行区间） |
| 类型 | 溢出 / 缺字 / 图号重复 / 图号跳号 / 标题差异 / 内容疑误 / 连接符 / … |
| 严重度 | pt 数（溢出）或 高 / 中 / 低 |
| 描述 | 一句话 |
| 状态 | 待核 / 已修 / 误报 / 存疑校注 / 不修 |
| 证据 | raw 页码、上下文、量纲依据等 |
| commit | 处置提交（修复或关闭时回填） |

台账同时是覆盖度地图：某章校对完成即其行全部离开 `待核`。

## 5. 门禁晋升（P4，暂缓）

`log-audit` 当前为独立目标，**不在** `make pre-push` 内。当现有错误级
溢出清零、连续两个发布周期无新增后，再把它并入 `pre-push`。`crosscheck`
保持 advisory，不晋升。
