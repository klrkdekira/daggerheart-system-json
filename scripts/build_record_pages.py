#!/usr/bin/env python3
"""Build a crawlable HTML counterpart for every record under records/.

Each page carries a canonical URL, a JSON-LD alternate link, the embedded
record JSON-LD, the source prose (with Markdown pipe tables promoted to HTML
tables), connected-record links, provenance, and the source attribution.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
from pathlib import Path

from build_corpus import ATTRIBUTION, BASE, COLLECTIONS

# Daggerheart "Hope" palette: lavender surfaces, violet ink, gold rules
# (brand colors from daggerheart.com: #160942/#24135F/#6946A6/#E7C74B).
STYLE = (
    "body{font:16px/1.65 system-ui,sans-serif;max-width:70rem;margin:2rem auto;"
    "padding:0 1.2rem;color:#241645;background:#f6f5fb}a{color:#24135f}"
    "h1,h2{font-family:Georgia,serif;color:#24135f}"
    "h1{font-size:2.4rem;margin-bottom:.2rem}"
    "h2{margin-top:2rem;padding-bottom:.25rem;border-bottom:2px solid #c9a227}"
    ".meta{color:#5c5382}"
    ".prose{white-space:pre-wrap;max-width:75ch;font:1.15rem/1.75 Georgia,serif}"
    "dl{display:grid;grid-template-columns:minmax(10rem,auto) 1fr;gap:.35rem 1rem;"
    "background:#fff;border:1px solid #c9c2e4;border-radius:10px;padding:1rem 1.2rem}"
    "dt{font-weight:700;color:#6946a6}dd{margin:0}.tablewrap{overflow:auto}"
    "table{border-collapse:collapse;width:100%;background:#fff}"
    "th,td{border:1px solid #c9c2e4;padding:.45rem;text-align:left}"
    "th{background:#24135f;color:#fdf691}"
    "footer{margin-top:3rem;padding-top:1.5rem;"
    "border-top:1px solid #c9c2e4;color:#5c5382;font-size:.85rem}"
)

FACT_KEYS = [
    ("tier", "Tier"), ("role", "Role"), ("category", "Category"),
    ("difficulty", "Difficulty"), ("thresholds", "Thresholds"),
    ("hitPoints", "HP"), ("stress", "Stress"), ("attackModifier", "ATK"),
    ("experience", "Experience"), ("level", "Level"), ("cardType", "Card Type"),
    ("recallCost", "Recall Cost"), ("startingEvasion", "Starting Evasion"),
    ("startingHitPoints", "Starting Hit Points"), ("classItems", "Class Items"),
    ("spellcastTrait", "Spellcast Trait"), ("trait", "Trait"), ("range", "Range"),
    ("damage", "Damage"), ("burden", "Burden"), ("variant", "Variant"),
    ("baseThresholds", "Base Thresholds"), ("baseScore", "Base Armor Score"),
    ("itemSet", "Set"), ("roll", "Roll"), ("exampleCreatures", "Example Creatures"),
    ("traitBonus", "Trait Bonus"), ("evasionBonus", "Evasion Bonus"),
    ("srdVersion", "SRD Version"), ("license", "License"),
    ("sourceFile", "Source File"), ("contentDigest", "Content Digest"),
    ("pdfFile", "PDF File"), ("pdfDigest", "PDF Digest"),
]

LIST_KEYS = [
    ("motivesAndTactics", "Motives & Tactics"), ("impulses", "Impulses"),
    ("damageTypes", "Damage Types"), ("advantageOn", "Advantage On"),
    ("tieredDamage", "Damage by Tier"),
]

SECTION_LIST_KEYS = [
    ("backgroundQuestions", "Background Questions"),
    ("connections", "Connections"),
    ("questions", "Transformation Questions"),
]

RELATION_KEYS = [
    ("domains", "Domain"), ("domain", "Domain"), ("subclasses", "Subclass"),
    ("parentClass", "Parent class"), ("fromClass", "Class"),
    ("fromSection", "Source section"), ("potentialAdversaries", "Adversary"),
    ("source", "Source"),
]


def esc(value) -> str:
    return html.escape(str(value), quote=False)


def prose_html(text: str) -> str:
    """Escaped prose with pipe tables promoted and markdown markers removed."""
    parts: list[str] = []
    lines = text.split("\n")
    buffer: list[str] = []

    def flush() -> None:
        chunk = "\n".join(buffer).strip("\n")
        if chunk.strip():
            body = esc(chunk)
            body = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", body)
            body = re.sub(r"^#{1,6} (.+)$", r"<strong>\1</strong>", body, flags=re.MULTILINE)
            parts.append(f'<div class=prose>{body}</div>')
        buffer.clear()

    index = 0
    while index < len(lines):
        line = lines[index]
        if line.startswith("|"):
            flush()
            rows = []
            while index < len(lines) and lines[index].startswith("|"):
                cells = [cell.strip() for cell in lines[index].strip("|").split("|")]
                if not all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
                    rows.append(cells)
                index += 1
            head, body_rows = rows[0], rows[1:]
            head_html = "".join(f"<th>{esc(cell)}</th>" for cell in head)
            body_html = "".join(
                "<tr>" + "".join(
                    f"<td>{esc(cell.replace('<br>', '; '))}</td>" for cell in row
                ) + "</tr>"
                for row in body_rows
            )
            parts.append(
                f'<div class=tablewrap><table><thead><tr>{head_html}</tr></thead>'
                f"<tbody>{body_html}</tbody></table></div>"
            )
        else:
            buffer.append(line)
            index += 1
    flush()
    return "".join(parts)


def relation_links(record: dict, names: dict[str, str]) -> str:
    items = []
    for key, label in RELATION_KEYS:
        values = record.get(key)
        if not values:
            continue
        for ref in values if isinstance(values, list) else [values]:
            target = ref["@id"].removeprefix(BASE + "objects/")
            display = names.get(ref["@id"], target)
            items.append(
                f'<li>{esc(label)}: <a href="../../{esc(target.split("/")[0])}/'
                f'{esc(target.split("/")[1])}/">{esc(display)}</a></li>'
            )
    return f"<section><h2>Connected records</h2><ul>{''.join(items)}</ul></section>" if items else ""


def feature_sections(record: dict) -> str:
    parts = []
    entries = []
    if record.get("hopeFeature"):
        entries.append(("Hope Feature", record["hopeFeature"]))
    for feature in record.get("features", []):
        entries.append((None, feature))
    if isinstance(record.get("feature"), dict):
        entries.append((None, record["feature"]))
    for section in record.get("sections", []):
        entries.append((None, section))
    for label, feature in entries:
        title = feature.get("name") or label or "Feature"
        kind = feature.get("kind") or feature.get("stage")
        suffix = f" <span class=meta>({esc(kind)})</span>" if kind else ""
        if label and feature.get("name"):
            suffix += f" <span class=meta>· {esc(label)}</span>"
        parts.append(f"<section><h2>{esc(title)}{suffix}</h2>")
        if feature.get("rulesText"):
            parts.append(prose_html(feature["rulesText"]))
        parts.append("</section>")
    for key, label in SECTION_LIST_KEYS:
        values = record.get(key)
        if values:
            items = "".join(f"<li>{esc(value)}</li>" for value in values)
            parts.append(f"<section><h2>{esc(label)}</h2><ul>{items}</ul></section>")
    return "".join(parts)


def page_html(record: dict, collection: str, names: dict[str, str]) -> str:
    name = record["name"]
    entity = record["@type"]
    locator = record.get("sourceLocator")
    meta_bits = []
    if locator:
        meta_bits.append(
            f"Daggerheart SRD 2.0 · {esc(locator['chapter'])} · {esc(locator['heading'])}"
            f" · PDF p. {locator['pdfPageStart']}"
            + ("" if locator["pdfPageStart"] == locator["pdfPageEnd"]
               else f"–{locator['pdfPageEnd']}")
            + f" · lines {locator['lineStart']}–{locator['lineEnd']}"
        )
    facts = "".join(
        f"<dt>{esc(label)}</dt><dd>{esc(record[key])}</dd>"
        for key, label in FACT_KEYS
        if record.get(key) is not None and not isinstance(record[key], (dict, list))
    )
    facts += "".join(
        f"<dt>{esc(label)}</dt><dd>{esc(', '.join(str(v) for v in record[key]))}</dd>"
        for key, label in LIST_KEYS
        if record.get(key)
    )
    for attack_key, attack_label in (("standardAttack", "Standard Attack"),
                                     ("attack", "Attack")):
        attack = record.get(attack_key)
        if attack:
            line = " · ".join(
                str(attack[part]) for part in ("name", "trait", "range", "damage")
                if attack.get(part)
            )
            facts += f"<dt>{esc(attack_label)}</dt><dd>{esc(line)}</dd>"
    body = []
    if record.get("description"):
        body.append(f"<section><h2>Description</h2>{prose_html(record['description'])}</section>")
    if record.get("rulesText"):
        body.append(f"<section><h2>Source text</h2>{prose_html(record['rulesText'])}</section>")
    body.append(feature_sections(record))
    body.append(relation_links(record, names))
    embedded = json.dumps(record, ensure_ascii=False).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{esc(name)} · Daggerheart SRD 2.0</title>
<meta name="description" content="Human-readable Daggerheart SRD 2.0 {esc(entity)} record for {esc(name)}." />
<link rel="canonical" href="{BASE}records/{collection}/{record["slug"]}/" />
<link rel="alternate" type="application/ld+json" href="../../../objects/{collection}/{record["slug"]}.jsonld" />
<link rel="license" href="https://www.darringtonpress.com/license" />
<script type="application/ld+json">{embedded}</script>
<style>{STYLE}</style></head>
<body><nav><a href="../../../#/{collection}/{record["slug"]}">Corpus explorer</a> · <a href="../../../objects/{collection}/{record["slug"]}.jsonld">Raw JSON-LD</a></nav>
<main><h1>{esc(name)}</h1><p class=meta>{esc(entity)}</p><p class=meta>{"".join(meta_bits)}</p>
{f'<section><h2>At a glance</h2><dl>{facts}</dl></section>' if facts else ''}
{''.join(body)}</main>
<footer>{esc(ATTRIBUTION)}</footer></body></html>
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    root = args.root
    records_dir = root / "records"
    if records_dir.exists():
        shutil.rmtree(records_dir)
    names: dict[str, str] = {}
    loaded: dict[str, list[dict]] = {}
    for collection, _ in COLLECTIONS:
        loaded[collection] = [
            json.loads(path.read_text())
            for path in sorted((root / "objects" / collection).glob("*.jsonld"))
        ]
        for record in loaded[collection]:
            names[record["@id"]] = record["name"]
    total = 0
    for collection, _ in COLLECTIONS:
        for record in loaded[collection]:
            page_dir = records_dir / collection / record["slug"]
            page_dir.mkdir(parents=True)
            (page_dir / "index.html").write_text(
                page_html(record, collection, names), encoding="utf-8"
            )
            total += 1
    print(f"wrote {total} record pages")


if __name__ == "__main__":
    main()
