# PDF 构建使用 POSIX shell + XeLaTeX（TinyTeX/CTeX）。不支持 Windows cmd。
# Python 仅用于审计，不参与出书。

PYTHON ?= python3
AUTHOR := 数理化自学丛书编委会
SOURCE_DATE_EPOCH ?= 1787875200
export SOURCE_DATE_EPOCH
export FORCE_SOURCE_DATE = 1
export TZ = UTC

XELATEX := xelatex -interaction=nonstopmode -file-line-error
GS := gs -dBATCH -dNOPAUSE -dSAFER -q -sDEVICE=pdfwrite

BOOKS := \
	代数（第一册） \
	代数（第二册） \
	代数（第三册） \
	代数（第四册） \
	平面三角 \
	平面几何（第一册） \
	平面几何（第二册） \
	平面解析几何 \
	立体几何 \
	化学（第一册） \
	化学（第二册） \
	化学（第三册） \
	化学（第四册） \
	物理（第一册） \
	物理（第二册） \
	物理（第三册） \
	物理（第四册）

MATH_BOOKS := \
	代数（第一册） \
	代数（第二册） \
	代数（第三册） \
	代数（第四册） \
	平面三角 \
	平面几何（第一册） \
	平面几何（第二册） \
	平面解析几何 \
	立体几何

PHYSICS_BOOKS := \
	物理（第一册） \
	物理（第二册） \
	物理（第三册） \
	物理（第四册）

CHEMISTRY_BOOKS := \
	化学（第一册） \
	化学（第二册） \
	化学（第三册） \
	化学（第四册）

VOLUME_PDFS := $(addprefix dist/,$(addsuffix .pdf,$(BOOKS)))
MATH_PDFS := $(addprefix dist/,$(addsuffix .pdf,$(MATH_BOOKS)))
PHYSICS_PDFS := $(addprefix dist/,$(addsuffix .pdf,$(PHYSICS_BOOKS)))
CHEMISTRY_PDFS := $(addprefix dist/,$(addsuffix .pdf,$(CHEMISTRY_BOOKS)))

.PHONY: all audit pdf-audit repository privacy pdf volumes collections \
	pdf-verify tex-deps tex-audit verify pre-push clean

all: audit tex-audit

audit:
	$(PYTHON) scripts/audit_sources.py
	$(PYTHON) scripts/audit_chinese_variants.py

tex-audit:
	$(PYTHON) scripts/audit_tex_sources.py

pdf-audit:
	$(PYTHON) scripts/audit_pdfs.py

repository:
	$(PYTHON) scripts/audit_repository.py

privacy:
	$(PYTHON) scripts/audit_privacy.py

pdf: volumes collections

volumes: $(VOLUME_PDFS)

collections: \
	dist/数学（合订本）.pdf \
	dist/物理学（合订本）.pdf \
	dist/化学（合订本）.pdf

dist/%.pdf: tex/books/%.tex tex/style/preamble.tex tex/style/driver.tex
	@mkdir -p dist .build/pdf/$*
	sed \
		-e 's/BOOKTITLE/$*/g' \
		-e 's/BOOKAUTHOR/$(AUTHOR)/g' \
		-e 's|BOOKCONTENT|tex/books/$*.tex|g' \
		tex/style/driver.tex > .build/pdf/$*/book.tex
	-$(XELATEX) -output-directory=.build/pdf/$* .build/pdf/$*/book.tex
	-$(XELATEX) -output-directory=.build/pdf/$* .build/pdf/$*/book.tex
	-$(XELATEX) -output-directory=.build/pdf/$* .build/pdf/$*/book.tex
	@test -s .build/pdf/$*/book.pdf
	cp -f .build/pdf/$*/book.pdf $@

.build/pdf/covers/%.pdf: tex/cover.tex
	@mkdir -p .build/pdf/covers
	sed \
		-e 's/COVER_TITLE/$*/g' \
		-e 's/COVER_AUTHOR/$(AUTHOR)/g' \
		tex/cover.tex > .build/pdf/covers/$*.tex
	-$(XELATEX) -output-directory=.build/pdf/covers .build/pdf/covers/$*.tex
	@test -s $@

dist/数学（合订本）.pdf: .build/pdf/covers/数学（合订本）.pdf $(MATH_PDFS)
	@mkdir -p dist
	$(GS) -sOutputFile=$@ .build/pdf/covers/数学（合订本）.pdf $(MATH_PDFS)
	ln -sf '数学（合订本）.pdf' dist/mathematics-collected.pdf

dist/物理学（合订本）.pdf: .build/pdf/covers/物理学（合订本）.pdf $(PHYSICS_PDFS)
	@mkdir -p dist
	$(GS) -sOutputFile=$@ .build/pdf/covers/物理学（合订本）.pdf $(PHYSICS_PDFS)
	ln -sf '物理学（合订本）.pdf' dist/physics-collected.pdf

dist/化学（合订本）.pdf: .build/pdf/covers/化学（合订本）.pdf $(CHEMISTRY_PDFS)
	@mkdir -p dist
	$(GS) -sOutputFile=$@ .build/pdf/covers/化学（合订本）.pdf $(CHEMISTRY_PDFS)
	ln -sf '化学（合订本）.pdf' dist/chemistry-collected.pdf

pdf-verify: $(VOLUME_PDFS) dist/数学（合订本）.pdf dist/物理学（合订本）.pdf dist/化学（合订本）.pdf
	@ok=0; \
	for f in $^; do \
		if [ ! -s "$$f" ]; then echo "ERROR: 缺少 $$f"; ok=1; continue; fi; \
		if ! dd if="$$f" bs=5 count=1 2>/dev/null | grep -q '%PDF-'; then \
			echo "ERROR: 不是 PDF：$$f"; ok=1; \
		fi; \
	done; \
	if [ "$$ok" -ne 0 ]; then exit 1; fi; \
	echo "pdf-verify: $(words $^) files OK"

verify: pdf-verify

tex-deps:
	@echo "TinyTeX/TeX Live 年份必须与仓库一致（本机为 2024）。当前 CTAN 为更新年份时，请改用 historic tlnet，例如："
	@echo "  tlmgr install --repository https://ftp.math.utah.edu/pub/tex/historic/systems/texlive/2024/tlnet-final \\"
	@echo "    \$$(grep -v '^[[:space:]]*#' tex/packages.txt | grep -v '^[[:space:]]*$$')"
	tlmgr install $$(grep -v '^[[:space:]]*#' tex/packages.txt | grep -v '^[[:space:]]*$$')

pre-push: audit tex-audit pdf-audit repository privacy pdf-verify

clean:
	rm -rf .build dist reports/*.json
