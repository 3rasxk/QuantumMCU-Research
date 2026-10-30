# make paper-figures : rebuild every paper figure, table and docs/phase4_report.md from data/raw (read-only)
PY ?= .venv/bin/python

.PHONY: paper-figures paper-figures-full test
paper-figures:
	$(PY) analysis/reproduce.py

paper-figures-full:
	$(PY) analysis/reproduce.py --full

test:
	@for f in $$(git ls-files '*_test.py'); do $(PY) $$f > /dev/null 2>&1 && echo "ok   $$f" || echo "FAIL $$f"; done
