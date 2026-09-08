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
- 已有 Git 提交中的非 GitHub noreply 邮箱和历史补丁

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

## 本次结果

- 未发现本机绝对路径、用户目录、用户名或主机名
- 未发现电子邮箱、私人网络地址或凭据 URL
- 未发现 API Key、访问令牌、密码或私钥
- 未发现手机号码或身份证号码样式
- 4,875 个 PNG 仅含 `IHDR`、`IDAT`、`IEND`，无 EXIF、文本、GPS、软件或时间元数据
- 17份原始 PDF（5,927页）无加密、附件、批注、主动脚本、表单数据或隐私模式命中
- 17 个生成 EPUB 的文本条目未发现本机或秘密信息
- 无符号链接；已配置的 Git 远端不含内嵌凭据；初始提交历史审计通过

`catalog.json` 中的 UUID 是电子书公开标识符，不是设备 UUID。EPUB 中的 Pandoc 生成器名称是公开软件信息，不包含设备或账户数据。

## GitHub 身份建议

本仓库提交邮箱已使用 GitHub noreply 地址。后续维护者提交前仍应确认身份配置，并再次运行 `make pre-push`。本地 `.git/config` 不会被推送，但提交作者邮箱会进入永久 Git 历史。
