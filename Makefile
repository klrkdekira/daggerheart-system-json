.PHONY: help convert verify schemas extract indexes llms vocab record-pages sitemap test validate determinism check ci-check serve

PYTHON ?= python3
PDF := DH_SRD_2_2026_08_25.pdf

help:
	@echo "Available targets:"
	@echo "  convert      Re-convert SRD.md from the source PDF"
	@echo "  verify       Verify SRD.md against the PDF extraction, page by page"
	@echo "  schemas      Regenerate systems/*.schema.json"
	@echo "  extract      Rebuild objects/ (records, manifest, bundle, metrics)"
	@echo "  indexes      Rebuild explorer browse and search indexes"
	@echo "  llms         Regenerate llms.txt and llms-full.txt"
	@echo "  vocab        Rebuild vocabulary terms and HTML reference"
	@echo "  record-pages Build crawlable HTML counterparts for every record"
	@echo "  sitemap      Regenerate the exact published URL inventory"
	@echo "  test         Run the structural test suite"
	@echo "  validate     Validate identity, schemas, references, coverage, aggregates, graph shape"
	@echo "  determinism  Assert a clean rebuild is byte-identical"
	@echo "  check        Full pipeline + tests + validation + determinism"
	@echo "  ci-check     check without the PDF-dependent verify gate"
	@echo "  serve        Serve the explorer locally on http://localhost:8321"

convert:
	$(PYTHON) scripts/convert_srd_pdf.py $(PDF) SRD.md

verify:
	$(PYTHON) scripts/verify_srd_markdown.py $(PDF) SRD.md

schemas:
	$(PYTHON) scripts/build_schemas.py --root .

extract:
	$(PYTHON) scripts/build_corpus.py --root .

indexes:
	$(PYTHON) scripts/build_indexes.py --root .

llms:
	$(PYTHON) scripts/build_llms.py --root .

vocab:
	$(PYTHON) scripts/build_vocab.py --root .

record-pages:
	$(PYTHON) scripts/build_record_pages.py --root .

sitemap:
	$(PYTHON) scripts/build_sitemap.py --root .

test:
	$(PYTHON) -m unittest discover -s tests

validate:
	$(PYTHON) scripts/validate_corpus.py

determinism:
	$(PYTHON) scripts/check_determinism.py

check: verify ci-check

ci-check: schemas extract indexes llms vocab record-pages sitemap test validate determinism
	@echo "All corpus gates passed."

serve:
	$(PYTHON) -m http.server 8321
