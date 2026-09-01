#!/usr/bin/env python3
"""Build the explorer's browse and search indexes from the emitted records.

- objects/collection-index.json: per-collection display metadata
  ({slug, name, sub, group}) in browse order, used by the explorer's list pane.
- objects/search-index.json: a static inverted token index over every record's
  name and text fields ({base, documents, tokens}), used by full-text search.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import build_corpus
from build_corpus import BASE, COLLECTIONS

EXCERPT_LENGTH = 110
TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9'’-]{2,}")

TEXT_KEYS = {
    "name", "description", "rulesText", "classItems", "spellcastTrait",
    "exampleCreatures", "experience", "potentialAdversariesText",
    "attributionStatement",
}
TEXT_LIST_KEYS = {
    "backgroundQuestions", "connections", "questions", "motivesAndTactics",
    "impulses", "advantageOn",
}


def load_records(objects: Path) -> dict[str, list[dict]]:
    return {
        collection: [
            json.loads(path.read_text())
            for path in sorted((objects / collection).glob("*.jsonld"))
        ]
        for collection, _ in COLLECTIONS
    }


def text_fragments(record: dict) -> list[str]:
    fragments: list[str] = []

    def walk(value) -> None:
        if isinstance(value, dict):
            for key, sub in value.items():
                if key in TEXT_KEYS and isinstance(sub, str):
                    fragments.append(sub)
                elif key in TEXT_LIST_KEYS and isinstance(sub, list):
                    fragments.extend(item for item in sub if isinstance(item, str))
                elif isinstance(sub, (dict, list)):
                    walk(sub)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(record)
    return fragments


# --- collection index ---------------------------------------------------------


def feature_names(record: dict) -> str:
    return ", ".join(
        feature["name"]
        for feature in record.get("features", [])
        if feature.get("name")
    )


def weapon_sub(record: dict) -> str:
    damage = record.get("damage") or "; ".join(record.get("tieredDamage", []))
    parts = [record.get("trait"), record.get("range"), damage, record.get("burden")]
    return " · ".join(part for part in parts if part)


def variant_label(variant: str) -> str:
    return {
        "core": "Core",
        "combat-wheelchair": "Combat Wheelchair",
        "everyday-hero": "Everyday Hero",
        "western": "Western",
        "monster-hunting": "Monster Hunting",
    }[variant]


def entry(record: dict, sub: str, group: str) -> dict:
    return {"slug": record["slug"], "name": record["name"], "sub": sub, "group": group}


def collection_entries(collection: str, records: list[dict],
                       names: dict[str, str]) -> list[dict]:
    def by_tier(record: dict) -> tuple:
        return (record.get("tier", 0), record["name"])

    if collection == "sources":
        return [entry(r, r["license"], "Sources") for r in records]
    if collection == "domains":
        return [
            entry(r, r["description"][:EXCERPT_LENGTH], "Domains")
            for r in sorted(records, key=lambda r: r["name"])
        ]
    if collection == "classes":
        return [
            entry(r, "Domains: " + " & ".join(
                names[d["@id"]] for d in r["domains"]), "Classes")
            for r in sorted(records, key=lambda r: r["name"])
        ]
    if collection == "subclasses":
        return [
            entry(r, feature_names(r), names[r["parentClass"]["@id"]])
            for r in sorted(
                records, key=lambda r: (names[r["parentClass"]["@id"]], r["name"])
            )
        ]
    if collection in {"ancestries", "communities", "transformations"}:
        label = collection.capitalize()
        return [
            entry(r, r.get("feature", {}).get("name") or feature_names(r), label)
            for r in sorted(records, key=lambda r: r["name"])
        ]
    if collection == "beastforms":
        return [
            entry(r, r.get("exampleCreatures", ""), f"Tier {r['tier']}")
            for r in sorted(records, key=by_tier)
        ]
    if collection == "weapons":
        ordered = sorted(records, key=lambda r: (
            list(variant_label(v) for v in [r["variant"]])[0] != "Core",
            r["variant"], r["category"], r.get("tier", 0), r["name"]))
        return [
            entry(r, weapon_sub(r),
                  f"{variant_label(r['variant'])} · {r['category'].capitalize()}"
                  + (f" · Tier {r['tier']}" if "tier" in r else ""))
            for r in ordered
        ]
    if collection == "armor":
        ordered = sorted(records, key=lambda r: (
            r["variant"] != "core", r["variant"], r.get("tier", 0), r["name"]))
        return [
            entry(r, f"{r['baseThresholds']} · Score {r['baseScore']}",
                  variant_label(r["variant"])
                  + (f" · Tier {r['tier']}" if "tier" in r else ""))
            for r in ordered
        ]
    if collection in {"items", "consumables"}:
        sets = {"core-set": "Core Set", "expansion": "Hope & Fear Expansion"}
        return [
            entry(r, f"Roll {r['roll']:02d} · {r['description'][:EXCERPT_LENGTH]}",
                  sets[r["itemSet"]])
            for r in sorted(records, key=lambda r: (r["itemSet"] != "core-set", r["roll"]))
        ]
    if collection == "adversaries":
        return [
            entry(r, f"Tier {r['tier']} {r['role']}"
                  + (f" · Difficulty {r['difficulty']}" if "difficulty" in r else ""),
                  f"Tier {r['tier']}")
            for r in sorted(records, key=by_tier)
        ]
    if collection == "environments":
        return [
            entry(r, f"Tier {r['tier']} {r['category']}"
                  + (f" · Difficulty {r['difficulty']}" if "difficulty" in r else ""),
                  f"Tier {r['tier']}")
            for r in sorted(records, key=by_tier)
        ]
    if collection == "domain-cards":
        return [
            entry(r, f"Level {r['level']} {r['cardType']} · Recall {r['recallCost']}",
                  names[r["domain"]["@id"]])
            for r in sorted(
                records,
                key=lambda r: (names[r["domain"]["@id"]], r["level"], r["name"]),
            )
        ]
    if collection == "rules":
        ordered = sorted(records, key=lambda r: r["sourceLocator"]["lineStart"])
        return [
            entry(r, f"PDF p. {r['sourceLocator']['pdfPageStart']}",
                  r["sourceLocator"]["chapter"].title())
            for r in ordered
        ]
    raise SystemExit(f"no browse order for collection: {collection}")


# --- search index -------------------------------------------------------------


def build_search_index(by_collection: dict[str, list[dict]]) -> dict:
    documents: list[dict] = []
    tokens: dict[str, list[dict]] = {}
    for collection, _ in COLLECTIONS:
        for record in by_collection[collection]:
            fragments = text_fragments(record)
            body = "\n".join(fragments)
            excerpt = ""
            for fragment in fragments:
                if fragment != record["name"] and fragment.strip():
                    excerpt = fragment[:EXCERPT_LENGTH].strip()
                    break
            document_index = len(documents)
            documents.append({
                "id": record["@id"].removeprefix(BASE),
                "type": record["@type"],
                "name": record["name"],
                "excerpt": excerpt,
            })
            lowered = body.casefold()
            seen: dict[str, str] = {}
            for match in TOKEN_PATTERN.finditer(lowered):
                token = match.group().strip("'’-")
                if len(token) < 3 or token in seen:
                    continue
                window_start = max(0, match.start() - 40)
                window = body[window_start : match.start() + 70]
                seen[token] = " ".join(window.split())
            for token, token_excerpt in sorted(seen.items()):
                tokens.setdefault(token, []).append(
                    {"document": document_index, "excerpt": token_excerpt}
                )
    return {
        "base": BASE,
        "documents": documents,
        "tokens": {token: tokens[token] for token in sorted(tokens)},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    objects = args.root / "objects"
    by_collection = load_records(objects)
    names = {
        record["@id"]: record["name"]
        for records in by_collection.values()
        for record in records
    }
    collection_index = {
        "collections": {
            collection: collection_entries(collection, records, names)
            for collection, records in by_collection.items()
        }
    }
    build_corpus.dump(objects / "collection-index.json", collection_index)
    search_index = build_search_index(by_collection)
    build_corpus.dump(objects / "search-index.json", search_index)
    total = sum(len(records) for records in by_collection.values())
    print(
        f"indexed {total} records: {len(search_index['tokens'])} search tokens, "
        f"{len(collection_index['collections'])} browse collections"
    )


if __name__ == "__main__":
    main()
