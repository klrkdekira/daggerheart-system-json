#!/usr/bin/env python3
"""Build the dereferenceable vocabulary: vocab/terms.json and vocab/index.html.

Classes come from the collection entity types; properties come from the
JSON-LD context. Every property records its JSON term(s), object kind, and a
description, and every emitted record key must resolve to a documented term.
"""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

from build_corpus import BASE, COLLECTIONS

VOCAB = BASE + "vocab/#"

CLASS_DESCRIPTIONS = {
    "Source": "The Daggerheart SRD source document record.",
    "Domain": "One of the ten magic domains.",
    "CharacterClass": "A playable class with starting stats and features.",
    "Subclass": "A subclass with foundation, specialization, and mastery features.",
    "Ancestry": "A heritage ancestry with its features.",
    "Community": "A heritage community with its feature.",
    "Transformation": "An optional transformation with features and questions.",
    "Beastform": "A Druid Beastform with stats, attack, and features.",
    "Weapon": "One weapon table row across all variants and tiers.",
    "Armor": "One armor table row across all variants and tiers.",
    "Item": "One reusable loot item with its roll number.",
    "Consumable": "One single-use consumable with its roll number.",
    "Adversary": "A decomposed adversary stat block.",
    "Environment": "A decomposed environment stat block.",
    "DomainCard": "A domain card with level, type, and recall cost.",
    "Rule": "Source-faithful prose for a section not covered by a typed record.",
    "Manifest": "The aggregate collection manifest.",
    "Bundle": "The single-file JSON-LD graph bundle.",
}

PROPERTY_DESCRIPTIONS = {
    "name": "Display name of the entity.",
    "description": "Source descriptive prose.",
    "slug": "Stable lowercase-kebab-case identifier.",
    "rulesText": "Source rules wording, preserved verbatim.",
    "source": "The SRD source record this entity derives from.",
    "htmlPage": "Crawlable HTML counterpart of this record.",
    "sourceLocator": "Chapter, heading, SRD.md line span, and PDF page span.",
    "license": "License code of the source content.",
    "licenseUrl": "License URL of the source content.",
    "attributionStatement": "Verbatim source attribution statement.",
    "domains": "Magic domains a class grants access to.",
    "domain": "The magic domain a card belongs to.",
    "classes": "Related character classes.",
    "parentClass": "The class a subclass refines.",
    "subclasses": "Subclasses belonging to a class.",
    "fromClass": "The class that grants this entity.",
    "fromSection": "The rule section whose table this entity was extracted from.",
    "potentialAdversaries": "Adversaries named by an environment stat block.",
    "cardsInDomain": "Reverse of domain: cards that belong to a domain.",
    "subclassOf": "Reverse of subclass: the class listing this subclass.",
    "beastformsOfClass": "Reverse of fromClass: beastforms granted by a class.",
    "appearsInEnvironment": "Reverse of potentialAdversary: environments naming an adversary.",
    "sectionEntities": "Reverse of fromSection: entities extracted from a section.",
    "tier": "Play tier (1-4).",
    "level": "Card level (1-10).",
    "cardType": "Domain card type: Ability, Spell, or Grimoire.",
    "recallCost": "Stress cost to recall the card from the vault.",
    "role": "Adversary role (Solo, Leader, Horde, ...).",
    "category": "Weapon slot (primary/secondary) or environment type.",
    "variant": "Equipment variant (core, combat-wheelchair, everyday-hero, western, monster-hunting).",
    "trait": "Character trait used with the entity.",
    "range": "Printed range.",
    "damage": "Printed damage expression.",
    "tieredDamage": "Per-tier damage expressions.",
    "damageTypes": "Damage types dealt (physical, magic).",
    "burden": "Hands occupied when equipped.",
    "feature": "A single named feature.",
    "features": "Ordered named features.",
    "sections": "Ordered untyped subsections retained with the entity.",
    "kind": "Feature kind (Passive, Action, Reaction, ...).",
    "stage": "Subclass feature stage (foundation, specialization, mastery).",
    "baseThresholds": "Printed base damage thresholds.",
    "baseScore": "Printed base armor score.",
    "roll": "Loot table roll number.",
    "itemSet": "Loot set provenance (core-set, expansion).",
    "startingEvasion": "Class starting Evasion.",
    "startingHitPoints": "Class starting Hit Points.",
    "classItems": "Printed class item options.",
    "hopeFeature": "The class Hope feature.",
    "backgroundQuestions": "Printed background questions.",
    "connections": "Printed connection questions.",
    "spellcastTrait": "Subclass Spellcast trait.",
    "questions": "Printed transformation questions.",
    "exampleCreatures": "Printed example creatures for a beastform.",
    "traitBonus": "Beastform trait bonus.",
    "evasionBonus": "Beastform Evasion bonus.",
    "attack": "Beastform attack statistics.",
    "advantageOn": "Verbs a beastform gains advantage on.",
    "motivesAndTactics": "Printed adversary motives and tactics.",
    "impulses": "Printed environment impulses.",
    "difficulty": "Printed difficulty value.",
    "thresholds": "Printed damage thresholds.",
    "hitPoints": "Adversary Hit Points.",
    "stress": "Adversary Stress.",
    "attackModifier": "Adversary attack modifier, as printed.",
    "standardAttack": "Adversary standard attack statistics.",
    "experience": "Printed adversary Experience modifiers.",
    "potentialAdversariesText": "Printed potential adversaries line, verbatim.",
    "collections": "Collection descriptors in the manifest.",
    "members": "Member records of a collection.",
    "schemaReference": "JSON Schema contract for a collection.",
    "entityType": "JSON-LD entity type of a collection.",
    "count": "Member count of a collection.",
    "contentDigest": "SHA-256 digest of the source markdown.",
    "sourceFile": "Filename of the source markdown.",
    "srdVersion": "Version of the source SRD.",
    "corpusVersion": "Version of this corpus.",
    "pdfFile": "Filename of the official source PDF.",
    "pdfDigest": "Registered SHA-256 digest of the official source PDF.",
    "recordCount": "Total record count in the manifest.",
}

