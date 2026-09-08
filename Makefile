PYTHON ?= $(shell test -x "$(CURDIR)/.venv/bin/python" && echo "$(CURDIR)/.venv/bin/python" || echo python3)

.PHONY: all audit pdf-audit repository privacy pdf pdf-tex pdf-verify tex-deps tex-audit verify pre-push clean

all: audit tex-audit

audit:
	$(PYTHON) scripts/audit_sources.py
	$(PYTHON) scripts/audit_chinese_variants.py

pdf-audit:
	$(PYTHON) scripts/audit_pdfs.py

repository:
	$(PYTHON) scripts/audit_repository.py

privacy:
	$(PYTHON) scripts/audit_privacy.py

pdf:
	$(PYTHON) scripts/build_pdfs.py

pdf-tex:
	$(PYTHON) scripts/build_pdfs.py

pdf-verify:
	$(PYTHON) scripts/build_pdfs.py --verify-only

tex-audit:
	$(PYTHON) scripts/audit_tex_sources.py

tex-deps:
	@echo "TinyTeX/TeX Live 年份必须与仓库一致（本机为 2024）。当前 CTAN 为更新年份时，请改用 historic tlnet，例如："
	@echo "  tlmgr install --repository https://ftp.math.utah.edu/pub/tex/historic/systems/texlive/2024/tlnet-final \\"
	@echo "    \$$(grep -v '^[[:space:]]*#' tex/packages.txt | grep -v '^[[:space:]]*$$')"
	tlmgr install $$(grep -v '^[[:space:]]*#' tex/packages.txt | grep -v '^[[:space:]]*$$')

verify:
	$(PYTHON) scripts/build_pdfs.py --verify-only

pre-push: audit tex-audit pdf-audit repository privacy verify

clean:
	rm -rf .build dist reports/*.json
