#!/usr/bin/env python3
"""Generate llms.txt (entry-point map) and llms-full.txt (full text projection)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from build_corpus import ATTRIBUTION, BASE, COLLECTIONS, CORPUS_VERSION

SKIP_KEYS = {
    "@context", "@id", "@type", "name", "slug", "source", "sourceLocator",
}


def flatten(value, label: str, lines: list[str]) -> None:
    if isinstance(value, dict):
        if set(value) == {"@id"}:
            lines.append(f"[{label}] {value['@id'].removeprefix(BASE)}")
            return
        named = value.get("name")
        for key, sub in value.items():
            if key == "name":
                continue
            sub_label = f"{label}.{key}" if not named else f"{label}: {named} ({key})"
            flatten(sub, sub_label, lines)
    elif isinstance(value, list):
        if all(isinstance(item, str) for item in value):
            lines.append(f"[{label}]")
            lines.extend(f"- {item}" for item in value)
        else:
            for item in value:
                flatten(item, label, lines)
    else:
        text = str(value)
        if "\n" in text:
            lines.append(f"[{label}]")
            lines.append(text)
        else:
            lines.append(f"[{label}] {text}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    root = args.root
    objects = root / "objects"
    manifest = json.loads((objects / "daggerheart-system-data.jsonld").read_text())

    counts = {entry["name"]: entry["count"] for entry in manifest["collections"]}
    total = manifest["recordCount"]

    guide = [
        "# Daggerheart SRD System JSON",
        "",
        f"> Machine-readable JSON-LD 1.1 reference corpus for the Daggerheart "
        f"System Reference Document 2.0, with JSON Schema Draft 2020-12 "
        f"validation. {total:,} records preserve source wording, typed fields, "
        "graph links, and line-level provenance.",
        "",
        f"Attribution: {ATTRIBUTION}",
        "",
        "## Entry points",
        "",
        f"- [Human-readable explorer]({BASE})",
        f"- [Full corpus context]({BASE}llms-full.txt): complete text projection",
        f"- [Aggregate manifest]({BASE}objects/daggerheart-system-data.jsonld)",
        f"- [Single-file bundle]({BASE}objects/daggerheart-system-data.bundle.jsonld)",
        f"- [Search index]({BASE}objects/search-index.json)",
        f"- [Collection index]({BASE}objects/collection-index.json)",
        f"- [JSON-LD context]({BASE}systems/context.jsonld)",
        f"- [Vocabulary terms]({BASE}vocab/terms.json)",
        "",
        "## Collections",
        "",
        "Raw records use `objects/<collection>/<slug>.jsonld`; indexable HTML "
        "counterparts use `records/<collection>/<slug>/`. Every JSON-LD record "
        "carries `htmlPage`.",
        "",
    ]
    entity_types = dict(COLLECTIONS)
    for collection, _ in COLLECTIONS:
        guide.append(
            f"- {collection}: {counts[collection]} {entity_types[collection]} records"
        )
    (root / "llms.txt").write_text("\n".join(guide) + "\n", encoding="utf-8")

    full = [
        "# Daggerheart SRD System JSON — full corpus context",
        "",
        "Machine-readable JSON-LD 1.1 reference corpus for the Daggerheart "
        "System Reference Document 2.0.",
        f"Base IRI: {BASE}",
        f"Corpus version: {CORPUS_VERSION}",
        f"Source digest: {manifest['contentDigest']}",
        "",
        f"Attribution: {ATTRIBUTION}",
    ]
    for collection, _ in COLLECTIONS:
        records = [
            json.loads(path.read_text())
            for path in sorted((objects / collection).glob("*.jsonld"))
        ]
        full.append("")
        full.append(f"## Collection: {collection} ({len(records)} records)")
        for record in records:
            full.append("")
            full.append(f"### {record['name']}")
            full.append(f"id: {record['@id'].removeprefix(BASE)}")
            locator = record.get("sourceLocator")
            if locator:
                full.append(
                    f"source: {locator['chapter']} · {locator['heading']} "
                    f"(SRD.md lines {locator['lineStart']}-{locator['lineEnd']}, "
                    f"PDF pages {locator['pdfPageStart']}-{locator['pdfPageEnd']})"
                )
            lines: list[str] = []
            for key, value in record.items():
                if key in SKIP_KEYS:
                    continue
                flatten(value, key, lines)
            full.extend(lines)
    (root / "llms-full.txt").write_text("\n".join(full) + "\n", encoding="utf-8")
    print(f"wrote llms.txt and llms-full.txt ({total} records)")


if __name__ == "__main__":
    main()
