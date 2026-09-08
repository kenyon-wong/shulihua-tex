# Git 与 Git LFS

本分支默认按 Unix 检出。克隆后先安装 Git LFS，再拉文件。

```bash
git lfs install
git clone <url>
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

## 远程与分支（独立维护 TeX，不向上游推送）

| 远程 | URL | 用途 |
|------|-----|------|
| `origin` | `git@github.com:kenyon-wong/shulihuazixuecongshu.git` | 自己的 fork，**唯一允许 push 的地方** |
| `upstream` | `https://github.com/tradecatlabs/shulihuazixuecongshu.git` | 原作者仓库，**只 fetch，禁止 push** |

| 分支 | 跟踪 | 用途 |
|------|------|------|
| `master` | `origin/master` | TeX 规范源、Makefile 出 PDF。独立维护，不向 `upstream` 发 PR |
| `main` | `upstream/main` | 上游 Markdown/EPUB 的只读镜像，只允许快进 |

不要把 `main` 合并进 `master`。上游会带回 EPUB、Pandoc 和另一套目录约定，和本分支冲突。

### 日常拉上游 Markdown

```bash
git fetch upstream
git checkout main
git merge --ff-only upstream/main
git checkout master
git diff main -- books/
```

确认 diff 后，只把 Markdown（以及新增/改动的插图）接到 `master`，再手工改对应 `tex/books/*.tex`：

```bash
git checkout master
git checkout main -- books/
# 审阅 git diff --cached -- books/
# 把内容改动写入 tex/books/<书名>.tex，不要用 Pandoc 整册重转
git add books/ tex/books/
git commit
git push origin master
```

插图有增删时，同步更新 `tex/` 里的 `\includegraphics`。不要 `git merge main`。

### 首次把本机推到自己的仓库

GitHub **禁止向公开 fork 上传新的 LFS 对象**（会报 `can not upload new objects to public fork`）。`raw/*.pdf` 已走 LFS，因此不能把 `master` 推到「Fork」出来的仓库。

可选其一：

1. **推荐：** 在 GitHub 新建一个**独立仓库**（不要点 Fork），或在现有 fork 的 Settings 里脱离 fork 网络，再：

```bash
git lfs install
git push -u origin master
```

2. 若必须保留 Fork 关系：不要用 LFS，把 `raw/*.pdf` 改回普通 Git 对象（单文件均小于 GitHub 100MB 限制）。独立维护 TeX 时不推荐这条。

推上去之后，把 **kenyon-wong** 那个仓库的默认分支设为 `master`。不要改 `tradecatlabs/shulihuazixuecongshu` 的默认分支，也不要向它 `git push`。
