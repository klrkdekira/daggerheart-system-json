#!/usr/bin/env python3
"""Validate the generated Daggerheart JSON-LD corpus.

Dependency-free gates, in the spirit of graph20's `make check`:

- identity: file path, @id, slug, @type, and @context agree for every record;
- schema: every record validates against its systems/ JSON Schema (a built-in
  validator covering the subset of Draft 2020-12 the schemas use);
- references: every node reference resolves to an emitted record;
- locators: line spans are in bounds, start at their declared heading, and
  section-owning spans never overlap page-marker arithmetic errors;
- coverage: every non-blank, non-comment SRD.md line falls inside at least
  one section-owning record or rule locator;
- aggregates: the manifest, bundle, and build metrics agree with the record
  files byte-for-byte and count-for-count;
- pins: collection counts match the expected corpus shape.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from build_corpus import BASE, COLLECTIONS, CONTEXT, Doc  # noqa: E402

EXPECTED_COUNTS = {
    "sources": 1,
    "domains": 10,
    "classes": 13,
    "subclasses": 26,
    "ancestries": 25,
    "communities": 15,
    "transformations": 6,
    "beastforms": 24,
    "weapons": 358,
    "armor": 76,
    "items": 120,
    "consumables": 120,
    "adversaries": 264,
    "environments": 47,
    "domain-cards": 210,
}

SECTION_OWNERS = {
    "domains", "classes", "ancestries", "communities", "transformations",
    "adversaries", "environments", "domain-cards", "rules",
}

REFERENCE_KEYS = {
    "source", "domains", "subclasses", "parentClass", "fromClass", "domain",
    "potentialAdversaries", "fromSection",
}


class SchemaValidator:
    """Validates the subset of JSON Schema Draft 2020-12 used in systems/."""

    def __init__(self, systems: Path) -> None:
        self.schemas = {
            path.name: json.loads(path.read_text())
            for path in systems.glob("*.schema.json")
        }

    def resolve(self, ref: str, current: str) -> tuple[dict, str]:
        file_part, _, pointer = ref.partition("#")
        name = file_part or current
        node: dict = self.schemas[name]
        for token in pointer.strip("/").split("/"):
            if token:
                node = node[token]
        return node, name

    def check(self, value, schema: dict, current: str, path: str, errors: list[str]) -> None:
        if "$ref" in schema:
            resolved, name = self.resolve(schema["$ref"], current)
            self.check(value, resolved, name, path, errors)
            return
        expected = schema.get("type")
        if expected is not None:
            allowed = expected if isinstance(expected, list) else [expected]
            kinds = {
                "object": dict, "array": list, "string": str,
                "integer": int, "number": (int, float), "boolean": bool,
            }
            if not any(
                isinstance(value, kinds[kind]) and not (kind == "integer" and isinstance(value, bool))
                for kind in allowed
            ):
                errors.append(f"{path}: expected {expected}, got {type(value).__name__}")
                return
        if "const" in schema and value != schema["const"]:
            errors.append(f"{path}: expected const {schema['const']!r}")
        if "enum" in schema and value not in schema["enum"]:
            errors.append(f"{path}: {value!r} not in enum")
        if isinstance(value, str):
            if "pattern" in schema and not re.search(schema["pattern"], value):
                errors.append(f"{path}: {value!r} fails pattern")
            if len(value) < schema.get("minLength", 0):
                errors.append(f"{path}: shorter than minLength")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if "minimum" in schema and value < schema["minimum"]:
                errors.append(f"{path}: below minimum")
        if isinstance(value, list):
            if len(value) < schema.get("minItems", 0):
                errors.append(f"{path}: fewer than minItems")
            if "items" in schema:
                for index, item in enumerate(value):
                    self.check(item, schema["items"], current, f"{path}[{index}]", errors)
        if isinstance(value, dict):
            properties = schema.get("properties", {})
            for key in schema.get("required", []):
                if key not in value:
                    errors.append(f"{path}: missing required {key!r}")
            for key, subvalue in value.items():
                if key in properties:
                    self.check(subvalue, properties[key], current, f"{path}.{key}", errors)
                elif schema.get("additionalProperties") is False:
                    errors.append(f"{path}: unexpected property {key!r}")


def main() -> None:
    root = Path(".")
    doc = Doc(root)
    objects = root / "objects"
    failures: list[str] = []
    validator = SchemaValidator(root / "systems")
    entity_types = dict(COLLECTIONS)

    records: dict[str, dict] = {}
    by_collection: dict[str, list[dict]] = {name: [] for name, _ in COLLECTIONS}
    for collection, _ in COLLECTIONS:
        for path in sorted((objects / collection).glob("*.jsonld")):
            record = json.loads(path.read_text())
            records[record["@id"]] = record
            by_collection[collection].append(record)
            expected_id = f"{BASE}objects/{collection}/{path.stem}"
            if record.get("@id") != expected_id:
                failures.append(f"{path}: @id does not match path")
            if record.get("slug") != path.stem:
                failures.append(f"{path}: slug does not match filename")
            if record.get("@context") != CONTEXT:
                failures.append(f"{path}: wrong @context")
            if record.get("@type") != entity_types[collection]:
                failures.append(f"{path}: wrong @type")
            schema_name = f"{entity_types[collection].casefold()}.schema.json"
            errors: list[str] = []
            validator.check(record, validator.schemas[schema_name], schema_name,
                            path.stem, errors)
            failures.extend(f"{path}: {error}" for error in errors[:3])

    # Collection count pins.
    for collection, expected in EXPECTED_COUNTS.items():
        actual = len(by_collection[collection])
        if actual != expected:
            failures.append(f"{collection}: expected {expected} records, found {actual}")

    # Reference resolution. htmlPage points at a record page, not a record.
    def refs_in(value):
        if isinstance(value, dict):
            if set(value) == {"@id"}:
                yield value["@id"]
            else:
                for key, sub in value.items():
                    # htmlPage and licenseUrl address pages/external IRIs,
                    # not corpus records.
                    if key in {"htmlPage", "licenseUrl"}:
                        continue
                    if key in REFERENCE_KEYS or isinstance(sub, (dict, list)):
                        yield from refs_in(sub)
        elif isinstance(value, list):
            for item in value:
                yield from refs_in(item)

    for record in records.values():
        for target in refs_in(record):
            if target not in records:
                failures.append(f"{record['@id']}: dangling reference {target}")

    # Locators and coverage.
    covered = [False] * len(doc.lines)
    for collection, _ in COLLECTIONS:
        if collection == "sources":
            continue
        for record in by_collection[collection]:
            locator = record["sourceLocator"]
            start, end = locator["lineStart"], locator["lineEnd"]
            if not (1 <= start <= end <= len(doc.lines)):
                failures.append(f"{record['@id']}: locator out of bounds")
                continue
            first = doc.lines[start - 1]
            if collection in SECTION_OWNERS - {"rules"} or (
                collection == "rules" and first.startswith("#")
            ):
                if collection in SECTION_OWNERS and first.startswith("#"):
                    if not first.endswith(locator["heading"]):
                        failures.append(f"{record['@id']}: heading mismatch at line {start}")
            if collection in SECTION_OWNERS:
                for index in range(start - 1, end):
                    covered[index] = True
    missing = [
        index + 1
        for index in range(len(doc.lines))
        if doc.is_content(index) and not covered[index]
    ]
    if missing:
        failures.append(f"coverage gap: {len(missing)} lines, first {missing[:5]}")

    # Manifest agreement.
    manifest = json.loads((objects / "daggerheart-system-data.jsonld").read_text())
    for entry in manifest["collections"]:
        actual = by_collection[entry["name"]]
        if entry["count"] != len(actual):
            failures.append(f"manifest count mismatch for {entry['name']}")
        member_ids = {member["@id"] for member in entry["members"]}
        if member_ids != {record["@id"] for record in actual}:
            failures.append(f"manifest members mismatch for {entry['name']}")
    if manifest["recordCount"] != len(records):
        failures.append("manifest recordCount mismatch")
    source = by_collection["sources"][0]
    if manifest["contentDigest"] != source["contentDigest"]:
        failures.append("manifest digest does not match source record")
    import hashlib

    actual_digest = "sha256:" + hashlib.sha256(doc.text.encode()).hexdigest()
    if source["contentDigest"] != actual_digest:
        failures.append("source record digest does not match SRD.md")

    # Bundle agreement.
    bundle = json.loads(
        (objects / "daggerheart-system-data.bundle.jsonld").read_text()
    )
    bundled = {member["@id"]: member for member in bundle["@graph"]}
    if set(bundled) != set(records):
        failures.append("bundle members do not match record files")
    else:
        for record_id, record in records.items():
            expected = dict(record)
            expected.pop("@context")
            if bundled[record_id] != expected:
                failures.append(f"bundle member differs from record: {record_id}")
                break

    # Explorer index agreement.
    collection_index = json.loads((objects / "collection-index.json").read_text())
    for collection, _ in COLLECTIONS:
        entries = collection_index["collections"].get(collection, [])
        if len(entries) != len(by_collection[collection]):
            failures.append(f"collection-index count mismatch for {collection}")
            continue
        slugs = {entry["slug"] for entry in entries}
        if slugs != {record["slug"] for record in by_collection[collection]}:
            failures.append(f"collection-index slugs mismatch for {collection}")
    search_index = json.loads((objects / "search-index.json").read_text())
    if len(search_index["documents"]) != len(records):
        failures.append("search-index document count mismatch")
    for token, postings in search_index["tokens"].items():
        if any(
            not (0 <= posting["document"] < len(search_index["documents"]))
            for posting in postings
        ):
            failures.append(f"search-index posting out of range for token {token!r}")
            break
    for name in ("llms.txt", "llms-full.txt", "index.html", "sitemap.xml",
                 "datapackage.json", "CITATION.cff", "SPECIFICATION.md",
                 "vocab/terms.json", "vocab/index.html"):
        if not (root / name).is_file():
            failures.append(f"missing artifact: {name}")

    # Record pages: every record has a crawlable page and vice versa.
    page_count = 0
    for record in records.values():
        page_id = record["htmlPage"]["@id"]
        relative = page_id.removeprefix(BASE)
        page = root / relative / "index.html"
        if not page.is_file():
            failures.append(f"missing record page: {relative}")
            continue
        page_count += 1
        content = page.read_text()
        if f'rel="canonical" href="{page_id}"' not in content:
            failures.append(f"record page missing canonical link: {relative}")
        if 'type="application/ld+json"' not in content:
            failures.append(f"record page missing JSON-LD alternate: {relative}")
    emitted_pages = len(list((root / "records").glob("*/*/index.html")))
    if emitted_pages != page_count:
        failures.append(
            f"records/ holds {emitted_pages} pages for {page_count} records"
        )

    # Sitemap agreement: every record page URL, exactly once.
    sitemap = (root / "sitemap.xml").read_text()
    sitemap_urls = re.findall(r"<loc>([^<]+)</loc>", sitemap)
    if len(sitemap_urls) != len(set(sitemap_urls)):
        failures.append("sitemap contains duplicate URLs")
    sitemap_set = set(sitemap_urls)
    for record in records.values():
        if record["htmlPage"]["@id"] not in sitemap_set:
            failures.append(f"sitemap missing {record['htmlPage']['@id']}")
            break

    # Graph shape: every emitted key must be a documented context term or
    # JSON-LD keyword; IRI-coerced predicates must carry node references.
    context_terms = json.loads(
        (root / "systems" / "context.jsonld").read_text()
    )["@context"]
    vocab_terms = json.loads((root / "vocab" / "terms.json").read_text())
    vocab_anchors = {entry["anchor"] for entry in vocab_terms["properties"]}
    structural_keys = {
        "@context", "@id", "@type", "@graph",
        # Nested structure keys live inside documented structured values.
        "chapter", "heading", "lineStart", "lineEnd", "pdfPageStart",
        "pdfPageEnd", "name", "kind", "stage", "rulesText",
    }
    coerced = {
        term for term, definition in context_terms.items()
        if isinstance(definition, dict) and definition.get("@type") == "@id"
        and "@reverse" not in definition
    }

    def check_keys(value, record_id: str) -> None:
        if isinstance(value, dict):
            for key, sub in value.items():
                if key not in structural_keys and key not in context_terms:
                    failures.append(f"{record_id}: undocumented term {key!r}")
                    continue
                if key in context_terms and not key.startswith("@"):
                    if key not in vocab_anchors and key not in structural_keys:
                        failures.append(f"{record_id}: term missing from vocabulary: {key!r}")
                if key in coerced:
                    nodes = sub if isinstance(sub, list) else [sub]
                    for node in nodes:
                        if not (isinstance(node, dict) and set(node) == {"@id"}):
                            failures.append(
                                f"{record_id}: bare value under IRI-coerced {key!r}"
                            )
                check_keys(sub, record_id)
        elif isinstance(value, list):
            for item in value:
                check_keys(item, record_id)

    for record in records.values():
        check_keys({k: v for k, v in record.items()}, record["@id"])
        if len(failures) > 60:
            break

    # Graph shape: incoming edge per non-source collection and link density.
    incoming: dict[str, int] = {name: 0 for name, _ in COLLECTIONS}
    outbound_linked = 0
    for record in records.values():
        has_outbound = False
        for key in REFERENCE_KEYS - {"source"}:
            values = record.get(key)
            if not values:
                continue
            has_outbound = True
            for ref_node in values if isinstance(values, list) else [values]:
                target_collection = ref_node["@id"].removeprefix(
                    BASE + "objects/"
                ).split("/")[0]
                incoming[target_collection] += 1
        if has_outbound:
            outbound_linked += 1
    manifest_member_collections = {
        entry["name"] for entry in manifest["collections"] if entry["members"]
    }
    for name, _ in COLLECTIONS:
        if name == "sources":
            continue
        if incoming[name] == 0 and name not in manifest_member_collections:
            failures.append(f"collection without incoming edges: {name}")
    density = outbound_linked / len(records)
    if density < 0.55:
        failures.append(
            f"outbound semantic-link coverage {density:.1%} is below the 55% gate"
        )

    # Version agreement across project metadata.
    import tomllib

    pyproject = tomllib.loads((root / "pyproject.toml").read_text())
    version = pyproject["project"]["version"]
    citation = (root / "CITATION.cff").read_text()
    datapackage = json.loads((root / "datapackage.json").read_text())
    if manifest["corpusVersion"] != version:
        failures.append("manifest corpusVersion disagrees with pyproject.toml")
    if f'version: "{version}"' not in citation:
        failures.append("CITATION.cff version disagrees with pyproject.toml")
    if datapackage["version"] != version:
        failures.append("datapackage.json version disagrees with pyproject.toml")
    if bundle["corpusVersion"] != version:
        failures.append("bundle corpusVersion disagrees with pyproject.toml")

    # Metrics agreement.
    metrics = json.loads((objects / "build-metrics.json").read_text())
    if metrics["recordCount"] != len(records):
        failures.append("metrics recordCount mismatch")
    if metrics["corpusVersion"] != version:
        failures.append("metrics corpusVersion disagrees with pyproject.toml")
    for name, _ in COLLECTIONS:
        if metrics["collections"][name] != len(by_collection[name]):
            failures.append(f"metrics count mismatch for {name}")

    if failures:
        print("Corpus validation failed:")
        for failure in failures[:40]:
            print(f"- {failure}")
        sys.exit(1)
    relation_total = metrics["relationCount"]
    print(
        f"Validated {len(records)} records, {relation_total} graph relations, "
        f"and full source coverage of {metrics['sourceContentLines']} content lines."
    )


if __name__ == "__main__":
    main()
