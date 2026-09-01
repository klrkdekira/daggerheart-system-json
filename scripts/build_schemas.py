#!/usr/bin/env python3
"""Generate the JSON Schema (Draft 2020-12) contracts under systems/.

Schemas are derived from one declarative table so that record shapes,
validation, and documentation stay in agreement. Leaf entity schemas reject
unknown properties.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

BASE = "https://cheeleong.dev/daggerheart-system-json/"
DRAFT = "https://json-schema.org/draft/2020-12/schema"

node_ref = {"$ref": "common.schema.json#/$defs/nodeRef"}
node_refs = {"type": "array", "items": node_ref, "minItems": 1}
string = {"type": "string", "minLength": 1}
integer = {"type": "integer"}
feature = {"$ref": "common.schema.json#/$defs/feature"}
features = {"type": "array", "items": feature}

COMMON = {
    "$schema": DRAFT,
    "$id": BASE + "systems/common.schema.json",
    "$defs": {
        "nodeRef": {
            "type": "object",
            "properties": {
                "@id": {"type": "string", "pattern": "^https://cheeleong\\.dev/daggerheart-system-json/objects/[a-z-]+/[a-z0-9-]+$"}
            },
            "required": ["@id"],
            "additionalProperties": False,
        },
        "sourceLocator": {
            "type": "object",
            "properties": {
                "chapter": string,
                "heading": string,
                "lineStart": {"type": "integer", "minimum": 1},
                "lineEnd": {"type": "integer", "minimum": 1},
                "pdfPageStart": {"type": "integer", "minimum": 1},
                "pdfPageEnd": {"type": "integer", "minimum": 1},
            },
            "required": ["chapter", "heading", "lineStart", "lineEnd",
                         "pdfPageStart", "pdfPageEnd"],
            "additionalProperties": False,
        },
        "feature": {
            "type": "object",
            "properties": {
                "name": string,
                "kind": string,
                "stage": {"enum": ["foundation", "specialization", "mastery"]},
                "rulesText": {"type": "string"},
            },
            "required": ["rulesText"],
            "additionalProperties": False,
        },
        "attack": {
            "type": "object",
            "properties": {
                "name": string,
                "range": string,
                "trait": string,
                "damage": string,
            },
            "required": ["range", "damage"],
            "additionalProperties": False,
        },
        "pageRef": {
            "type": "object",
            "properties": {
                "@id": {"type": "string", "pattern": "^https://cheeleong\\.dev/daggerheart-system-json/records/[a-z-]+/[a-z0-9-]+/$"}
            },
            "required": ["@id"],
            "additionalProperties": False,
        },
    },
}


def entity_schema(entity_type: str, fields: dict, required: list[str]) -> dict:
    properties = {
        "@context": {"const": BASE + "systems/context.jsonld"},
        "@id": {"type": "string", "pattern": "^https://cheeleong\\.dev/daggerheart-system-json/objects/[a-z-]+/[a-z0-9-]+$"},
        "@type": {"const": entity_type},
        "name": string,
        "slug": {"type": "string", "pattern": "^[a-z0-9-]+$"},
        "source": node_ref,
        "sourceLocator": {"$ref": "common.schema.json#/$defs/sourceLocator"},
        "htmlPage": {"$ref": "common.schema.json#/$defs/pageRef"},
        "fromSection": node_ref,
    }
    properties.update(fields)
    return {
        "$schema": DRAFT,
        "$id": f"{BASE}systems/{entity_type.casefold()}.schema.json",
        "type": "object",
        "properties": properties,
        "required": ["@context", "@id", "@type", "name", "slug", "source",
                     "sourceLocator", "htmlPage", *required],
        "additionalProperties": False,
    }


SCHEMAS: dict[str, dict] = {
    "common": COMMON,
    "source": {
        "$schema": DRAFT,
        "$id": BASE + "systems/source.schema.json",
        "type": "object",
        "properties": {
            "@context": {"const": BASE + "systems/context.jsonld"},
            "@id": {"const": BASE + "objects/sources/daggerheart-srd-2-0"},
            "@type": {"const": "Source"},
            "name": string,
            "slug": {"const": "daggerheart-srd-2-0"},
            "srdVersion": string,
            "sourceFile": {"const": "SRD.md"},
            "contentDigest": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
            "pdfFile": string,
            "pdfDigest": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
            "license": string,
            "licenseUrl": {
                "type": "object",
                "properties": {"@id": string},
                "required": ["@id"],
                "additionalProperties": False,
            },
            "attributionStatement": string,
            "htmlPage": {"$ref": "common.schema.json#/$defs/pageRef"},
        },
        "required": ["@context", "@id", "@type", "name", "slug", "srdVersion",
                     "sourceFile", "contentDigest", "pdfFile", "pdfDigest",
                     "license", "licenseUrl", "attributionStatement", "htmlPage"],
        "additionalProperties": False,
    },
    "domain": entity_schema("Domain", {"description": string}, ["description"]),
    "characterclass": entity_schema("CharacterClass", {
        "description": string,
        "domains": node_refs,
        "subclasses": node_refs,
        "startingEvasion": integer,
        "startingHitPoints": integer,
        "hopeFeature": feature,
        "features": features,
        "classItems": string,
        "backgroundQuestions": {"type": "array", "items": string},
        "connections": {"type": "array", "items": string},
        "sections": features,
    }, ["domains", "subclasses", "startingEvasion", "startingHitPoints",
        "hopeFeature", "features"]),
    "subclass": entity_schema("Subclass", {
        "description": string,
        "parentClass": node_ref,
        "spellcastTrait": string,
        "features": features,
    }, ["parentClass", "features"]),
    "ancestry": entity_schema("Ancestry", {
        "description": string,
        "features": features,
    }, ["description"]),
    "community": entity_schema("Community", {
        "description": string,
        "feature": feature,
    }, ["description"]),
    "transformation": entity_schema("Transformation", {
        "description": string,
        "features": features,
        "questions": {"type": "array", "items": string},
    }, ["description", "features"]),
    "beastform": entity_schema("Beastform", {
        "tier": integer,
        "fromClass": node_ref,
        "description": string,
        "exampleCreatures": string,
        "traitBonus": string,
        "evasionBonus": integer,
        "attack": {"$ref": "common.schema.json#/$defs/attack"},
        "advantageOn": {"type": "array", "items": string},
        "features": features,
    }, ["tier", "fromClass"]),
    "weapon": entity_schema("Weapon", {
        "tier": integer,
        "category": {"enum": ["primary", "secondary"]},
        "variant": {"enum": ["core", "combat-wheelchair", "everyday-hero",
                             "western", "monster-hunting"]},
        "trait": string,
        "range": string,
        "damage": string,
        "tieredDamage": {"type": "array", "items": string},
        "damageTypes": {"type": "array",
                        "items": {"enum": ["physical", "magic"]}},
        "burden": string,
        "feature": feature,
    }, ["category", "variant", "trait", "range"]),
    "armor": entity_schema("Armor", {
        "tier": integer,
        "variant": {"enum": ["core", "everyday-hero", "monster-hunting"]},
        "baseThresholds": string,
        "baseScore": string,
        "feature": feature,
    }, ["variant", "baseThresholds", "baseScore"]),
    "item": entity_schema("Item", {
        "itemSet": {"enum": ["core-set", "expansion"]},
        "roll": integer,
        "description": string,
    }, ["itemSet", "roll", "description"]),
    "consumable": entity_schema("Consumable", {
        "itemSet": {"enum": ["core-set", "expansion"]},
        "roll": integer,
        "description": string,
    }, ["itemSet", "roll", "description"]),
    "adversary": entity_schema("Adversary", {
        "tier": integer,
        "role": string,
        "description": string,
        "motivesAndTactics": {"type": "array", "items": string},
        "difficulty": {"type": ["integer", "string"]},
        "thresholds": string,
        "hitPoints": integer,
        "stress": {"type": ["integer", "string"]},
        "attackModifier": string,
        "standardAttack": {"$ref": "common.schema.json#/$defs/attack"},
        "experience": string,
        "features": features,
    }, ["tier", "role", "features"]),
    "environment": entity_schema("Environment", {
        "tier": integer,
        "category": {"enum": ["Exploration", "Event", "Social", "Traversal"]},
        "description": string,
        "impulses": {"type": "array", "items": string},
        "difficulty": {"type": ["integer", "string"]},
        "potentialAdversariesText": string,
        "potentialAdversaries": node_refs,
        "features": features,
    }, ["tier", "category", "features"]),
    "domaincard": entity_schema("DomainCard", {
        "level": integer,
        "domain": node_ref,
        "cardType": {"enum": ["Ability", "Spell", "Grimoire"]},
        "recallCost": integer,
        "rulesText": string,
    }, ["level", "domain", "cardType", "recallCost", "rulesText"]),
    "rule": entity_schema("Rule", {"rulesText": {"type": "string"}}, ["rulesText"]),
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    systems = args.root / "systems"
    systems.mkdir(exist_ok=True)
    for name, schema in SCHEMAS.items():
        path = systems / f"{name}.schema.json"
        path.write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    print(f"wrote {len(SCHEMAS)} schemas")


if __name__ == "__main__":
    main()
