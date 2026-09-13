# 隐私与发布前审计

## 审计范围

发布前隐私脚本会检查：

- Git 实际会纳入的已跟踪及未忽略文件
- 本机用户目录、Windows/WSL 绝对路径、用户名和主机名
- 电子邮箱、内网/回环地址及带凭据 URL
- 常见 API Key、访问令牌、密码赋值和私钥头
- 中国大陆手机号码及身份证号码样式
- `.env`、私钥、凭据库等敏感文件名
- 绝对路径符号链接
- PNG 文本、EXIF、时间及其他隐私元数据块
- `raw/` 中 PDF 的哈希、XMP/Info 元数据、附件、批注、表单、JavaScript与其他主动内容
- `dist/` 中如仍有 EPUB，扫描其文本型 ZIP 条目；本分支默认只生成 PDF
- 仅扫描尚未推送提交的新增行（`+`）；已在 `origin/master` 上的历史补丁和作者邮箱不作为失败项
- SSH 形如 `git@github.com:...` 以及 `tex/vendor/` 里许可证/宏包公开邮箱不作为失败项

运行：

```bash
make pdf-audit
make privacy
```

完整推送前门禁：

```bash
make pre-push
```

机器可读报告写入 `reports/privacy-audit.json`，该报告被 `.gitignore` 排除。

## 工作区门禁（当前树）

以 `make privacy` 为准，不把过期快照当规范：

- 扫描 Git 将纳入的已跟踪及未忽略文件（不含 `.agents/`）
- PNG 只允许 `IHDR`/`IDAT`/`IEND` 一类块
- `raw/*.pdf` 的结构与主动内容由 `make pdf-audit` 检查
- `catalog.json` 中的 UUID 是书目公开标识符，不是设备 UUID

## GitHub 身份建议

既有提交历史使用个人邮箱，不改写。新提交建议改用 GitHub noreply；本地 `.git/config` 不会被推送，但作者邮箱会进入永久 Git 历史。推送前运行 `make pre-push`。
