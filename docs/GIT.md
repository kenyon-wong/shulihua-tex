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
