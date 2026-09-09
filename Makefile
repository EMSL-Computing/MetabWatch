# MetabWatch — local workflow smoke tests
#
# Primary targets:
#   make test-workflow-targeted    Targeted search-space end-to-end run
#   make test-workflow-untargeted  Untargeted search-space end-to-end run
#
# Convenience:
#   make test-workflow             Both targeted and untargeted
#
# Prerequisites:
#   - Repo .venv with package deps installed (`pip install -e .`), or set PYTHON=
#   - Raw files under $(RAW_DIR) (default: data/raw_positive/)
#
# Large .raw files are not in git. Place them under data/raw_positive/
# or use `make get-test-data` once a download URL is configured.

SHELL := /bin/bash

# Prefer the repo virtualenv; override with e.g. PYTHON=python3 on the CLI.
ifeq ($(origin PYTHON),undefined)
  ifneq ($(wildcard .venv/bin/python),)
    PYTHON := .venv/bin/python
  else
    PYTHON := python
  endif
endif

# Shared raw input for HILIC QC test runs
RAW_DIR ?= data/raw_positive

# Targeted: built-in preset CLI (method + search + folders)
METHOD ?= hilic_metab_pnnl
TARGETED_RESULTS_DIR ?= data/results_hilic_pos

# Untargeted smoke: advanced JSON so fixtures named QC_Metab_* still match
# (preset untargeted filter is "Pooled"; local smoke data uses QC_Metab_ stems).
UNTARGETED_CONFIG      ?= data/hilic_pipeline_config_untargeted.json
UNTARGETED_RESULTS_DIR ?= data/results_hilic_pos_untargeted

# Optional future CI download location (not required when data is already on disk)
TEST_DATA_DIR ?= test_data
# When URLs are available, set e.g.:
#   TEST_DATA_ARCHIVE_URL = https://example.com/hilic_qc_raw.tar.gz
TEST_DATA_ARCHIVE_URL ?=

.PHONY: help \
	check-test-data get-test-data \
	test-unit \
	test-workflow-targeted test-workflow-untargeted test-workflow \
	verify-workflow-outputs \
	changelog-draft

help:
	@echo "MetabWatch workflow test targets"
	@echo ""
	@echo "  make test-unit                 Config loader unit tests (pytest)"
	@echo "  make test-workflow-targeted    Targeted mode (--once --force-reprocess)"
	@echo "  make test-workflow-untargeted  Untargeted mode (--once --force-reprocess)"
	@echo "  make test-workflow             Targeted, then untargeted"
	@echo "  make check-test-data           Verify local raw test data is present"
	@echo "  make get-test-data             Download test data (when URL configured) or check local"
	@echo "  make verify-workflow-outputs   Check expected result files (set RESULTS_DIR=...)"
	@echo "  make changelog-draft           Print origin/main..HEAD subjects for docs/CHANGELOG.md"
	@echo ""
	@echo "Variables (override on the command line):"
	@echo "  PYTHON=$(PYTHON)"
	@echo "  RAW_DIR=$(RAW_DIR)"
	@echo "  METHOD=$(METHOD)   # hilic_metab_pnnl, hilic_metab_olympic_eclipse01, rp_metab_pnnl, or rp_metab_olympic_eclipse01"
	@echo "  TARGETED_RESULTS_DIR=$(TARGETED_RESULTS_DIR)"
	@echo "  UNTARGETED_CONFIG=$(UNTARGETED_CONFIG)  # advanced JSON for QC_Metab fixtures"
	@echo "  UNTARGETED_RESULTS_DIR=$(UNTARGETED_RESULTS_DIR)"
	@echo ""
	@echo "Workflow tests always pass --once --force-reprocess (full end-to-end from raw)."
	@echo "Targeted uses: metabwatch --method \$$METHOD --search targeted -i -o"
	@echo "Untargeted smoke keeps --config (sample filter QC_Metab_*, not Pooled)."
	@echo ""
	@echo "Examples:"
	@echo "  make test-unit"
	@echo "  make test-workflow-targeted"
	@echo "  make test-workflow-untargeted"
	@echo "  make test-workflow"
	@echo "  make test-workflow PYTHON=python3   # override default .venv"
	@echo "  make changelog-draft"

