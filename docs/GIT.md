# Git 与 Git LFS

本分支默认按 Unix 检出。克隆后先安装 Git LFS，再拉文件。

```bash
git lfs install
git clone https://github.com/kenyon-wong/shulihua-tex.git
# 若已经 clone 过但没装 LFS：
git lfs install
git lfs pull
```

## 什么进 LFS

| 路径 | 方式 | 原因 |
|------|------|------|
| `raw/*.pdf` | Git LFS | 17 份扫描，单文件最大约 32MB，合计约 129MB，几乎不改 |
| `books/assets/*.png` | 普通 Git | 约 4875 张，中位约 1KB，LFS 指针开销更大 |
| `tex/**/*.tex`、`books/*.md` | 普通 Git 文本 | 规范正文和上游对照稿 |

不要把 `*.png` 或 `tex/` 配进 LFS。不要对已有历史做 `git lfs migrate import`（会改写提交）。

当前提交起，`raw/*.pdf` 以 LFS 指针入库；更早的 `main` 祖先提交里仍是完整 blob。

## 换行与可执行位

- 文本统一 LF（`.gitattributes` 的 `eol=lf`）。
- 不要给 `.py` 加可执行位，除非它是入口脚本且确有需要。
- 不要提交 `.DS_Store`、`.build/`、`dist/`、XeLaTeX 的 `.aux/.log/.toc`。

## 推送

`raw/*.pdf` 走 LFS 上传。没有 `git lfs install` 时，push 可能把指针当普通文本推上去，克隆端会拿到几十字节的 pointer 而不是 PDF。

`origin` 保持 SSH：`git@github.com:kenyon-wong/shulihua-tex.git`。不要改成 HTTPS 再 push，LFS 仍会走 `lfs.github.com`，还可能弹出用户名密码。

本仓库本地已关闭 LFS file locking 校验，并把并发降到 3、加长 TLS/拨号超时。全局 `~/.gitconfig` 里 `lfs.tlstimeout 3`、`lfs.transfer.maxretries 1` 是给内网 git 用的，对着 GitHub 会握手超时。

若上传到 16/17 后报 S3 `EOF` 或 `TLS handshake timeout`，已经成功的对象会留在远端，直接重试即可：

```bash
git lfs push origin master
git push -u origin master
```

## 远程与分支（独立维护 TeX，不向上游推送）

| 远程 | URL | 用途 |
|------|-----|------|
| `origin` | `https://github.com/kenyon-wong/shulihua-tex.git` | 独立仓库，**唯一允许 push 的地方** |
| `upstream` | `https://github.com/tradecatlabs/shulihuazixuecongshu.git` | Markdown/EPUB 源仓库，**只 fetch，禁止 push** |

| 分支 | 跟踪 | 用途 |
|------|------|------|
| `master` | `origin/master` | TeX 规范源、Makefile 出 PDF |

本仓库不保留 `main`。对照上游 Markdown 时直接用 `upstream/main`，不要在本地再建跟踪分支，也不要把 `upstream/main` 合并进 `master`。上游会带回 EPUB、Pandoc 和另一套目录约定，和本分支冲突。

旧 fork `kenyon-wong/shulihuazixuecongshu` 仍在 GitHub 的 fork 网络里。GitHub **禁止向公开 fork 上传新的 LFS 对象**，不要再向那个地址 push。

### 日常拉上游 Markdown

```bash
git fetch upstream
git diff upstream/main -- books/
```

确认 diff 后，只把 Markdown（以及新增/改动的插图）接到 `master`，再手工改对应 `tex/books/*.tex`：

```bash
git checkout master
git checkout upstream/main -- books/
# 审阅 git diff --cached -- books/
# 把内容改动写入 tex/books/<书名>.tex，不要用 Pandoc 整册重转
git add books/ tex/books/
git commit
git push origin master
```

插图有增删时，同步更新 `tex/` 里的 `\includegraphics`。不要 `git merge upstream/main`。不要改 `tradecatlabs/shulihuazixuecongshu` 的默认分支，也不要向它 `git push`。
