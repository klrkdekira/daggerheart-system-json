#!/usr/bin/env python3
"""Build the Daggerheart SRD JSON-LD corpus from SRD.md.

One JSON-LD record per reusable entity under
objects/<collection>/<slug>.jsonld, plus a manifest, a single-file bundle, and
build metrics. SRD.md is the sole content source; every record carries a
line-level source locator and the PDF pages it came from.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

BASE = "https://cheeleong.dev/daggerheart-system-json/"
CONTEXT = BASE + "systems/context.jsonld"
SOURCE_SLUG = "daggerheart-srd-2-0"
SOURCE_ID = BASE + "objects/sources/" + SOURCE_SLUG
CORPUS_VERSION = "0.1.0"
PDF_NAME = "DH_SRD_2_2026_08_25.pdf"
# Registered digest of the official SRD 2.0 PDF; the PDF itself is not
# distributed with the repository. When the file is present locally its
# digest must match; clean rebuilds elsewhere rely on the registered value.
PDF_DIGEST = "sha256:55d8b92b7e58aa1da99a4a59aa77352483ef4fbda71baddb9af9bfc1f333bd2a"

CLASS_NAMES = [
    "ASSASSIN", "BARD", "BRAWLER", "DRUID", "GUARDIAN", "RANGER", "ROGUE",
    "SERAPH", "SORCERER", "WARLOCK", "WARRIOR", "WITCH", "WIZARD",
]
DOMAIN_NAMES = [
    "ARCANA", "BLADE", "BONE", "CODEX", "DREAD", "GRACE", "MIDNIGHT",
    "SAGE", "SPLENDOR", "VALOR",
]
ANCESTRY_NAMES = [
    "AETHERIS", "CLANK", "DRAKONA", "DWARF", "EARTHKIN", "ELF", "EMBERKIN",
    "FAERIE", "FAUN", "FIRBOLG", "FUNGRIL", "GALAPA", "GIANT", "GNOME",
    "GOBLIN", "HALFLING", "HUMAN", "INFERNIS", "KATARI", "ORC", "RIBBET",
    "SIMIAH", "SKYKIN", "TIDEKIN", "MIXED ANCESTRY",
]
TRANSFORMATION_NAMES = [
    "DEMIGOD", "GHOST", "REANIMATED", "SHAPESHIFTER", "VAMPIRE", "WEREWOLF",
]
ENVIRONMENT_CATEGORIES = {"Exploration", "Event", "Social", "Traversal"}
MINOR_WORDS = {"a", "an", "and", "as", "at", "by", "for", "from", "in", "of",
               "on", "or", "the", "to", "with"}

COLLECTIONS = [
    ("sources", "Source"),
    ("domains", "Domain"),
    ("classes", "CharacterClass"),
    ("subclasses", "Subclass"),
    ("ancestries", "Ancestry"),
    ("communities", "Community"),
    ("transformations", "Transformation"),
    ("beastforms", "Beastform"),
    ("weapons", "Weapon"),
    ("armor", "Armor"),
    ("items", "Item"),
    ("consumables", "Consumable"),
    ("adversaries", "Adversary"),
    ("environments", "Environment"),
    ("domain-cards", "DomainCard"),
    ("rules", "Rule"),
]

ATTRIBUTION = (
    "This document, including the Witherwild Campaign Frame, is considered "
    "Public Game Content per the Darrington Press Community Gaming License. "
    "© 2026 Critical Role LLC. All rights reserved. For more information, "
    "please visit www.darringtonpress.com/license."
)


# --- source model -----------------------------------------------------------


class Doc:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.text = (root / "SRD.md").read_text(encoding="utf-8")
        self.lines = self.text.split("\n")
        self.pages: list[int] = []
        self.comment: list[bool] = []
        page = 0
        in_comment = False
        for line in self.lines:
            marker = re.match(r"<!-- PDF page (\d+) -->", line)
            if marker:
                page = int(marker.group(1))
            self.pages.append(page)
            starts = line.lstrip().startswith("<!--")
            self.comment.append(in_comment or starts)
            if (in_comment or starts) and "-->" not in line:
                in_comment = True
            elif "-->" in line:
                in_comment = False

        self.headings: list[tuple[int, int, str]] = []
        for index, line in enumerate(self.lines):
            match = re.match(r"(#{1,6}) (.+)$", line)
            if match:
                self.headings.append((index, len(match.group(1)), match.group(2)))

    def is_content(self, index: int) -> bool:
        return bool(self.lines[index].strip()) and not self.comment[index]

    def section_end(self, heading_index: int) -> int:
        """Exclusive end line of the section starting at headings[heading_index]."""
        start, level, _ = self.headings[heading_index]
        for index, other_level, _ in self.headings[heading_index + 1 :]:
            if other_level <= level:
                return index
        return len(self.lines)

    def body(self, start: int, end: int) -> str:
        kept = [
            line
            for index, line in enumerate(self.lines[start:end], start)
            if not self.comment[index]
        ]
        text = "\n".join(kept).strip("\n")
        return re.sub(r"\n{3,}", "\n\n", text)

    def locator(self, chapter: str, heading: str, start: int, end: int) -> dict:
        """1-based inclusive line span; `end` is the exclusive 0-based bound."""
        last = end - 1
        while last > start and not self.is_content(last):
            last -= 1
        while start < last and not self.is_content(start):
            start += 1
        return {
            "chapter": chapter,
            "heading": heading,
            "lineStart": start + 1,
            "lineEnd": last + 1,
            "pdfPageStart": self.pages[start],
            "pdfPageEnd": self.pages[last],
        }

    def chapter_at(self, line_index: int) -> str:
        chapter = "DAGGERHEART"
        for index, level, text in self.headings:
            if index > line_index:
                break
            if level == 2:
                chapter = text
        return chapter


def slugify(name: str) -> str:
    text = name.casefold().replace("’", "").replace("'", "")
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def title_name(heading: str) -> str:
    words = heading.split(" ")
    result = []
    for index, word in enumerate(words):
        lowered = word.casefold()
        if 0 < index < len(words) - 1 and lowered in MINOR_WORDS:
            result.append(lowered)
        else:
            result.append("-".join(
                part[:1].upper() + part[1:].casefold() for part in word.split("-")
            ))
    return " ".join(result)


def strip_markup(text: str) -> str:
    return text.replace("**", "").replace("*", "")


def blocks_of(text: str) -> list[str]:
    return [block for block in text.split("\n\n") if block.strip()]


def ref(collection: str, slug: str) -> dict:
    return {"@id": f"{BASE}objects/{collection}/{slug}"}


def parse_features(blocks: list[str]) -> tuple[list[dict], list[str]]:
    """Split paragraphs into bold-led features; return (features, preamble)."""
    features: list[dict] = []
    preamble: list[str] = []
    for block in blocks:
        match = re.match(r"\*\*([^*]+?):?\*\* ?(.*)", block, re.DOTALL)
        if match:
            label = match.group(1).rstrip(":")
            feature = {"name": label}
            kind_match = re.match(r"(.*) - (\w+)$", label)
            if kind_match:
                feature["name"] = kind_match.group(1)
                feature["kind"] = kind_match.group(2)
            feature["rulesText"] = strip_markup(match.group(2)).strip()
            features.append(feature)
        elif features:
            features[-1]["rulesText"] = (
                features[-1]["rulesText"] + "\n\n" + strip_markup(block)
            ).strip()
        else:
            preamble.append(strip_markup(block))
    return features, preamble


def parse_bullets(text: str) -> list[str]:
    return [
        strip_markup(re.sub(r"^\s*- ", "", line)).strip()
        for line in text.split("\n")
        if line.lstrip().startswith("- ")
    ]


def parse_pipe_table(lines: list[str], start: int) -> tuple[list[str], list[list[str]], int]:
    """Parse a pipe table at lines[start]; return (headers, row-(line, cells)s, end)."""
    def cells(line: str) -> list[str]:
        return [cell.strip() for cell in line.strip().strip("|").split("|")]

    headers = cells(lines[start])
    index = start + 1
    if index < len(lines) and re.fullmatch(r"\|(?: --- \|)+", lines[index]):
        index += 1
    rows: list[list] = []
    while index < len(lines) and lines[index].startswith("|"):
        rows.append([index, cells(lines[index])])
        index += 1
    return headers, rows, index


# --- corpus builder ---------------------------------------------------------


class Corpus:
    def __init__(self, doc: Doc) -> None:
        self.doc = doc
        self.records: dict[str, list[dict]] = {name: [] for name, _ in COLLECTIONS}
        self.claims: list[tuple[int, int]] = []
        self.slugs: dict[str, set[str]] = {name: set() for name, _ in COLLECTIONS}

    def add(self, collection: str, record: dict, claim: tuple[int, int] | None = None) -> dict:
        slug = record["slug"]
        if slug in self.slugs[collection]:
            raise SystemExit(f"duplicate slug in {collection}: {slug}")
        self.slugs[collection].add(slug)
        entity_type = dict(COLLECTIONS)[collection]
        full = {
            "@context": CONTEXT,
            "@id": f"{BASE}objects/{collection}/{slug}",
            "@type": entity_type,
        }
        full.update(record)
        full["htmlPage"] = {"@id": f"{BASE}records/{collection}/{slug}/"}
        if collection != "sources":
            full.setdefault("source", {"@id": SOURCE_ID})
        self.records[collection].append(full)
        if claim is not None:
            self.claims.append(claim)
        return full

    def record_for(self, collection: str, heading_index: int, extra: dict,
                   name: str | None = None, claim: bool = True) -> dict:
        doc = self.doc
        start, _, heading = doc.headings[heading_index]
        end = doc.section_end(heading_index)
        record = {
            "name": name if name is not None else title_name(heading),
            "slug": slugify(name if name is not None else heading),
            "sourceLocator": doc.locator(doc.chapter_at(start), heading, start, end),
        }
        record.update(extra)
        return self.add(collection, record, (start, end) if claim else None)


# --- typed extractors -------------------------------------------------------


def heading_indexes(doc: Doc, level: int, within: tuple[int, int] | None = None):
    for index, (line, heading_level, _) in enumerate(doc.headings):
        if heading_level != level:
            continue
        if within and not (within[0] <= line < within[1]):
            continue
        yield index


def chapter_span(doc: Doc, title: str) -> tuple[int, int]:
    for index, (line, level, text) in enumerate(doc.headings):
        if level == 2 and text == title:
            return line, doc.section_end(index)
    raise SystemExit(f"chapter not found: {title}")


def section_span(doc: Doc, level: int, title: str) -> tuple[int, int]:
    for index, (line, heading_level, text) in enumerate(doc.headings):
        if heading_level == level and text == title:
            return line, doc.section_end(index)
    raise SystemExit(f"section not found: {title}")


def extract_source(corpus: Corpus, root: Path) -> None:
    doc = corpus.doc
    pdf = root / PDF_NAME
    if pdf.exists():
        actual = "sha256:" + hashlib.sha256(pdf.read_bytes()).hexdigest()
        if actual != PDF_DIGEST:
            raise SystemExit(
                f"{PDF_NAME} does not match the registered digest: {actual}"
            )
    corpus.add("sources", {
        "name": "Daggerheart System Reference Document 2.0",
        "slug": SOURCE_SLUG,
        "srdVersion": "2.0",
        "sourceFile": "SRD.md",
        "contentDigest": "sha256:" + hashlib.sha256(doc.text.encode()).hexdigest(),
        "pdfFile": PDF_NAME,
        "pdfDigest": PDF_DIGEST,
        "license": "Darrington Press Community Gaming License",
        "licenseUrl": {"@id": "https://www.darringtonpress.com/license"},
        "attributionStatement": ATTRIBUTION,
    })


def extract_class_domains(doc: Doc) -> dict[str, list[str]]:
    start, end = section_span(doc, 3, "Class Domains")
    mapping: dict[str, list[str]] = {}
    for bullet in parse_bullets(doc.body(start, end)):
        match = re.match(r"(.+?): (.+) & (.+)$", bullet)
        if match:
            mapping[match.group(1)] = [match.group(2), match.group(3)]
    # The source prints "Assassion" once; the class heading is ASSASSIN.
    if "Assassion" in mapping:
        mapping["Assassin"] = mapping.pop("Assassion")
    if sorted(mapping) != sorted(title_name(name) for name in CLASS_NAMES):
        raise SystemExit(f"unexpected class-domain list: {sorted(mapping)}")
    return mapping


def extract_domains(corpus: Corpus) -> None:
    doc = corpus.doc
    start, end = section_span(doc, 3, "DOMAINS")
    for index in heading_indexes(doc, 4, (start, end)):
        line, _, heading = doc.headings[index]
        if heading not in DOMAIN_NAMES:
            continue
        corpus.record_for("domains", index, {
            "description": strip_markup(doc.body(line + 1, doc.section_end(index))),
        })


def parse_named_features(doc: Doc, start: int, end: int) -> list[dict]:
    features, _ = parse_features(blocks_of(doc.body(start, end)))
    return features


def extract_classes(corpus: Corpus, class_domains: dict[str, list[str]]) -> None:
    doc = corpus.doc
    classes_start, classes_end = section_span(doc, 3, "CLASSES")
    class_heads = [
        index
        for index in heading_indexes(doc, 4, (classes_start, classes_end))
        if doc.headings[index][2] in CLASS_NAMES
    ]
    if len(class_heads) != len(CLASS_NAMES):
        raise SystemExit(f"expected {len(CLASS_NAMES)} classes, found {len(class_heads)}")

    for position, head in enumerate(class_heads):
        start, _, heading = doc.headings[head]
        end = (
            doc.headings[class_heads[position + 1]][0]
            if position + 1 < len(class_heads)
            else classes_end
        )
        class_name = title_name(heading)
        record: dict = {
            "domains": [ref("domains", slugify(domain)) for domain in class_domains[class_name]],
            "subclasses": [],
        }
        sections: list[dict] = []
        description: list[str] = []
        subclass_heads: list[int] = []
        subclass_mode = False
        cursor = head + 1
        # Intro prose before the first h5.
        first_sub = next(
            (i for i, (l, lv, _) in enumerate(doc.headings) if l > start and l < end),
            None,
        )
        intro_end = doc.headings[first_sub][0] if first_sub is not None else end
        description = strip_markup(doc.body(start + 1, intro_end))

        for index, (line, level, text) in enumerate(doc.headings):
            if not (start < line < end):
                continue
            sub_end = min(doc.section_end(index), end)
            if level == 4:
                if text == f"{heading} SUBCLASSES":
                    subclass_mode = True
                elif subclass_mode and len(subclass_heads) < 2:
                    # Every class has exactly two subclasses, printed directly
                    # after its SUBCLASSES heading.
                    subclass_heads.append(index)
                elif not re.match(r"TIER \d$", text) and text not in {"BEASTFORM OPTIONS"}:
                    body = strip_markup(doc.body(line + 1, sub_end))
                    if body:
                        sections.append({"name": title_name(text), "rulesText": body})
            elif level == 5 and not subclass_mode:
                match = re.fullmatch(r"STARTING EVASION – (\d+)", text)
                if match:
                    record["startingEvasion"] = int(match.group(1))
                    continue
                match = re.fullmatch(r"STARTING HIT POINTS – (\d+)", text)
                if match:
                    record["startingHitPoints"] = int(match.group(1))
                    continue
                if text.endswith("HOPE FEATURE"):
                    features = parse_named_features(doc, line + 1, sub_end)
                    if features:
                        record["hopeFeature"] = features[0]
                elif text in {"CLASS FEATURE", "CLASS FEATURES"}:
                    record["features"] = parse_named_features(doc, line + 1, sub_end)

        # Class items paragraph lives under the hit-points heading.
        items = re.search(r"^CLASS ITEMS – (.+)$", doc.body(start, end), re.MULTILINE)
        if items:
            record["classItems"] = strip_markup(items.group(1))

        # Background questions and connections are class-level h5 sections.
        for index, (line, level, text) in enumerate(doc.headings):
            if not (start < line < end) or level != 5:
                continue
            sub_end = min(doc.section_end(index), end)
            if text == "BACKGROUND QUESTIONS":
                record["backgroundQuestions"] = parse_bullets(doc.body(line + 1, sub_end))
            elif text == "CONNECTIONS":
                record["connections"] = parse_bullets(doc.body(line + 1, sub_end))

        if sections:
            record["sections"] = sections
        record["description"] = description
        class_slug = slugify(heading)
        class_record = corpus.record_for("classes", head, record, claim=True)

        for order, sub_index in enumerate(subclass_heads):
            sub_line, _, sub_heading = doc.headings[sub_index]
            sub_end = min(doc.section_end(sub_index), end)
            extract_subclass(corpus, sub_index, sub_end, class_slug)
            class_record["subclasses"].append(
                ref("subclasses", slugify(sub_heading))
            )
        if heading == "DRUID":
            extract_beastforms(corpus, start, end, class_slug)


def extract_subclass(corpus: Corpus, head: int, end: int, class_slug: str) -> None:
    doc = corpus.doc
    start, _, heading = doc.headings[head]
    record: dict = {"parentClass": ref("classes", class_slug), "features": []}
    first_sub = next(
        (l for l, lv, _ in doc.headings if start < l < end), end
    )
    record["description"] = strip_markup(doc.body(start + 1, first_sub))
    for index, (line, level, text) in enumerate(doc.headings):
        if not (start < line < end) or level != 5:
            continue
        sub_end = min(doc.section_end(index), end)
        if text == "SPELLCAST TRAIT":
            record["spellcastTrait"] = strip_markup(doc.body(line + 1, sub_end))
        else:
            match = re.fullmatch(r"(FOUNDATION|SPECIALIZATION|MASTERY) FEATURES?", text)
            if match:
                stage = match.group(1).casefold()
                for feature in parse_named_features(doc, line + 1, sub_end):
                    feature = {"name": feature["name"], "stage": stage,
                               "rulesText": feature["rulesText"]}
                    record["features"].append(feature)
    corpus.add("subclasses", {
        "name": title_name(heading),
        "slug": slugify(heading),
        "sourceLocator": doc.locator(doc.chapter_at(start), heading, start, end),
        **record,
    })


def extract_beastforms(corpus: Corpus, start: int, end: int, class_slug: str) -> None:
    doc = corpus.doc
    options_line, _ = section_span(doc, 4, "BEASTFORM OPTIONS")
    tier = 0
    for index, (line, level, text) in enumerate(doc.headings):
        # Beastform sections run from BEASTFORM OPTIONS to the end of the
        # Druid class section, interleaved with TIER group headings.
        if not (options_line < line < end) or level != 4:
            continue
        tier_match = re.fullmatch(r"TIER (\d)", text)
        if tier_match:
            tier = int(tier_match.group(1))
            continue
        sub_end = min(doc.section_end(index), end)
        record: dict = {"tier": tier, "fromClass": ref("classes", class_slug)}
        body = doc.body(line + 1, sub_end)
        feature_blocks: list[str] = []
        for block in blocks_of(body):
            examples = re.fullmatch(r"\*\((.+)\)\*", block)
            stats = re.fullmatch(r"\*([A-Za-z]+) ([+-]\d+) \| Evasion ([+-]\d+)\*", block)
            attack = re.fullmatch(
                r"\*(Melee|Very Close|Close|Far|Very Far) ([A-Za-z]+) (d\d+(?:\+\d+)?) (phy|mag)\*",
                block,
            )
            advantage = re.match(r"\*\*Gain advantage on:\*\* (.+)", block, re.DOTALL)
            if examples:
                record["exampleCreatures"] = examples.group(1)
            elif stats:
                record["traitBonus"] = f"{stats.group(1)} {stats.group(2)}"
                record["evasionBonus"] = int(stats.group(3))
            elif attack:
                record["attack"] = {
                    "range": attack.group(1),
                    "trait": attack.group(2),
                    "damage": f"{attack.group(3)} {attack.group(4)}",
                }
            elif advantage:
                record["advantageOn"] = [
                    item.strip() for item in advantage.group(1).replace("\n", " ").split(",")
                ]
            else:
                feature_blocks.append(block)
        features, preamble = parse_features(feature_blocks)
        if preamble:
            record["description"] = "\n\n".join(preamble)
        if features:
            record["features"] = features
        corpus.record_for("beastforms", index, record, claim=False)


def extract_heritage(corpus: Corpus) -> None:
    doc = corpus.doc
    core = chapter_span(doc, "CORE MATERIALS")
    start, end = section_span(doc, 3, "ANCESTRIES")
    for index in heading_indexes(doc, 4, (start, end)):
        line, _, heading = doc.headings[index]
        if heading not in ANCESTRY_NAMES:
            continue
        sub_end = doc.section_end(index)
        feature_start = next(
            (l for l, lv, text in doc.headings
             if line < l < sub_end and text in {"ANCESTRY FEATURES", "ANCESTRY FEATURE"}),
            sub_end,
        )
        record: dict = {"description": strip_markup(doc.body(line + 1, feature_start))}
        if feature_start < sub_end:
            record["features"] = parse_named_features(doc, feature_start + 1, sub_end)
        corpus.record_for("ancestries", index, record)

    start, end = section_span(doc, 3, "COMMUNITIES")
    for index in heading_indexes(doc, 4, (start, end)):
        line, _, heading = doc.headings[index]
        if not heading.endswith("BORNE"):
            continue
        sub_end = doc.section_end(index)
        feature_start = next(
            (l for l, lv, text in doc.headings
             if line < l < sub_end and text == "COMMUNITY FEATURE"),
            sub_end,
        )
        record = {"description": strip_markup(doc.body(line + 1, feature_start))}
        if feature_start < sub_end:
            features = parse_named_features(doc, feature_start + 1, sub_end)
            if features:
                record["feature"] = features[0]
        corpus.record_for("communities", index, record)

    start, end = section_span(doc, 3, "TRANSFORMATIONS")
    for index in heading_indexes(doc, 4, (start, end)):
        line, _, heading = doc.headings[index]
        if heading not in TRANSFORMATION_NAMES:
            continue
        sub_end = doc.section_end(index)
        record = {}
        boundary = sub_end
        for sub, (l, lv, text) in enumerate(doc.headings):
            if not (line < l < sub_end) or lv != 5:
                continue
            inner_end = min(doc.section_end(sub), sub_end)
            if text == "TRANSFORMATION FEATURES":
                boundary = min(boundary, l)
                record["features"] = parse_named_features(doc, l + 1, inner_end)
            elif text == "TRANSFORMATION QUESTIONS":
                boundary = min(boundary, l)
                record["questions"] = parse_bullets(doc.body(l + 1, inner_end))
        record["description"] = strip_markup(doc.body(line + 1, boundary))
        corpus.record_for("transformations", index, record)


def extract_stat_blocks(corpus: Corpus) -> None:
    doc = corpus.doc
    adversary_names: dict[str, str] = {}
    pending_environments: list[tuple[int, dict]] = []

    for index in heading_indexes(doc, 4):
        line, _, heading = doc.headings[index]
        end = doc.section_end(index)
        body = doc.body(line + 1, end)
        first = blocks_of(body)[0] if blocks_of(body) else ""
        tier_match = re.fullmatch(r"\*Tier (\d) ([A-Za-z()/0-9 ]+)\*", first)
        if not tier_match:
            continue
        tier, role = int(tier_match.group(1)), tier_match.group(2)
        record: dict = {"tier": tier}
        feature_line = next(
            (l for l, lv, text in doc.headings if line < l < end and text == "FEATURES"),
            end,
        )
        head_blocks = blocks_of(doc.body(line + 1, feature_line))[1:]
        description: list[str] = []
        for block in head_blocks:
            plain = strip_markup(block).replace("\n", " ")
            if plain.startswith("Motives & Tactics: "):
                record["motivesAndTactics"] = [
                    item.strip() for item in plain[len("Motives & Tactics: "):].split(",")
                ]
            elif plain.startswith("Impulses: "):
                record["impulses"] = [
                    item.strip() for item in plain[len("Impulses: "):].split(",")
                ]
            elif plain.startswith("Difficulty: "):
                stats = re.fullmatch(
                    r"Difficulty: (\S+) \| Thresholds: (.+?) \| HP: (\d+) \| Stress: (\S+)",
                    plain,
                )
                if stats:
                    record["difficulty"] = int(stats.group(1)) if stats.group(1).isdigit() else stats.group(1)
                    record["thresholds"] = stats.group(2)
                    record["hitPoints"] = int(stats.group(3))
                    record["stress"] = int(stats.group(4)) if stats.group(4).isdigit() else stats.group(4)
                else:
                    value = plain[len("Difficulty: "):]
                    record["difficulty"] = int(value) if value.isdigit() else value
            elif plain.startswith("ATK: "):
                attack = re.fullmatch(r"ATK: (\S+) \| (.+?): (.+?) \| (.+)", plain)
                if not attack:
                    raise SystemExit(f"unparsed attack line for {heading}: {plain!r}")
                record["attackModifier"] = attack.group(1)
                record["standardAttack"] = {
                    "name": attack.group(2),
                    "range": attack.group(3),
                    "damage": attack.group(4),
                }
            elif plain.startswith("Experience: "):
                record["experience"] = plain[len("Experience: "):]
            elif plain.startswith("Potential Adversaries: "):
                record["potentialAdversariesText"] = plain[len("Potential Adversaries: "):]
            else:
                description.append(plain)
        if description:
            record["description"] = "\n\n".join(description)
        if feature_line < end:
            record["features"] = parse_named_features(doc, feature_line + 1, end)

        # Adversary and environment roles overlap (both have Social), so the
        # stat line vocabulary decides: adversaries print Motives & Tactics,
        # environments print Impulses.
        is_environment = "impulses" in record or "potentialAdversariesText" in record
        is_adversary = "motivesAndTactics" in record or "hitPoints" in record
        if is_environment == is_adversary:
            raise SystemExit(f"ambiguous stat block: {heading}")
        if is_environment:
            if role not in ENVIRONMENT_CATEGORIES:
                raise SystemExit(f"unexpected environment category for {heading}: {role}")
            record["category"] = role
            pending_environments.append((index, record))
        else:
            record["role"] = role
            emitted = corpus.record_for("adversaries", index, record)
            adversary_names[emitted["name"].casefold()] = emitted["slug"]

    for index, record in pending_environments:
        text = record.get("potentialAdversariesText", "")
        links = []
        for candidate in re.split(r"[,()]", text):
            slug = adversary_names.get(candidate.strip().casefold())
            if slug and ref("adversaries", slug) not in links:
                links.append(ref("adversaries", slug))
        if links:
            record["potentialAdversaries"] = links
        corpus.record_for("environments", index, record)


def extract_domain_cards(corpus: Corpus) -> None:
    doc = corpus.doc
    start, end = section_span(doc, 3, "Domain Card reference")
    for index in heading_indexes(doc, 4, (start, end)):
        line, _, heading = doc.headings[index]
        domain = heading.removesuffix(" DOMAIN")
        if domain not in DOMAIN_NAMES:
            raise SystemExit(f"unexpected appendix domain: {heading}")
        group_end = doc.section_end(index)
        for card_index, (card_line, level, card_heading) in enumerate(doc.headings):
            if not (line < card_line < group_end) or level != 5:
                continue
            card_end = min(doc.section_end(card_index), group_end)
            blocks = blocks_of(doc.body(card_line + 1, card_end))
            meta = re.fullmatch(
                r"\*\*Level (\d+) ([A-Za-z]+) (Ability|Spell|Grimoire)\*\*", blocks[0]
            )
            cost = re.fullmatch(r"\*\*Recall Cost:\*\* (\d+)", blocks[1])
            # The two-column appendix layout can carry a domain's last cards
            # past the next domain heading, so the card's own printed domain
            # line is authoritative rather than the enclosing group.
            if not meta or not cost or meta.group(2).upper() not in DOMAIN_NAMES:
                raise SystemExit(f"unparsed domain card header: {card_heading}")
            corpus.record_for("domain-cards", card_index, {
                "level": int(meta.group(1)),
                "domain": ref("domains", slugify(meta.group(2))),
                "cardType": meta.group(3),
                "recallCost": int(cost.group(1)),
                "rulesText": strip_markup("\n\n".join(blocks[2:])),
            })


# --- table-derived equipment -------------------------------------------------


WEAPON_HEADERS = {("Name", "Trait", "Range", "Damage", "Burden", "Feature"),
                  ("Name", "Tier", "Trait", "Range", "Damage", "Burden", "Feature")}
ARMOR_HEADERS = {("Name", "Base Thresholds", "Base Score", "Feature")}
LOOT_HEADERS = {("ROLL", "Loot", "description"), ("ROLL", "LOOT", "description")}


def parse_feature_cell(cell: str) -> dict | None:
    cell = cell.replace("<br>", " ").strip()
    if cell in {"", "—"}:
        return None
    match = re.match(r"([A-Z][^:]{0,40}): (.+)", cell, re.DOTALL)
    if match:
        return {"name": match.group(1), "rulesText": match.group(2)}
    return {"rulesText": cell}


def damage_fields(cell: str) -> dict:
    fields: dict = {}
    if "<br>" in cell:
        fields["tieredDamage"] = cell.split("<br>")
    else:
        fields["damage"] = cell
    types = []
    if re.search(r"\bphy\b", cell):
        types.append("physical")
    if re.search(r"\bmag\b", cell):
        types.append("magic")
    if types:
        fields["damageTypes"] = types
    return fields


def extract_tables(corpus: Corpus) -> None:
    doc = corpus.doc
    heading_stack: list[tuple[int, str]] = []
    section_rule_slug: dict[int, str] = {}
    last_headers: tuple[str, ...] = ()
    index = 0
    loot_sets: dict[str, set[str]] = {"items": set(), "consumables": set()}

    def context_value(pattern: str) -> str | None:
        for _, text in reversed(heading_stack):
            if re.search(pattern, text, re.IGNORECASE):
                return text
        return None

    while index < len(doc.lines):
        line = doc.lines[index]
        heading = re.match(r"(#{1,6}) (.+)$", line)
        if heading:
            level = len(heading.group(1))
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            heading_stack.append((level, heading.group(2)))
            # A continuation table (empty header row) only ever follows its
            # parent table directly; any heading breaks the continuation.
            last_headers = ()
            index += 1
            continue
        if not line.startswith("|"):
            index += 1
            continue
        headers, rows, table_end = parse_pipe_table(doc.lines, index)
        signature = tuple(headers)
        if not any(headers):
            signature = last_headers
        else:
            last_headers = signature
        chapter = doc.chapter_at(index)

        if signature in WEAPON_HEADERS or signature in ARMOR_HEADERS:
            tier_text = context_value(r"^TIER \d") or ""
            tier_match = re.match(r"TIER (\d)", tier_text)
            variant = "core"
            if context_value(r"WHEELCHAIR|FRAME MODELS"):
                variant = "combat-wheelchair"
            elif context_value(r"EVERYDAY HERO"):
                variant = "everyday-hero"
            elif chapter.startswith("Supplemental") or chapter == "SUPPLEMENTAL CAMPAIGN MECHANICS":
                if context_value(r"WESTERN"):
                    variant = "western"
                elif context_value(r"MONSTER HUNTING"):
                    variant = "monster-hunting"
                else:
                    variant = "everyday-hero"
        if signature in WEAPON_HEADERS:
            category = "secondary" if context_value(r"SECONDARY") else "primary"
            for row_line, cells in rows:
                row = dict(zip(signature, cells))
                record = {
                    "name": row["Name"],
                    "slug": slugify(row["Name"]),
                    "sourceLocator": doc.locator(chapter, heading_stack[-1][1], row_line, row_line + 1),
                    "category": category,
                    "variant": variant,
                    "trait": row["Trait"],
                    "range": row["Range"],
                    "burden": row["Burden"] or None,
                    **damage_fields(row["Damage"]),
                }
                if "Tier" in row:
                    record["tier"] = int(row["Tier"])
                elif tier_match:
                    record["tier"] = int(tier_match.group(1))
                if record["burden"] is None:
                    del record["burden"]
                feature = parse_feature_cell(row["Feature"])
                if feature:
                    record["feature"] = feature
                corpus.add("weapons", record)
        elif signature in ARMOR_HEADERS:
            for row_line, cells in rows:
                row = dict(zip(signature, cells))
                record = {
                    "name": row["Name"],
                    "slug": slugify(row["Name"]),
                    "sourceLocator": doc.locator(chapter, heading_stack[-1][1], row_line, row_line + 1),
                    "variant": variant,
                    "baseThresholds": row["Base Thresholds"].replace("<br>", "; "),
                    "baseScore": row["Base Score"].replace("<br>", "; "),
                }
                if tier_match:
                    record["tier"] = int(tier_match.group(1))
                feature = parse_feature_cell(row["Feature"])
                if feature:
                    record["feature"] = feature
                corpus.add("armor", record)
        elif signature in LOOT_HEADERS:
            collection = "consumables" if context_value(r"CONSUMABLES") else "items"
            set_heading = context_value(r"^(Core Set|Additional)") or ""
            item_set = "core-set" if set_heading.startswith("Core Set") else "expansion"
            for row_line, cells in rows:
                row = dict(zip(("ROLL", "LOOT", "description"), cells))
                slug = slugify(row["LOOT"])
                if slug in corpus.slugs[collection]:
                    slug = f"{slug}-{item_set}"
                corpus.add(collection, {
                    "name": row["LOOT"],
                    "slug": slug,
                    "sourceLocator": doc.locator(chapter, heading_stack[-1][1], row_line, row_line + 1),
                    "itemSet": item_set,
                    "roll": int(row["ROLL"]),
                    "description": row["description"],
                })
        index = table_end


# --- rules (gap coverage) ----------------------------------------------------


def extract_rules(corpus: Corpus) -> None:
    doc = corpus.doc
    claimed = [False] * len(doc.lines)
    for start, end in corpus.claims:
        for index in range(start, end):
            claimed[index] = True

    def unclaimed_content(start: int, end: int) -> bool:
        return any(
            doc.is_content(i) and not claimed[i] for i in range(start, end)
        )

    def emit(heading: str, start: int, end: int) -> None:
        if not unclaimed_content(start, end):
            return
        body_start = start + 1 if doc.lines[start].startswith("#") else start
        record = {
            "name": title_name(heading),
            "slug": None,
            "sourceLocator": doc.locator(doc.chapter_at(start), heading, start, end),
            "rulesText": doc.body(body_start, end),
        }
        base = slugify(heading)
        slug = base
        counter = 2
        while slug in corpus.slugs["rules"]:
            slug = f"{base}-{counter}"
            counter += 1
        record["slug"] = slug
        corpus.add("rules", record, (start, end))

    def walk(heading: str, start: int, end: int, children: list[int]) -> None:
        if not unclaimed_content(start, end):
            return
        inner = [
            index for index in children
            if start < doc.headings[index][0] < end
        ]
        # Direct children: minimal level among inner headings.
        if not inner:
            emit(heading, start, end)
            return
        child_level = min(doc.headings[i][1] for i in inner)
        direct = [i for i in inner if doc.headings[i][1] == child_level]
        first_child = doc.headings[direct[0]][0]
        has_claimed = any(
            claimed[i] for i in range(start, end) if doc.is_content(i)
        )
        if not has_claimed and end - start < 400:
            emit(heading, start, end)
            return
        if unclaimed_content(start, first_child):
            emit(heading, start, first_child)
        for position, child in enumerate(direct):
            child_start = doc.headings[child][0]
            child_end = min(doc.section_end(child), end)
            walk(doc.headings[child][2], child_start, child_end, inner)

    all_headings = list(range(len(doc.headings)))
    walk("DAGGERHEART", 0, len(doc.lines), all_headings)

    # Coverage assertion: every content line must now be claimed.
    for start, end in corpus.claims:
        for index in range(start, end):
            claimed[index] = True
    missing = [
        index + 1
        for index in range(len(doc.lines))
        if doc.is_content(index) and not claimed[index]
    ]
    if missing:
        raise SystemExit(f"uncovered content lines: {missing[:10]} ({len(missing)} total)")


# --- aggregates ---------------------------------------------------------------


def dump(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


def link_table_sections(corpus: Corpus) -> None:
    """Point each table-derived record at the rule section holding its table."""
    spans = sorted(
        (
            (rule["sourceLocator"]["lineStart"], rule["sourceLocator"]["lineEnd"],
             rule["slug"])
            for rule in corpus.records["rules"]
        ),
    )
    for collection in ("weapons", "armor", "items", "consumables"):
        for record in corpus.records[collection]:
            line = record["sourceLocator"]["lineStart"]
            best = None
            for start, end, slug in spans:
                if start <= line <= end and (
                    best is None or end - start < best[0]
                ):
                    best = (end - start, slug)
            if best is None:
                raise SystemExit(f"no containing rule section for {record['@id']}")
            record["fromSection"] = ref("rules", best[1])


def build(root: Path, out: Path) -> None:
    doc = Doc(root)
    corpus = Corpus(doc)
    extract_source(corpus, root)
    class_domains = extract_class_domains(doc)
    extract_domains(corpus)
    extract_classes(corpus, class_domains)
    extract_heritage(corpus)
    extract_stat_blocks(corpus)
    extract_domain_cards(corpus)
    extract_tables(corpus)
    extract_rules(corpus)
    link_table_sections(corpus)

    objects = out / "objects"
    if objects.exists():
        import shutil

        shutil.rmtree(objects)
    total = 0
    collection_entries = []
    graph = []
    for collection, entity_type in COLLECTIONS:
        records = sorted(corpus.records[collection], key=lambda r: r["slug"])
        for record in records:
            dump(objects / collection / f"{record['slug']}.jsonld", record)
            member = dict(record)
            member.pop("@context")
            graph.append(member)
        collection_entries.append({
            "name": collection,
            "entityType": entity_type,
            "schemaReference": {"@id": f"{BASE}systems/{entity_type.casefold()}.schema.json"},
            "count": len(records),
            "members": [{"@id": record["@id"]} for record in records],
        })
        total += len(records)

    manifest = {
        "@context": CONTEXT,
        "@id": f"{BASE}objects/daggerheart-system-data",
        "@type": "Manifest",
        "name": "Daggerheart SRD System Data",
        "corpusVersion": CORPUS_VERSION,
        "srdVersion": "2.0",
        "sourceFile": "SRD.md",
        "contentDigest": "sha256:" + hashlib.sha256(doc.text.encode()).hexdigest(),
        "license": "Darrington Press Community Gaming License",
        "attributionStatement": ATTRIBUTION,
        "recordCount": total,
        "collections": collection_entries,
    }
    dump(objects / "daggerheart-system-data.jsonld", manifest)
    dump(objects / "daggerheart-system-data.bundle.jsonld", {
        "@context": CONTEXT,
        "@id": f"{BASE}objects/daggerheart-system-data.bundle",
        "@type": "Bundle",
        "name": "Daggerheart SRD System Data Bundle",
        "corpusVersion": CORPUS_VERSION,
        "@graph": graph,
    })

    content_lines = sum(1 for index in range(len(doc.lines)) if doc.is_content(index))
    relation_count = sum(
        len(v) if isinstance(v, list) else 1
        for record in graph
        for key, v in record.items()
        if key in {"domains", "domain", "parentClass", "subclasses", "fromClass",
                   "potentialAdversaries", "fromSection", "source"}
    )
    dump(objects / "build-metrics.json", {
        "corpusVersion": CORPUS_VERSION,
        "recordCount": total,
        "collections": {name: len(corpus.records[name]) for name, _ in COLLECTIONS},
        "sourceContentLines": content_lines,
        "coveredContentLines": content_lines,
        "relationCount": relation_count,
    })
    print(f"built {total} records across {len(COLLECTIONS)} collections")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    build(args.root, args.out or args.root)


if __name__ == "__main__":
    main()