# ---------------------------------------------------------------------------
# Release helpers
# ---------------------------------------------------------------------------

# Print commit subjects since origin/main for hand-editing into docs/CHANGELOG.md.
# Does not modify any files. See docs/RELEASING.md.
changelog-draft:
	@git fetch origin main --quiet 2>/dev/null || true
	@echo "=== Commits origin/main..HEAD (no merges) — draft into docs/CHANGELOG.md ==="
	@git log origin/main..HEAD --oneline --no-merges
	@echo "=== End draft list ==="

# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------

test-unit:
	@echo "=== Unit tests (Python: $$($(PYTHON) -c 'import sys; print(sys.executable)')) ==="
	$(PYTHON) -m pytest tests/test_config.py tests/test_presets.py tests/test_cli_presets.py tests/test_polarity.py -q
	@echo "=== Unit tests PASSED ==="

# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------

check-test-data:
	@if [ ! -d "$(RAW_DIR)" ]; then \
		echo "Error: raw test data directory missing: $(RAW_DIR)"; \
		echo "Place Thermo .raw files there (not stored in git)."; \
		echo "Or run 'make get-test-data' once a download URL is configured."; \
		exit 1; \
	fi
	@raw_count=$$(find "$(RAW_DIR)" -maxdepth 1 -name '*.raw' | wc -l | tr -d ' '); \
	if [ "$$raw_count" -lt 1 ]; then \
		echo "Error: no .raw files in $(RAW_DIR)"; \
		exit 1; \
	fi; \
	echo "Test data OK: $$raw_count .raw file(s) in $(RAW_DIR)"

# Optional download for CI/CD (metaMS / MONET-style). Not required when local data exists.
# When TEST_DATA_ARCHIVE_URL is set, downloads and unpacks under the repo root
# (expected to populate data/raw_positive/ or the path you set via RAW_DIR).
#
# TODO: add a resolvable URL for CI/CD test-data download (large .raw files not in git)
# TODO: refine archive layout / unpack destination once the hosted test-data URL is known
get-test-data:
	@if [ -n "$(TEST_DATA_ARCHIVE_URL)" ]; then \
		echo "Downloading test data from $(TEST_DATA_ARCHIVE_URL)"; \
		mkdir -p "$(TEST_DATA_DIR)"; \
		archive="$(TEST_DATA_DIR)/hilic_qc_raw_archive"; \
		curl --retry 3 --retry-delay 5 --connect-timeout 30 --max-time 600 \
			-L -o "$$archive" "$(TEST_DATA_ARCHIVE_URL)"; \
		case "$(TEST_DATA_ARCHIVE_URL)" in \
			*.zip) unzip -o "$$archive" -d "$(CURDIR)" ;; \
			*.tar.gz|*.tgz) tar -xzf "$$archive" -C "$(CURDIR)" ;; \
			*.tar) tar -xf "$$archive" -C "$(CURDIR)" ;; \
			*) echo "Error: unknown archive type for $(TEST_DATA_ARCHIVE_URL)"; exit 1 ;; \
		esac; \
		echo "Test data downloaded (see $(RAW_DIR))"; \
		$(MAKE) check-test-data RAW_DIR="$(RAW_DIR)"; \
	else \
		echo "TEST_DATA_ARCHIVE_URL is not set (expected for CI once URLs exist)."; \
		echo "Skipping download; checking for existing local test data..."; \
		$(MAKE) check-test-data RAW_DIR="$(RAW_DIR)"; \
	fi

# ---------------------------------------------------------------------------
# Workflow smoke tests
# ---------------------------------------------------------------------------