NODE_KINDS = {
    "source", "htmlPage", "domains", "domain", "classes", "parentClass",
    "subclasses", "fromClass", "fromSection", "potentialAdversaries",
    "cardsInDomain", "subclassOf", "beastformsOfClass", "appearsInEnvironment",
    "sectionEntities", "members", "schemaReference",
}
STRUCTURED_KINDS = {
    "sourceLocator", "feature", "features", "sections", "hopeFeature",
    "attack", "standardAttack", "collections",
}


def build_terms(context: dict) -> dict:
    terms = context["@context"]
    classes = sorted(
        {entity for _, entity in COLLECTIONS} | {"Manifest", "Bundle"}
    )
    class_entries = [
        {
            "iri": VOCAB + name,
            "anchor": name,
            "description": CLASS_DESCRIPTIONS[name],
        }
        for name in classes
    ]
    property_entries = []
    documented = dict(PROPERTY_DESCRIPTIONS)
    for term, definition in sorted(terms.items()):
        if term.startswith("@") or term in {"dh", "schema", "dcterms"}:
            continue
        if term not in documented:
            raise SystemExit(f"context term without a vocabulary description: {term}")
        if isinstance(definition, dict):
            mapped = definition.get("@reverse") or definition.get("@id") or term
        else:
            mapped = definition
        if term in NODE_KINDS:
            kinds = ["node reference"]
        elif term in STRUCTURED_KINDS:
            kinds = ["structured value"]
        else:
            kinds = ["literal"]
        entry = {
            "iri": VOCAB + term if mapped.startswith("dh:") else mapped.replace(
                "schema:", "https://schema.org/"
            ).replace("dcterms:", "http://purl.org/dc/terms/"),
            "anchor": term,
            "jsonTerms": [term],
            "mapsTo": mapped,
            "valueKinds": kinds,
            "description": documented[term],
        }
        if isinstance(definition, dict) and "@reverse" in definition:
            entry["reverseOf"] = definition["@reverse"]
        property_entries.append(entry)
    return {
        "vocabulary": VOCAB,
        "classes": class_entries,
        "properties": property_entries,
    }


