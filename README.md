# Daggerheart SRD System JSON

A source-faithful, machine-readable edition of the **Daggerheart System
Reference Document 2.0**, built on:

- JSON-LD 1.1 identity and graph relationships;
- JSON Schema Draft 2020-12 contracts;
- one record per reusable entity, with the original SRD prose alongside typed
  fields for discovery and filtering; and
- line-level provenance back to `SRD.md` and page-level provenance back to
  the official SRD PDF.

This is a reference corpus, not a rules engine or character builder.

## Start here

| I want to… | Start with |
| --- | --- |
| Browse and search the SRD | `index.html` (web explorer; `make serve`) |
| Fetch one record | `objects/<collection>/<slug>.jsonld` |
| Link to an indexable record page | `records/<collection>/<slug>/` |
| Load the complete graph | `objects/daggerheart-system-data.bundle.jsonld` |
| Discover collections and record IDs | `objects/daggerheart-system-data.jsonld` |
| Build a search or browse UI | `objects/search-index.json` and `objects/collection-index.json` |
| Give the corpus to an LLM | `llms-full.txt` |
| Resolve classes and properties | `vocab/terms.json` (HTML reference at `vocab/`) |
| Validate an integration | `systems/` |
| Read the architecture | `SPECIFICATION.md` |
| Cite the dataset | `CITATION.cff` / `datapackage.json` |

## Pipeline

```
DH_SRD_2_2026_08_25.pdf
  └─ scripts/convert_srd_pdf.py ──► SRD.md          (verified page-by-page)
       └─ scripts/build_corpus.py ──► objects/       (records, manifest, bundle)
            ├─ scripts/build_indexes.py ──► browse + search indexes
            ├─ scripts/build_llms.py ──► llms.txt, llms-full.txt
            └─ scripts/validate_corpus.py            (gates, below)
```

`index.html` is a static single-page explorer over these artifacts (browse,
filter, full-text search, and typed record views); run `make serve` and open
<http://localhost:8321/> to use it locally. Its design system derives from
the official Daggerheart brand palette (violet night sky `#160942`/`#24135F`,
gold foil `#E7C74B`, teal highlight `#83CDC2`, lavender `#F6F5FB`): the
default dark theme is the brand's "Fear" night-sky look, the light theme its
"Hope" counterpart, and every text pairing meets WCAG AA. Record pages and
the vocabulary reference share the same palette.

`SRD.md` is the sole content source for the corpus. It is itself generated
from the official PDF and verified token-for-token by
`scripts/verify_srd_markdown.py`, so every record traces back to the printed
document: each `sourceLocator` carries the SRD.md line span and the PDF pages
it came from.

## Corpus scope

The clean build contains 1,539 records across 16 collections:

| Collection | Count | Content |
| --- | ---: | --- |
| sources | 1 | Origin, version, license, attribution, and SHA-256 digests |
| domains | 10 | The ten magic domains |
| classes / subclasses | 13 / 26 | Starting stats, hope/class features, background questions, connections, domain and subclass relationships |
| ancestries / communities | 25 / 15 | Heritage descriptions and features |
| transformations | 6 | Features and roleplaying questions |
| beastforms | 24 | Druid forms with stats, attacks, advantages, and features |
| weapons / armor | 358 / 76 | Every table row across core, wheelchair, everyday-hero, western, and monster-hunting variants |
| items / consumables | 120 / 120 | Both loot tables with roll numbers and set provenance |
| adversaries | 264 | Decomposed stat blocks: tier, role, difficulty, thresholds, HP, stress, standard attack, experiences, and typed features |
| environments | 47 | Stat blocks with impulses, difficulty, features, and resolved links to their potential adversaries |
| domain-cards | 210 | Level, domain, type, recall cost, and card text |
| rules | 224 | Source-faithful prose for every section not covered by a typed record |

Every non-blank content line of `SRD.md` is inside at least one record
locator; the validator recomputes this on every run.

## Artifacts

| Artifact | Purpose |
| --- | --- |
| `index.html` | Static web explorer: browse, filter, search, and typed record views |
| `objects/<collection>/<slug>.jsonld` | One JSON-LD record per entity |
| `records/<collection>/<slug>/` | Crawlable HTML counterpart of every record (canonical URL, JSON-LD alternate, embedded JSON-LD) |
| `objects/daggerheart-system-data.jsonld` | Manifest with collection descriptors, counts, member links, and schema links |
| `objects/daggerheart-system-data.bundle.jsonld` | All records in one JSON-LD `@graph` |
| `objects/collection-index.json` | Compact browse metadata (names, slugs, groups, display subtitles) |
| `objects/search-index.json` | Static inverted token index used by the explorer's full-text search |
| `objects/build-metrics.json` | Asserted record/relation totals, recomputed by validation |
| `llms.txt` / `llms-full.txt` | LLM entry-point map and full plain-text corpus projection |
| `vocab/` | Dereferenceable vocabulary: `terms.json` and an HTML reference |
| `sitemap.xml` | Exact published URL inventory with deterministic `lastmod` |
| `datapackage.json` / `CITATION.cff` | Frictionless Data Package and citation metadata |
| `systems/context.jsonld` | Shared JSON-LD 1.1 context, including IRI coercion rules and reverse aliases |
| `systems/*.schema.json` | Draft 2020-12 contracts (generated by `scripts/build_schemas.py`) |

Record files use the path `objects/<collection>/<slug>.jsonld`; inside a
record the canonical `@id` omits the extension. Example:

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

## Verification

`make check` rebuilds every artifact and runs distinct gates:

- `verify` — SRD.md against the PDF extraction: per-page token multisets and
  character counts must match exactly;
- `schemas` / `extract` / `indexes` / `llms` / `vocab` / `record-pages` /
  `sitemap` — deterministic regeneration of every artifact;
- `test` — structural regression fixtures for extraction edge cases
  (`tests/`);
- `validate` — identity, schema conformance (dependency-free Draft 2020-12
  subset validator), reference resolution, locator bounds, 100% source-line
  coverage, manifest/bundle/metrics/index/page/sitemap/vocab agreement,
  graph shape (documented terms, node-reference coercion, incoming edges,
  ≥55% outbound link coverage), version agreement across `pyproject.toml`,
  the manifest, metrics, `CITATION.cff`, and `datapackage.json`, and
  collection count pins;
- `determinism` — a clean rebuild must be byte-identical to the checked-in
  `objects/`, `systems/`, `vocab/`, and `records/` trees and the generated
  text projections.

CI (`.github/workflows/ci.yml`) runs `make ci-check` — every gate except the
PDF-extraction parity check — on Python 3.12 and 3.13 with pinned actions,
then rejects any dirty tree. The official PDF is not committed; its SHA-256
digest is registered in the builder and asserted whenever the file is
present, so clean rebuilds elsewhere remain fully verified against the
registered digest.

## Legal

The Daggerheart SRD content is used under the Darrington Press Community
Gaming License. This document, including the Witherwild Campaign Frame, is
considered Public Game Content per that license. © 2026 Critical Role LLC.
All rights reserved. See <https://www.darringtonpress.com/license> and the
repository `LICENSE` file.
