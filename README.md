# Daggerheart SRD System JSON

[![CI](https://github.com/klrkdekira/daggerheart-system-json/actions/workflows/ci.yml/badge.svg)](https://github.com/klrkdekira/daggerheart-system-json/actions/workflows/ci.yml)
[![Version](https://img.shields.io/badge/version-0.1.0-blue.svg)](https://github.com/klrkdekira/daggerheart-system-json)
[![JSON-LD 1.1](https://img.shields.io/badge/JSON--LD-1.1-blue.svg)](https://www.w3.org/TR/json-ld11/)
[![Content License: DPCGL](https://img.shields.io/badge/Content_License-DPCGL-lightgrey.svg)](https://darringtonpress.com/license/)
[![Code License: MIT](https://img.shields.io/badge/Code_License-MIT-yellow.svg)](LICENSE)

A source-faithful, machine-readable edition of the **Daggerheart System
Reference Document 2.0**. The repository turns the official SRD PDF into
1,539 modular records across 16 collections, with:

- JSON-LD 1.1 identity and graph relationships;
- JSON Schema Draft 2020-12 contracts;
- the original SRD prose alongside typed fields for discovery and filtering;
  and
- line-level provenance back to `SRD.md` and page-level provenance back to
  the official SRD PDF.

This is a reference corpus, not a rules engine or character builder.

[Explore the corpus](https://cheeleong.dev/daggerheart-system-json/) ·
[Read the vocabulary](https://cheeleong.dev/daggerheart-system-json/vocab/) ·
[Technical specification](SPECIFICATION.md) ·
[LLM guide](llms.txt)

## Start here

The repository is published as static files, so consumers do not need an API
key, database, or runtime.

| I want to… | Start with |
| --- | --- |
| Browse and search the SRD | [Web explorer](https://cheeleong.dev/daggerheart-system-json/) |
| Fetch one record | [`objects/<collection>/<slug>.jsonld`](objects/adversaries/acid-burrower.jsonld) |
| Link to an indexable record page | [`records/<collection>/<slug>/`](records/adversaries/acid-burrower/) |
| Load the complete graph | [`objects/daggerheart-system-data.bundle.jsonld`](https://cheeleong.dev/daggerheart-system-json/objects/daggerheart-system-data.bundle.jsonld) |
| Discover collections and record IDs | [`objects/daggerheart-system-data.jsonld`](https://cheeleong.dev/daggerheart-system-json/objects/daggerheart-system-data.jsonld) |
| Build a search or browse UI | [`objects/search-index.json`](https://cheeleong.dev/daggerheart-system-json/objects/search-index.json) and [`objects/collection-index.json`](https://cheeleong.dev/daggerheart-system-json/objects/collection-index.json) |
| Give the corpus to an LLM | [`llms-full.txt`](https://cheeleong.dev/daggerheart-system-json/llms-full.txt) |
| Resolve classes and properties | [`vocab/terms.json`](https://cheeleong.dev/daggerheart-system-json/vocab/terms.json) |
| Validate an integration | [`systems/`](systems/) |
| Cite the dataset | [`CITATION.cff`](CITATION.cff) / [`datapackage.json`](datapackage.json) |

For example, fetch a single adversary or the complete bundle:

```bash
curl -fsSL https://cheeleong.dev/daggerheart-system-json/objects/adversaries/acid-burrower.jsonld
curl -fsSL https://cheeleong.dev/daggerheart-system-json/objects/daggerheart-system-data.bundle.jsonld -o daggerheart.jsonld
```

Record files use the path `objects/<collection>/<slug>.jsonld`. Inside a
record, the canonical `@id` omits the file extension:

```json
{
  "@id": "https://cheeleong.dev/daggerheart-system-json/objects/adversaries/acid-burrower",
  "@type": "Adversary",
  "name": "Acid Burrower",
  "tier": 1,
  "role": "Solo",
  "standardAttack": { "name": "Claws", "range": "Very Close", "damage": "1d12+2 phy" },
  "sourceLocator": { "lineStart": 5354, "lineEnd": 5376, "pdfPageStart": 97, "pdfPageEnd": 97 }
}
```

The example is abbreviated. The full record also retains the description,
motives and tactics, thresholds, experiences, and typed features.

## Pipeline

```
DH_SRD_2_2026_08_25.pdf
  └─ scripts/convert_srd_pdf.py ──► SRD.md          (verified page-by-page)
       └─ scripts/build_corpus.py ──► objects/       (records, manifest, bundle)
            ├─ scripts/build_indexes.py ──► browse + search indexes
            ├─ scripts/build_llms.py ──► llms.txt, llms-full.txt
            └─ scripts/validate_corpus.py            (gates, below)
```

`SRD.md` is the sole content source for the corpus. It is itself generated
from the official PDF and verified token-for-token by
`scripts/verify_srd_markdown.py`, so every record traces back to the printed
document: each `sourceLocator` carries the SRD.md line span and the PDF pages
it came from.

`index.html` is a static single-page explorer over these artifacts (browse,
filter, full-text search, and typed record views); run `make serve` and open
<http://localhost:8321/> to use it locally. Its design system derives from
the official Daggerheart brand palette: the default dark theme is the brand's
"Fear" night-sky look, the light theme its "Hope" counterpart, and every text
pairing meets WCAG AA. Record pages and the vocabulary reference share the
same palette.

## Corpus inventory

The clean build contains 1,539 records across 16 collections:

| Collection | Records | What is represented |
| --- | ---: | --- |
| `sources` | 1 | Origin, version, license, attribution, and SHA-256 digests |
| `domains` | 10 | The ten magic domains |
| `classes` / `subclasses` | 13 / 26 | Starting stats, hope/class features, background questions, connections, domain and subclass relationships |
| `ancestries` / `communities` | 25 / 15 | Heritage descriptions and features |
| `transformations` | 6 | Features and roleplaying questions |
| `beastforms` | 24 | Druid forms with stats, attacks, advantages, and features |
| `weapons` / `armor` | 358 / 76 | Every table row across core, wheelchair, everyday-hero, western, and monster-hunting variants |
| `items` / `consumables` | 120 / 120 | Both loot tables with roll numbers and set provenance |
| `adversaries` | 264 | Decomposed stat blocks: tier, role, difficulty, thresholds, HP, stress, standard attack, experiences, and typed features |
| `environments` | 47 | Stat blocks with impulses, difficulty, features, and resolved links to their potential adversaries |
| `domain-cards` | 210 | Level, domain, type, recall cost, and card text |
| `rules` | 224 | Source-faithful prose for every section not covered by a typed record |
| **Total** | **1,539** | **8,904 non-blank source lines covered** |

## Data model and guarantees

The project is designed for source-backed reference and retrieval workloads:

- **Stable identity.** Every entity has a lowercase-kebab-case canonical
  `@id` under `https://cheeleong.dev/daggerheart-system-json/` and an
  `@type` defined by the shared context.
- **Graph-safe links.** Semantic relationships use `{ "@id": "…" }` node
  references. `$ref` is reserved for JSON Schema composition.
- **Typed mechanics.** Adversaries and environments expose decomposed stat
  blocks; weapons, armor, items, and consumables expose typed table fields;
  domain cards expose level, domain, type, and recall cost.
- **Source-faithful prose.** `rulesText` and `description` preserve source
  wording. Typed sibling fields are indexes, not replacements for the prose.
- **Physical provenance.** `sourceLocator` identifies the source chapter,
  heading, inclusive `SRD.md` line range, and the official PDF page range.
- **No invented values.** Extraction does not fill gaps in the source; a
  stat printed as `None` stays `None`.
- **Official-PDF parity.** `SRD.md` is checked page-by-page against the
  224-page official SRD 2.0 PDF
  (`sha256:55d8b92b7e58aa1da99a4a59aa77352483ef4fbda71baddb9af9bfc1f333bd2a`):
  per-page token multisets and character counts must match exactly. The PDF
  itself is not committed; its digest is registered in the builder and
  asserted whenever the file is present.
- **Deterministic output.** Clean builds contain no timestamps or random
  ordering and must reproduce the checked-in artifacts byte for byte.

The generated metrics currently report 100% interval coverage of the 8,904
in-scope, non-blank source lines, 2,695 graph relations, and 64.1% outbound
semantic-link coverage (validated against a ≥55% gate). Coverage means every
line falls within at least one record locator; the separate identity, schema,
reference, and graph gates test stronger claims.

See [SPECIFICATION.md](SPECIFICATION.md) for the source boundary, extraction
grammar, architecture, and acceptance criteria.

## Published artifacts

| Artifact | Purpose |
| --- | --- |
| [`index.html`](https://cheeleong.dev/daggerheart-system-json/) | Static web explorer: browse, filter, search, and typed record views |
| [`objects/<collection>/<slug>.jsonld`](objects/) | One JSON-LD record per entity |
| [`records/<collection>/<slug>/`](records/) | Crawlable HTML counterpart of every record (canonical URL, JSON-LD alternate, embedded JSON-LD) |
| [`objects/daggerheart-system-data.jsonld`](https://cheeleong.dev/daggerheart-system-json/objects/daggerheart-system-data.jsonld) | Manifest with collection descriptors, counts, member links, and schema links |
| [`objects/daggerheart-system-data.bundle.jsonld`](https://cheeleong.dev/daggerheart-system-json/objects/daggerheart-system-data.bundle.jsonld) | All 1,539 records in one JSON-LD `@graph` |
| [`objects/collection-index.json`](https://cheeleong.dev/daggerheart-system-json/objects/collection-index.json) | Compact browse metadata (names, slugs, groups, display subtitles) |
| [`objects/search-index.json`](https://cheeleong.dev/daggerheart-system-json/objects/search-index.json) | Static inverted token index used by the explorer's full-text search |
| [`objects/build-metrics.json`](objects/build-metrics.json) | Asserted record/relation totals, recomputed by validation |
| [`llms.txt`](https://cheeleong.dev/daggerheart-system-json/llms.txt) / [`llms-full.txt`](https://cheeleong.dev/daggerheart-system-json/llms-full.txt) | LLM entry-point map and full plain-text corpus projection |
| [`vocab/`](https://cheeleong.dev/daggerheart-system-json/vocab/) | Dereferenceable vocabulary: `terms.json` and an HTML reference |
| [`sitemap.xml`](sitemap.xml) | Exact published URL inventory with deterministic `lastmod` |
| [`datapackage.json`](datapackage.json) / [`CITATION.cff`](CITATION.cff) | Frictionless Data Package and citation metadata |
| [`systems/context.jsonld`](systems/context.jsonld) | Shared JSON-LD 1.1 context, including IRI coercion rules and reverse aliases |
| [`systems/*.schema.json`](systems/) | Draft 2020-12 contracts (generated by `scripts/build_schemas.py`) |

## Development

### Prerequisites

- Python 3.12 or newer (the build and validation scripts are dependency-free)
- Poppler's `pdftotext` for the PDF-dependent conversion and parity targets

Run the full verification pipeline:

```bash
make check
```

### Make targets

| Target | Result |
| --- | --- |
| `convert` | Re-convert `SRD.md` from the source PDF. |
| `verify` | Verify `SRD.md` against the PDF extraction, page by page. |
| `schemas` | Regenerate `systems/*.schema.json`. |
| `extract` | Rebuild `objects/` (records, manifest, bundle, metrics). |
| `indexes` | Rebuild explorer browse and search indexes. |
| `llms` | Regenerate `llms.txt` and `llms-full.txt`. |
| `vocab` | Rebuild vocabulary terms and the HTML reference. |
| `record-pages` | Build crawlable HTML counterparts for every record. |
| `sitemap` | Regenerate the exact published URL inventory. |
| `test` | Run the structural test suite. |
| `validate` | Validate identity, schemas, references, coverage, aggregates, and graph shape. |
| `determinism` | Assert a clean rebuild is byte-identical. |
| `check` | Full pipeline + tests + validation + determinism. |
| `ci-check` | `check` without the PDF-dependent verify gate. |
| `serve` | Serve the explorer locally on <http://localhost:8321>. |

`make check` rebuilds every artifact and runs distinct gates:

- `verify`: SRD.md against the PDF extraction; per-page token multisets and
  character counts must match exactly.
- `schemas`, `extract`, `indexes`, `llms`, `vocab`, `record-pages`, and
  `sitemap`: deterministic regeneration of every artifact.
- `test`: structural regression fixtures for extraction edge cases
  (`tests/`).
- `validate`: identity, schema conformance (dependency-free Draft 2020-12
  subset validator), reference resolution, locator bounds, 100% source-line
  coverage, manifest/bundle/metrics/index/page/sitemap/vocab agreement,
  graph shape (documented terms, node-reference coercion, incoming edges,
  ≥55% outbound link coverage), version agreement across `pyproject.toml`,
  the manifest, metrics, `CITATION.cff`, and `datapackage.json`, and
  collection count pins.
- `determinism`: a clean rebuild must be byte-identical to the checked-in
  `objects/`, `systems/`, `vocab/`, and `records/` trees and the generated
  text projections.

CI (`.github/workflows/ci.yml`) runs `make ci-check` on Python 3.12 and 3.13
with pinned actions, then rejects any dirty tree. `ci-check` covers every
gate except the PDF-extraction parity check, since the PDF is not committed.

## Repository layout

```text
daggerheart-system-json/
├── SRD.md                 # Authoritative in-scope source, generated from the PDF
├── objects/               # Generated records, manifest, bundle, and indexes
│   └── sources/           # Source metadata and digests
├── systems/               # JSON-LD context and JSON Schema contracts
├── vocab/                 # Vocabulary browser and machine-readable terms
├── records/               # Generated crawlable HTML record counterparts
├── scripts/               # Deterministic conversion, build, and validation tools
├── tests/                 # Structural regression tests
├── index.html             # Dependency-free static web explorer
├── llms.txt               # LLM-oriented corpus guide
├── llms-full.txt          # Full plain-text corpus projection
├── SPECIFICATION.md       # Source of truth for architecture and acceptance
└── Makefile               # Build and verification entry points
```

The official SRD 2.0 PDF (`DH_SRD_2_2026_08_25.pdf`) is not committed; place
it in the repository root to run the `convert` and `verify` targets.

## Scope

`SRD.md` is the sole content source. Material from rulebooks, wikis, other
SRD versions, or external datasets is not mixed into the corpus. Executable
rules interpretation, campaign state, character building, and automation
inferred from prose are intentionally out of scope.

## License and attribution

Repository-authored code, schemas, and documentation are available under the
[MIT License](LICENSE). SRD content is used under the
[Darrington Press Community Gaming License](https://darringtonpress.com/license/)
with the required attribution:

> This product includes materials from the Daggerheart System Reference
> Document 2.0, © Critical Role, LLC. All rights reserved. It is used under
> the terms of the Darrington Press Community Gaming (DPCGL) License.
> Darrington Press, LLC is the creator of this Public Game Content. More
> information can be found at <https://www.daggerheart.com>.

Project citation metadata is available in [`CITATION.cff`](CITATION.cff).

This is an independent, unofficial reference project and is not affiliated
with, sponsored by, or endorsed by Darrington Press, LLC or Critical Role,
LLC.
