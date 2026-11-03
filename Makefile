# make paper-figures : rebuild every paper figure, table and docs/phase4_report.md from data/raw (read-only)
PY ?= .venv/bin/python

.PHONY: paper-figures paper-figures-full test
paper-figures:
	$(PY) analysis/reproduce.py

paper-figures-full:
	$(PY) analysis/reproduce.py --full

test:
	@for f in $$(git ls-files '*_test.py'); do $(PY) $$f > /dev/null 2>&1 && echo "ok   $$f" || echo "FAIL $$f"; done

# make paper : numbers.tex and tables from the derived CSVs, link F1-F5 from figures/phase4, build paper/main.pdf (latexmk, else tectonic)
.PHONY: paper paper-numbers paper-figs
paper-numbers:
	$(PY) analysis/paper/make_numbers.py

paper-figs:
	@mkdir -p paper/figures
	@for f in F2_parity F3_memory_wall F4_crossover_by_circuit F5_phase1_accuracy F6_decision_map; do ln -sf ../../figures/phase4/$$f.pdf paper/figures/$$f.pdf; done

paper: paper-numbers paper-figs
	@if command -v latexmk >/dev/null 2>&1; then cd paper && latexmk -pdf -interaction=nonstopmode main.tex; \
	else cd paper && tectonic -X compile --keep-logs --keep-intermediates main.tex; fi

# make freeze : write docs/DATA_FREEZE.md and data/derived/MANIFEST.sha256 (run after paper-figures; the tag is created by hand, see the file)
.PHONY: freeze
freeze:
	$(PY) analysis/phase4/data_freeze.py