def build_html(terms: dict) -> str:
    rows_classes = "\n".join(
        f'<tr id="{html.escape(entry["anchor"])}"><td><code>{html.escape(entry["anchor"])}</code></td>'
        f"<td>{html.escape(entry['description'])}</td></tr>"
        for entry in terms["classes"]
    )
    rows_properties = "\n".join(
        f'<tr id="{html.escape(entry["anchor"])}"><td><code>{html.escape(entry["anchor"])}</code></td>'
        f"<td><code>{html.escape(entry['mapsTo'])}</code></td>"
        f"<td>{html.escape(', '.join(entry['valueKinds']))}</td>"
        f"<td>{html.escape(entry['description'])}</td></tr>"
        for entry in terms["properties"]
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Vocabulary · Daggerheart SRD System JSON</title>
<meta name="description" content="Dereferenceable classes and properties of the Daggerheart SRD System JSON vocabulary." />
<link rel="canonical" href="{BASE}vocab/" />
<link rel="alternate" type="application/json" href="terms.json" />
<style>body{{font:16px/1.65 system-ui,sans-serif;max-width:72rem;margin:2rem auto;padding:0 1.2rem;color:#241645;background:#f6f5fb}}a{{color:#24135f}}h1,h2{{font-family:Georgia,serif;color:#24135f}}h2{{padding-bottom:.25rem;border-bottom:2px solid #c9a227}}table{{border-collapse:collapse;width:100%;margin:1rem 0 2rem;background:#fff}}th,td{{border:1px solid #c9c2e4;padding:.5rem .6rem;text-align:left;vertical-align:top}}th{{background:#24135f;color:#fdf691}}code{{background:#ece9f6;padding:.08rem .3rem;border-radius:4px}}footer{{margin-top:3rem;padding-top:1.5rem;border-top:1px solid #c9c2e4;color:#5c5382;font-size:.85rem}}</style></head>
<body><nav><a href="../">Corpus explorer</a> · <a href="terms.json">terms.json</a></nav>
<h1>Vocabulary</h1>
<p>Classes and properties under <code>{VOCAB}</code>, as used by the
<a href="../">Daggerheart SRD System JSON</a> corpus. Fragment identifiers on this
page dereference each term. The machine-readable projection is
<a href="terms.json">terms.json</a>.</p>
<h2>Classes ({len(terms["classes"])})</h2>
<table><thead><tr><th>Class</th><th>Description</th></tr></thead><tbody>
{rows_classes}
</tbody></table>
<h2>Properties ({len(terms["properties"])})</h2>
<table><thead><tr><th>Term</th><th>Maps to</th><th>Value kind</th><th>Description</th></tr></thead><tbody>
{rows_properties}
</tbody></table>
<footer>This work includes material from the Daggerheart System Reference Document 2.0,
© 2026 Critical Role LLC, used as Public Game Content per the Darrington Press
Community Gaming License (www.darringtonpress.com/license).</footer></body></html>
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    context = json.loads((args.root / "systems" / "context.jsonld").read_text())
    terms = build_terms(context)
    vocab_dir = args.root / "vocab"
    vocab_dir.mkdir(exist_ok=True)
    (vocab_dir / "terms.json").write_text(
        json.dumps(terms, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (vocab_dir / "index.html").write_text(build_html(terms), encoding="utf-8")
    print(
        f"wrote vocab: {len(terms['classes'])} classes, "
        f"{len(terms['properties'])} properties"
    )


if __name__ == "__main__":
    main()