test-workflow-targeted: check-test-data
	@if [ ! -x "$(PYTHON)" ] && ! command -v "$(PYTHON)" >/dev/null 2>&1; then \
		echo "Error: Python not found: $(PYTHON)"; \
		echo "Create the repo venv (.venv) or set PYTHON=..."; \
		exit 1; \
	fi
	@echo "=== Targeted workflow test ==="
	@echo "Python: $$($(PYTHON) -c 'import sys; print(sys.executable)')"
	@echo "Preset: --method $(METHOD) --search targeted  (--once --force-reprocess)"
	$(PYTHON) -m metabwatch.pipeline --mode watch \
		--method $(METHOD) --search targeted \
		--input $(RAW_DIR) --output $(TARGETED_RESULTS_DIR) \
		--once --force-reprocess
	@$(MAKE) verify-workflow-outputs RESULTS_DIR="$(TARGETED_RESULTS_DIR)"
	@echo "=== Targeted workflow test PASSED ==="

test-workflow-untargeted: check-test-data
	@if [ ! -f "$(UNTARGETED_CONFIG)" ]; then \
		echo "Error: untargeted config missing: $(UNTARGETED_CONFIG)"; \
		exit 1; \
	fi
	@if [ ! -x "$(PYTHON)" ] && ! command -v "$(PYTHON)" >/dev/null 2>&1; then \
		echo "Error: Python not found: $(PYTHON)"; \
		echo "Create the repo venv (.venv) or set PYTHON=..."; \
		exit 1; \
	fi
	@echo "=== Untargeted workflow test ==="
	@echo "Python: $$($(PYTHON) -c 'import sys; print(sys.executable)')"
	@echo "Config: $(UNTARGETED_CONFIG)  (--once --force-reprocess)"
	$(PYTHON) -m metabwatch.pipeline --mode watch --config $(UNTARGETED_CONFIG) --once --force-reprocess
	@$(MAKE) verify-workflow-outputs RESULTS_DIR="$(UNTARGETED_RESULTS_DIR)"
	@echo "=== Untargeted workflow test PASSED ==="

test-workflow: test-workflow-targeted test-workflow-untargeted
	@echo ""
	@echo "========================================"
	@echo " test-workflow: ALL CHECKS PASSED"
	@echo "  targeted:   --method $(METHOD) --search targeted -> $(TARGETED_RESULTS_DIR)"
	@echo "  untargeted: $(UNTARGETED_CONFIG) -> $(UNTARGETED_RESULTS_DIR)"
	@echo "========================================"

verify-workflow-outputs:
	@if [ -z "$(RESULTS_DIR)" ]; then \
		echo "Error: RESULTS_DIR is not set (e.g. RESULTS_DIR=data/results_hilic_pos)"; \
		exit 1; \
	fi
	@missing=0; \
	for f in \
		"$(RESULTS_DIR)/dashboard.html" \
		"$(RESULTS_DIR)/pipeline_manifest.json" \
		"$(RESULTS_DIR)/export_mz.csv" \
		"$(RESULTS_DIR)/export_rt.csv" \
		"$(RESULTS_DIR)/export_height.csv"; do \
		if [ ! -f "$$f" ]; then \
			echo "Missing expected output: $$f"; \
			missing=1; \
		else \
			echo "Found: $$f"; \
		fi; \
	done; \
	match_count=$$(find "$(RESULTS_DIR)" -maxdepth 1 -name '*_targeted_matches.csv' 2>/dev/null | wc -l | tr -d ' '); \
	if [ "$$match_count" -lt 1 ]; then \
		echo "Missing expected output: $(RESULTS_DIR)/*_targeted_matches.csv"; \
		missing=1; \
	else \
		echo "Found: $$match_count targeted_matches CSV(s) under $(RESULTS_DIR)"; \
	fi; \
	if [ "$$missing" -ne 0 ]; then \
		echo "Error: workflow outputs incomplete under $(RESULTS_DIR)"; \
		exit 1; \
	fi
	@echo "Expected workflow outputs present."
