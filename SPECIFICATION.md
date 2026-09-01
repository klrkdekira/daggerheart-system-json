# Daggerheart SRD System JSON — Technical Specification

Status: v0.1.0. The source-boundary, graph-fidelity, physical-provenance,
coverage, typed-extraction, vocabulary, and documentation requirements are
implemented and enforced by `make check`.

## 1. Objective

Turn the Daggerheart System Reference Document 2.0 into a modular,
machine-readable corpus with JSON-LD 1.1 identity and relationships, JSON
Schema Draft 2020-12 contracts, one file per reusable entity, aggregate
artifacts, physical source traceability, and source-faithful prose.

The corpus is reference data. Executable rules engines, character builders,
campaign state, and automation inferred from prose remain out of scope.

## 2. Source and legal boundary

`SRD.md` is the sole content source. It is generated from the official
`DH_SRD_2_2026_08_25.pdf` by `scripts/convert_srd_pdf.py` and verified
page-by-page by `scripts/verify_srd_markdown.py`: per-page token multisets
and non-whitespace character counts must exactly match the PDF text layer,
so the Markdown adds structure (headings, tables, emphasis) without adding,
losing, or rewording content. The PDF itself is not distributed; its SHA-256
digest is registered in `scripts/build_corpus.py` and asserted whenever the
file is present.

The SRD content is Public Game Content per the Darrington Press Community
Gaming License. The required attribution statement is preserved verbatim in
the source record, manifest, record pages, `llms.txt`, and `llms-full.txt`.

## 3. Corpus scope

The clean build contains 1,539 records across 16 collections:

| Collection | Count | Content |
| --- | ---: | --- |
| sources | 1 | Origin, version, license, attribution, and SHA-256 digests |
| domains | 10 | The ten magic domains |
| classes / subclasses | 13 / 26 | Starting stats, hope/class features, background questions, connections, and relationships |
| ancestries / communities | 25 / 15 | Heritage descriptions and features |
| transformations | 6 | Features and roleplaying questions |
| beastforms | 24 | Druid forms with stats, attacks, advantages, and features |
| weapons / armor | 358 / 76 | Every table row across core, wheelchair, everyday-hero, western, and monster-hunting variants |
| items / consumables | 120 / 120 | Both loot tables with roll numbers and set provenance |
| adversaries | 264 | Decomposed stat blocks with typed features |
| environments | 47 | Stat blocks with impulses and resolved adversary links |
| domain-cards | 210 | Level, domain, type, recall cost, and card text |
| rules | 224 | Source-faithful prose for every section not covered by a typed record |

## 4. Data architecture

| Concern | Decision |
| --- | --- |
| Base IRI | `https://cheeleong.dev/daggerheart-system-json/` |
| Vocabulary | Fragment IRIs under `https://cheeleong.dev/daggerheart-system-json/vocab/#` |
| Context | `systems/context.jsonld`, JSON-LD 1.1 |
| Schemas | Draft 2020-12; entity schemas reject unknown properties |
| Identity | Stable lowercase-kebab-case canonical `@id` values |
| Relationships | `{ "@id": "..." }` node references only under IRI-coerced predicates |
| Prose | Source wording in `rulesText`/`description`; structured fields remain indexes |
| Aggregates | Manifest, member-validated bundle, browse/search indexes, LLM guides, vocabulary, record pages, sitemap, build metrics |

Emitted predicates cover class domains and subclasses, subclass parents,
card domains, beastform classes, environment adversary references, table-row
section provenance (`fromSection`), and source attribution. Core incoming
directions have documented JSON-LD `@reverse` aliases (`cardsInDomain`,
`subclassOf`, `beastformsOfClass`, `appearsInEnvironment`,
`sectionEntities`). The graph gate enforces at least 55% outbound
semantic-link coverage, documented terms for every emitted key, node-reference
shape for IRI-coerced predicates, and an incoming edge for every non-source
collection.

Every record carries a physical source locator (chapter, heading, SRD.md
line span, and PDF page span) and an `htmlPage` link to its crawlable HTML
counterpart under `records/<collection>/<slug>/`.

## 5. Extraction rules

`SRD.md` has a hierarchical heading structure. Typed entities are recognized
from structural grammar:

- classes: the 13 printed class names inside the CLASSES section; each class
  owns everything to the next class heading, with exactly two subclasses
  after its SUBCLASSES heading;
- heritages/transformations: printed name headings inside their sections;
- beastforms: headings between BEASTFORM OPTIONS and the end of the Druid
  section, grouped by TIER headings;
- stat blocks: any heading whose first content line is `*Tier N Role*`;
  Motives & Tactics vs. Impulses decides adversary vs. environment;
- domain cards: appendix headings with a printed `Level N Domain Type` line;
  the card's own printed domain is authoritative because the two-column
  appendix layout can carry a domain's last cards past the next group
  heading;
- equipment: Markdown pipe tables recognized by header signature
  (weapon/armor/loot), with tier, category, and variant taken from enclosing
  headings; a header-less table continues the immediately preceding table;
- rules: every remaining heading section, emitted by a recursive gap walker
  so that 100% of content lines fall inside at least one locator.

Environment `Potential Adversaries` strings are matched case-insensitively
against adversary names to produce graph links while the printed string is
preserved verbatim.

## 6. Verification

`make check` rebuilds every artifact and runs distinct gates.
`pyproject.toml` is the single project-version source; validation
cross-checks it against the manifest, bundle, metrics, data package, and
citation metadata.

- `verify`: SRD.md against the PDF extraction (requires the local PDF);
- `schemas` / `extract` / `indexes` / `llms` / `vocab` / `record-pages` /
  `sitemap`: deterministic regeneration of every artifact;
- `validate`: identity, schema conformance via a dependency-free Draft
  2020-12 subset validator, reference resolution, locator bounds, 100%
  source-line coverage, manifest/bundle/metrics/index/page/sitemap/vocab
  agreement, graph shape, version agreement, and collection count pins;
- `test`: structural regression fixtures for extraction edge cases;
- `determinism`: two clean builds must be byte-identical to the checked-in
  artifacts.

These automated gates establish the repository acceptance criteria; they do
not make the project official or expand the source/legal scope.
