#!/usr/bin/env python3
"""Convert the Daggerheart SRD PDF text layer to readable Markdown.

The PDF is laid out in two columns on most pages and contains several wide
tables. Poppler's reading-order extraction is used for prose. Layout-aware
extraction is used for table-heavy pages, which layout_pages renders as
Markdown tables in reading order. PDF page markers are retained as comments
so the result can be audited page by page against the source.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from layout_pages import render_layout_page


# The PDF's embedded icon font maps the visible digits 0-9 to private-use
# characters. U+F0E0 is a Wingdings right arrow used in the tier list.
GLYPH_MAP = str.maketrans(
    {
        "\ue53f": "0",
        "\ue541": "1",
        "\ue542": "2",
        "\ue543": "3",
        "\ue544": "4",
        "\ue545": "5",
        "\ue546": "6",
        "\ue547": "7",
        "\ue548": "8",
        "\ue549": "9",
        "\uf0e0": "→",
    }
)


# These pages consist primarily of tables whose relationships would be lost if
# their cells were flattened into reading-order paragraphs.
LAYOUT_PAGES = frozenset(
    {
        *range(56, 70),
        *range(71, 85),
        88,
        89,
        90,
        95,
        96,
        159,
        191,
        192,
        193,
        194,
        197,
        201,
    }
)


CHAPTER_TITLES = {
    "CONTENTS",
    "INTRODUCTION",
    "CHARACTER CREATION",
    "CORE MATERIALS",
    "CORE MECHANICS",
    "RUNNING AN ADVENTURE",
    "SUPPLEMENTAL CAMPAIGN MECHANICS",
    "APPENDIX",
}


SECTION_TITLES = {
    "CLASS DOMAINS",
    "DOMAINS",
    "CLASSES",
    "ANCESTRIES",
    "COMMUNITIES",
    "TRANSFORMATIONS",
    "FLOW OF THE GAME",
    "CORE GAMEPLAY LOOP",
    "THE SPOTLIGHT",
    "TURN ORDER & ACTION ECONOMY",
    "MAKING MOVES & TAKING ACTION",
    "COMBAT",
    "STRESS",
    "ATTACKING",
    "MAPS, RANGE & MOVEMENT",
    "CONDITIONS",
    "DOWNTIME",
    "DEATH",
    "ADDITIONAL RULES",
    "LEVELING UP",
    "MULTICLASSING",
    "EQUIPMENT",
    "WEAPONS",
    "COMBAT WHEELCHAIR",
    "ARMOR",
    "LOOT & ITEMS",
    "CONSUMABLES",
    "GM GUIDANCE",
    "CORE GM MECHANICS",
    "ADVERSARIES AND ENVIRONMENTS",
    "ADDITIONAL GM GUIDANCE",
    "THE WITHERWILD CAMPAIGN FRAME",
    "FACTION TRACKING",
    "EVERYDAY HERO STARTING EQUIPMENT",
    "FEASTS",
    "GRIMDARK CAMPAIGNS",
    "TECH-BASED CAMPAIGNS",
    "WESTERN CAMPAIGNS",
    "COLOSSAL ADVERSARIES",
    "FLOATING MAGIC SCHOOL CAMPAIGNS",
    "FAIRY TALE CAMPAIGNS",
    "MONSTER HUNTING CAMPAIGNS",
    "HEX CRAWL CAMPAIGNS",
    "DOMAIN CARD REFERENCE",
}


# A title is only a section heading when it appears on the page where that
# section begins. Several short section names (most notably "Death") also
# occur as ordinary body text elsewhere in the document.
SECTION_STARTS = {
    7: {"DOMAINS"},
    8: {"CLASS DOMAINS", "CLASSES"},
    32: {"ANCESTRIES"},
    38: {"COMMUNITIES"},
    42: {"TRANSFORMATIONS"},
    46: {"FLOW OF THE GAME", "CORE GAMEPLAY LOOP", "THE SPOTLIGHT"},
    47: {"TURN ORDER & ACTION ECONOMY", "MAKING MOVES & TAKING ACTION"},
    50: {"COMBAT", "STRESS", "ATTACKING"},
    51: {"MAPS, RANGE, AND MOVEMENT"},
    52: {"CONDITIONS", "DOWNTIME"},
    53: {"DEATH", "ADDITIONAL RULES", "LEVELING UP"},
    54: {"MULTICLASSING"},
    55: {"EQUIPMENT", "WEAPONS"},
    70: {"COMBAT WHEELCHAIR"},
    72: {"ARMOR"},
    75: {"LOOT & ITEMS"},
    80: {"CONSUMABLES"},
    85: {"INTRODUCTION", "GM GUIDANCE"},
    86: {"CORE GM MECHANICS"},
    93: {"ADVERSARIES AND ENVIRONMENTS"},
    183: {"ADDITIONAL GM GUIDANCE"},
    184: {"THE WITHERWILD", "THE WITHERWILD CAMPAIGN FRAME"},
    190: {"FACTION TRACKING"},
    191: {"EVERYDAY HERO STARTING EQUIPMENT"},
    192: {"FEASTS"},
    195: {"GRIMDARK CAMPAIGNS", "TECH-BASED CAMPAIGNS"},
    197: {"WESTERN CAMPAIGNS"},
    198: {"COLOSSAL ADVERSARIES"},
    199: {"FLOATING MAGIC SCHOOL CAMPAIGNS"},
    200: {"FAIRY TALE CAMPAIGNS"},
    201: {"MONSTER HUNTING CAMPAIGNS"},
    203: {"HEX CRAWL CAMPAIGNS"},
    206: {"DOMAIN CARD REFERENCE"},
}


DETAIL_HEADINGS = {
    "ANCESTRY FEATURES",
    "ATTACK MODIFIER",
    "BACKGROUND QUESTIONS",
    "BURDEN",
    "CLASS FEATURE",
    "CLASS FEATURES",
    "COMMUNITY FEATURE",
    "CONNECTIONS",
    "DAMAGE",
    "DAMAGE TYPE",
    "DESCRIPTION",
    "DIFFICULTY",
    "EVASION",
    "EXPERIENCE (OPTIONAL)",
    "FEATURE",
    "FEATURE(S)",
    "FEATURES",
    "FEAR FEATURE(S)",
    "FOUNDATION FEATURE",
    "FOUNDATION FEATURES",
    "MASTERY FEATURE",
    "MASTERY FEATURES",
    "MOTIVES & TACTICS",
    "NAME",
    "SPECIALIZATION FEATURE",
    "SPECIALIZATION FEATURES",
    "SPELLCAST TRAIT",
    "STANDARD ATTACK",
    "TIER",
    "TRANSFORMATION FEATURES",
    "TRANSFORMATION QUESTIONS",
    "TYPE",
}


def extract_pages(pdf: Path, *, layout: bool = False) -> list[str]:
    command = ["pdftotext", "-enc", "UTF-8"]
    if layout:
        command.append("-layout")
    command.extend([str(pdf), "-"])
    result = subprocess.run(command, check=True, stdout=subprocess.PIPE)
    text = result.stdout.decode("utf-8")
    pages = text.split("\f")
    if pages and not pages[-1].strip():
        pages.pop()
    return pages


@dataclass(frozen=True)
class TextBlock:
    x_min: float
    y_min: float
    x_max: float
    y_max: float
    text: str


def extract_bbox_pages(pdf: Path) -> list[list[TextBlock]]:
    command = ["pdftotext", "-enc", "UTF-8", "-bbox-layout", str(pdf), "-"]
    result = subprocess.run(command, check=True, stdout=subprocess.PIPE)
    root = ET.fromstring(result.stdout)
    namespace = {"x": "http://www.w3.org/1999/xhtml"}
    pages: list[list[TextBlock]] = []
    for page in root.findall(".//x:page", namespace):
        blocks: list[TextBlock] = []
        for block in page.findall(".//x:block", namespace):
            line_texts: list[str] = []
            for line in block.findall("./x:line", namespace):
                words = line.findall("./x:word", namespace)
                if words:
                    line_text = ""
                    previous_x_max: float | None = None
                    for word in words:
                        word_text = "".join(word.itertext())
                        x_min = float(word.attrib["xMin"])
                        if line_text and previous_x_max is not None:
                            # Poppler emits a new <word> at several fi/fl
                            # ligature boundaries even when there is no visual
                            # word space. Rejoin touching glyph runs.
                            if x_min - previous_x_max > 0.5:
                                line_text += " "
                        line_text += word_text
                        previous_x_max = float(word.attrib["xMax"])
                    line_texts.append(line_text)
            text = reflow(line_texts)
            if text:
                blocks.append(
                    TextBlock(
                        x_min=float(block.attrib["xMin"]),
                        y_min=float(block.attrib["yMin"]),
                        x_max=float(block.attrib["xMax"]),
                        y_max=float(block.attrib["yMax"]),
                        text=normalize_glyphs(text),
                    )
                )
        pages.append(blocks)
    return pages


def normalize_glyphs(text: str) -> str:
    return text.translate(GLYPH_MAP).replace("\u00ad", "")


def strip_page_furniture(page: str, page_number: int) -> str:
    """Remove the running title and its paired folio, wherever they occur."""
    lines = [normalize_glyphs(line).rstrip() for line in page.splitlines()]
    remove: set[int] = set()
    footer_indexes: list[int] = []
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not re.fullmatch(
            rf"(?:(?:{page_number})\s+)?Daggerheart SRD(?:\s+(?:{page_number}))?",
            stripped,
        ):
            continue
        remove.add(index)
        footer_indexes.append(index)

    if footer_indexes:
        candidates = [
            (min(abs(other - footer) for footer in footer_indexes), other)
            for other, line in enumerate(lines)
            if line.strip() == str(page_number)
        ]
        if candidates:
            remove.add(min(candidates)[1])

    cleaned = [line for index, line in enumerate(lines) if index not in remove]
    while cleaned and not cleaned[0].strip():
        cleaned.pop(0)
    while cleaned and not cleaned[-1].strip():
        cleaned.pop()
    return "\n".join(cleaned)


def strip_block_furniture(
    blocks: list[TextBlock], page_number: int
) -> list[TextBlock]:
    footer_blocks = [block for block in blocks if block.text == "Daggerheart SRD"]
    candidates = [block for block in blocks if block.text == str(page_number)]
    folio: TextBlock | None = None
    if footer_blocks and candidates:
        folio = min(
            candidates,
            key=lambda block: min(
                abs(block.y_min - footer.y_min) + abs(block.x_min - footer.x_min)
                for footer in footer_blocks
            ),
        )
    return [
        block
        for block in blocks
        if block not in footer_blocks and (folio is None or block is not folio)
    ]


def order_blocks(blocks: list[TextBlock], page_width: float = 612.0) -> list[TextBlock]:
    """Order full-width bands, then each band's left and right columns."""
    midpoint = page_width / 2
    # Mirrored page margins put the even-page right column at x=304.6, just
    # left of the geometric page midpoint. The actual gutter is always clear
    # by x=300 on prose pages.
    column_boundary = 300.0
    gutter = 10.0
    spanning = sorted(
        (
            block
            for block in blocks
            if block.x_min < midpoint - gutter and block.x_max > midpoint + gutter
        ),
        key=lambda block: (block.y_min, block.x_min),
    )
    columns = [block for block in blocks if block not in spanning]
    ordered: list[TextBlock] = []
    previous_y = float("-inf")

    def append_band(upper_y: float) -> None:
        band = [
            block
            for block in columns
            if previous_y <= (block.y_min + block.y_max) / 2 < upper_y
        ]
        left = sorted(
            (block for block in band if block.x_min < column_boundary),
            key=lambda block: (block.y_min, block.x_min),
        )
        right = sorted(
            (block for block in band if block.x_min >= column_boundary),
            key=lambda block: (block.y_min, block.x_min),
        )
        ordered.extend(left)
        ordered.extend(right)

    for block in spanning:
        append_band(block.y_min)
        ordered.append(block)
        previous_y = max(previous_y, block.y_max)
    append_band(float("inf"))
    return ordered


def bbox_page_blocks(blocks: list[TextBlock], page_number: int) -> list[TextBlock]:
    return order_blocks(strip_block_furniture(blocks, page_number))


def bbox_page_text(blocks: list[TextBlock], page_number: int) -> str:
    return "\n\n".join(block.text for block in bbox_page_blocks(blocks, page_number))


def is_heading_candidate(text: str) -> bool:
    text = text.strip()
    if len(text) < 3 or len(text) > 110 or "...." in text:
        return False
    if text.endswith((".", ",", ";", ":")):
        return False
    letters = [char for char in text if char.isalpha()]
    return bool(letters) and all(not char.islower() for char in letters)


CHAPTER_STARTS = {
    2: "CONTENTS",
    3: "INTRODUCTION",
    4: "CHARACTER CREATION",
    7: "CORE MATERIALS",
    46: "CORE MECHANICS",
    85: "RUNNING AN ADVENTURE",
    190: "SUPPLEMENTAL CAMPAIGN MECHANICS",
    206: "APPENDIX",
}


def is_known_heading(text: str, page_number: int | None = None) -> bool:
    canonical = text.upper()
    if canonical == "DAGGERHEART":
        return True
    if page_number is None:
        return canonical in CHAPTER_TITLES | SECTION_TITLES
    return (
        CHAPTER_STARTS.get(page_number) == canonical
        or canonical in SECTION_STARTS.get(page_number, set())
    )


def is_detail_heading(text: str, page_number: int) -> bool:
    """Return whether an all-caps heading labels details of a larger entry."""
    canonical = text.upper()
    if not (8 <= page_number <= 45 or 93 <= page_number <= 182):
        return False
    return (
        canonical in DETAIL_HEADINGS
        or canonical.endswith("’S HOPE FEATURE")
        or canonical.endswith("'S HOPE FEATURE")
        or bool(
            re.fullmatch(
                r"STARTING (?:EVASION|HIT POINTS)\s+–\s+\d+", canonical
            )
        )
    )


def heading_level(text: str, page_number: int | None = None) -> int:
    canonical = text.upper()
    if canonical == "DAGGERHEART":
        return 1
    if page_number is not None and CHAPTER_STARTS.get(page_number) == canonical:
        return 2
    if page_number is not None and canonical in SECTION_STARTS.get(page_number, set()):
        return 3
    if page_number is not None and 3 <= page_number <= 6:
        return 4 if canonical in {"WHAT IS DAGGERHEART?", "EXAMPLE EXPERIENCES"} else 3
    if page_number is not None and page_number >= 206:
        return 4 if canonical.endswith(" DOMAIN") else 5
    if page_number is not None and is_detail_heading(text, page_number):
        return 5
    if page_number is None and canonical in CHAPTER_TITLES | SECTION_TITLES:
        return 3
    return 4


def is_list_item(block: str) -> bool:
    return bool(re.match(r"^(?:\s*-|\d+\.)\s+", block))


def join_markdown_blocks(blocks: list[str]) -> str:
    """Join Markdown blocks, keeping consecutive list items in one list."""
    output = ""
    previous = ""
    for block in blocks:
        if not output:
            output = block
        elif is_list_item(previous) and is_list_item(block):
            output += "\n" + block
        else:
            output += "\n\n" + block
        previous = block
    return output


def split_bullet_items(text: str) -> list[str]:
    """Split bullet glyphs that Poppler merged into a single text block."""
    return [item.strip() for item in re.split(r"\s*[•◦]\s*", text) if item.strip()]


def html_table(
    headers: list[str], rows: list[list[str | tuple[str, int]]]
) -> str:
    """Render a table, using HTML only when cells span multiple columns."""
    if not any(isinstance(cell, tuple) for row in rows for cell in row):
        columns = len(headers) or len(rows[0])
        if headers:
            header_row = "| " + " | ".join(headers) + " |"
        else:
            header_row = "|" + " |" * columns
        lines = [header_row, "|" + " --- |" * columns]
        lines.extend("| " + " | ".join(row) + " |" for row in rows)
        return "\n".join(lines)
    output = ["<table>"]
    if headers:
        output.extend(["  <thead>", "    <tr>"])
        output.extend(f"      <th>{header}</th>" for header in headers)
        output.extend(["    </tr>", "  </thead>"])
    output.append("  <tbody>")
    for row in rows:
        output.append("    <tr>")
        for index, cell in enumerate(row):
            text, colspan = cell if isinstance(cell, tuple) else (cell, 1)
            tag = "th" if index == 0 else "td"
            attribute = f' colspan="{colspan}"' if colspan > 1 else ""
            output.append(f"      <{tag}{attribute}>{text}</{tag}>")
        output.append("    </tr>")
    output.extend(["  </tbody>", "</table>"])
    return "\n".join(output)


def replace_once(markdown: str, old: str, new: str, page_number: int) -> str:
    if markdown.count(old) != 1:
        raise RuntimeError(
            f"page {page_number} table layout no longer matches its parser"
        )
    return markdown.replace(old, new, 1)


def repair_compact_tables(
    markdown: str, blocks: list[TextBlock], page_number: int
) -> str:
    """Restore compact tables that occur within otherwise prose-heavy pages."""
    text = [block.text for block in bbox_page_blocks(blocks, page_number)]

    if page_number == 26:
        table = html_table([], [text[index : index + 3] for index in range(29, 53, 3)])
        return replace_once(markdown, "\n\n".join(text[29:53]), table, page_number)

    if page_number == 29:
        table = html_table(
            text[20:22],
            [[text[23], text[22]], [text[25], text[24]], [text[27], text[26]]],
        )
        return replace_once(markdown, "\n\n".join(text[20:28]), table, page_number)

    if page_number == 30:
        table = html_table(
            ["Roll", "Phase", text[13]],
            [
                [text[14], text[16], text[15]],
                ["2–3", "Waxing", text[18]],
                [text[19], text[20], text[21]],
                ["5–6", "Waning", "+1 to Evasion"],
            ],
        )
        return replace_once(markdown, "\n\n".join(text[12:23]), table, page_number)

    if page_number == 91:
        countdown_table = html_table(
            text[6:9],
            [text[index : index + 3] for index in range(9, 24, 3)],
        )
        markdown = replace_once(
            markdown, "\n\n".join(text[6:24]), countdown_table, page_number
        )
        costs_table = html_table(
            [], [text[index : index + 2] for index in range(37, 61, 2)]
        )
        return replace_once(
            markdown, "\n\n".join(text[37:61]), costs_table, page_number
        )

    if page_number == 93:
        table = html_table([], [text[index : index + 3] for index in range(36, 54, 3)])
        return replace_once(markdown, "\n\n".join(text[36:54]), table, page_number)

    if page_number == 183:
        table = html_table(
            text[31:33],
            [text[index : index + 2] for index in range(33, 57, 2)],
        )
        return replace_once(markdown, "\n\n".join(text[31:57]), table, page_number)

    return markdown


def reflow(lines: list[str]) -> str:
    result = ""
    for line in lines:
        text = line.strip()
        if not text:
            continue
        if not result:
            result = text
        elif result.endswith("-") and text[:1].islower():
            result += text
        else:
            result += " " + text
    return result


def split_block(lines: list[str]) -> list[tuple[str, list[str]]]:
    """Split a PDF text block into prose, headings, and bullet items."""
    segments: list[tuple[str, list[str]]] = []
    current_kind = "prose"
    current: list[str] = []

    def flush() -> None:
        nonlocal current
        if current:
            segments.append((current_kind, current))
            current = []

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        if is_heading_candidate(line):
            flush()
            segments.append(("heading", [line]))
            current_kind = "prose"
        elif line.startswith("•"):
            flush()
            current_kind = "bullet"
            current = [line[1:].strip()]
        elif line.startswith("◦"):
            flush()
            current_kind = "subbullet"
            current = [line[1:].strip()]
        elif re.match(r"^\d+[.)]\s+", line):
            flush()
            current_kind = "numbered"
            current = [re.sub(r"^(\d+)[.)]\s+", r"\1. ", line)]
        else:
            current.append(line)
    flush()
    return segments


def prose_to_markdown(page: str) -> str:
    blocks = re.split(r"\n\s*\n", page)
    output: list[str] = []
    for block in blocks:
        lines = block.splitlines()
        for kind, segment_lines in split_block(lines):
            text = reflow(segment_lines)
            if not text:
                continue
            if kind == "heading":
                output.append(f"{'#' * heading_level(text)} {text}")
            elif kind == "bullet":
                output.append(f"- {text}")
            elif kind == "subbullet":
                output.append(f"  - {text}")
            elif kind == "numbered":
                output.append(text)
            elif text.startswith("Note:"):
                output.append(f"> {text}")
            else:
                output.append(text)
    return join_markdown_blocks(output)


def contents_to_markdown(blocks: list[TextBlock], page_number: int) -> str:
    """Format the two-column contents page as a compact nested list."""
    entries: list[str] = []
    entry_pattern = re.compile(r".*?\.{2,}\s*\d+(?=\s|$)")

    for block in bbox_page_blocks(blocks, page_number):
        text = block.text.strip()
        if text == "CONTENTS":
            continue
        matches = [entry.strip() for entry in entry_pattern.findall(text)]
        if not matches:
            raise RuntimeError(f"could not parse contents entry: {text!r}")
        entries.extend(matches)

    output = ["## CONTENTS"]
    for entry in entries:
        title = re.split(r"\.{2,}", entry, maxsplit=1)[0]
        source_title = title.strip().rstrip(". ")
        canonical = source_title.upper()
        is_chapter = source_title == canonical or canonical == (
            "SUPPLEMENTAL CAMPAIGN MECHANICS"
        )
        indent = "" if is_chapter and canonical in CHAPTER_TITLES else "  "
        output.append(f"{indent}- {entry}")
    return "\n\n".join((output[0], "\n".join(output[1:])))


def page_196_to_markdown(blocks: list[TextBlock], page_number: int) -> str:
    """Restore the two Scrap tables split apart by the PDF's column layout."""
    page_blocks = bbox_page_blocks(blocks, page_number)
    if len(page_blocks) != 82 or page_blocks[11].text != "GATHERING SCRAP":
        raise RuntimeError("page 196 layout no longer matches the Scrap table parser")
    text = [block.text for block in page_blocks]

    scrap_table = html_table(
        [text[14], *text[15:20], *text[34:39]],
        [
            [text[20], *text[21:26], text[39], *text[40:44]],
            [
                text[26],
                (text[27], 2),
                (text[28], 2),
                text[29],
                *text[44:49],
            ],
            [
                text[30],
                (text[31], 2),
                (text[32], 3),
                (text[49], 2),
                *text[50:53],
            ],
        ],
    )
    rewards_table = html_table(
        [*text[54:57], *text[70:72]],
        [
            [text[57], text[58], text[59], text[72], text[73]],
            [text[60], text[61], text[62], text[74], text[75]],
            [text[63], text[64], text[65], text[76], text[77]],
        ],
    )

    output = [
        text[0],
        f"#### {text[1]}",
        text[2],
        f"#### {text[3]}",
        text[4],
        f"#### {text[6]}",
        text[7],
        *(f"- {item[1:].strip()}" for item in text[8:11]),
        f"#### {text[11]}",
        text[12],
        f"##### {text[5]}",
        text[13],
        scrap_table,
        f"##### {text[33]}",
        text[53],
        rewards_table,
        f"#### {text[66]}",
        text[67],
        f"#### {text[68]}",
        f"{text[69]} {text[78]}",
        f"#### {text[79]}",
        text[80],
        text[81],
    ]
    return join_markdown_blocks(output)


def page_70_to_markdown(blocks: list[TextBlock], page_number: int) -> str:
    """Restore the light-frame wheelchair table and its two-column reading order."""
    page_blocks = bbox_page_blocks(blocks, page_number)
    if len(page_blocks) != 57 or page_blocks[0].text != "Combat Wheelchair":
        raise RuntimeError("page 70 layout no longer matches the wheelchair parser")
    text = [block.text for block in page_blocks]
    wheelchair_table = html_table(
        [*text[22:27], *text[47:49]],
        [
            [*text[27:32], text[50], text[49]],
            [*text[32:37], text[52], text[51]],
            [*text[37:42], text[54], text[53]],
            [*text[42:47], text[56], text[55]],
        ],
    )
    output = [
        f"### {text[0]}",
        text[1],
        text[2],
        f"#### {text[3]}",
        text[4],
        *(f"- {item[1:].strip()}" for item in text[5:8]),
        f"#### {text[8]}",
        *text[9:14],
        f"#### {text[15]}",
        text[16],
        f"#### {text[17]}",
        text[18],
        f"#### {text[19]}",
        text[20],
        f"##### {text[14]}",
        text[21],
        wheelchair_table,
    ]
    return join_markdown_blocks(output)


def blocks_to_markdown(blocks: list[TextBlock], page_number: int) -> str:
    output: list[str] = []
    ancestry_features_seen = False
    for block in bbox_page_blocks(blocks, page_number):
        text = block.text.strip()
        if not text:
            continue
        if page_number == 1 and text == "System reference Document 2.0":
            output.append(f"## {text}")
        elif page_number == 1 and text.startswith(("SRD Writer:", "Layout:")):
            output.append(f"- {text}")
        elif text.startswith("•"):
            for item in split_bullet_items(text[1:]):
                output.append(f"- {item}")
        elif text.startswith("◦"):
            for item in split_bullet_items(text[1:]):
                output.append(f"  - {item}")
        elif is_heading_candidate(text) or is_known_heading(text, page_number):
            level = heading_level(text, page_number)
            if page_number == 32 and text == "ANCESTRY FEATURES":
                if not ancestry_features_seen:
                    level = 4
                ancestry_features_seen = True
            output.append(f"{'#' * level} {text}")
        elif re.match(r"^\d+[.)]\s+", text):
            output.append(re.sub(r"^(\d+)[.)]\s+", r"\1. ", text))
        elif text.startswith("Note:"):
            output.append(f"> {text}")
        elif " • " in text:
            introduction, *items = split_bullet_items(text)
            output.append(introduction)
            output.extend(f"- {item}" for item in items)
        else:
            output.append(text)
    markdown = join_markdown_blocks(output)
    return repair_compact_tables(markdown, blocks, page_number)


# Stat-block feature entries are labeled "<Name> - <Kind>:" in the source.
FEATURE_MARKER = re.compile(
    r" - (?:Passive|Action|Reaction|Evolution|Water|Fire|Earth|Air|Sandstorm|"
    r"Hurricane):"
)
STAT_LABEL = re.compile(r"(^|\| )([A-Z][A-Za-z’& ]*?):")
BEASTFORM_LINE = re.compile(
    r"^([A-Za-z]+ [+-]\d+ \| Evasion [+-]\d+) "
    r"((?:Melee|Very Close|Close|Far|Very Far) [A-Za-z]+ d\d+(?:\+\d+)? "
    r"(?:phy|mag))$"
)
EXAMPLE_CREATURES = re.compile(r"^\([A-Z][^()]*\)$")
ANATOMY_LABEL = re.compile(r"^(Level|Domain|Recall Cost|Title|Type|Feature) (?=[A-Z])")
COLON_LEAD = re.compile(r"^(\s*- )?([A-Z][^:.\n]{1,40}): ")
# A colon-led opener is a label worth bolding unless it reads as a sentence.
SENTENCE_LEAD = re.compile(
    r"\b(?:you|your|can|are|is|this|that|there|they|example|see|follow|don)\b",
    re.IGNORECASE,
)


def bold_colon_lead(match: re.Match) -> str:
    prefix, lead = match.group(1) or "", match.group(2)
    if SENTENCE_LEAD.search(lead):
        return match.group(0)
    return f"{prefix}**{lead}:** "


def bold_bullet_leads(segment: str) -> str:
    return "\n".join(
        COLON_LEAD.sub(bold_colon_lead, line) if line.lstrip().startswith("- ") else line
        for line in segment.split("\n")
    )
FEATURE_NAME = re.compile(r"^([A-Z][^:.]{1,60}): ")
CARD_META = re.compile(r"^Level (\d+) ([A-Za-z ]+?) Recall Cost: (\d+)$")
TIER_LINE = re.compile(r"Tier \d [A-Z][\w()/ ]{2,30}")


def split_feature_paragraphs(text: str) -> list[str]:
    """Split a run of stat-block features into one bolded paragraph each."""
    markers = list(FEATURE_MARKER.finditer(text))
    if not markers:
        return [text]
    starts: list[int] = []
    for marker in markers:
        # A feature name follows the end of the previous sentence, or an
        # inline standard-attack line that ends with a damage type.
        start = max(
            (
                boundary + len(terminator)
                for terminator in (". ", "! ", "? ", "” ", " phy ", " mag ")
                if (boundary := text.rfind(terminator, 0, marker.start())) >= 0
            ),
            default=0,
        )
        if not starts or start > starts[-1]:
            starts.append(start)
    segments = []
    if starts[0] > 0:
        segments.append(text[: starts[0]].strip())
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(text)
        segment = text[start:end].strip()
        marker = FEATURE_MARKER.search(segment)
        if marker is None:
            segments.append(segment)
        else:
            name = segment[: marker.end()].strip()
            segments.append(f"**{name}** {segment[marker.end():].strip()}")
    return segments


def prettify_stat_segment(segment: str) -> list[str]:
    """Reshape one adversary/environment stat-block paragraph."""
    if TIER_LINE.fullmatch(segment):
        return [f"*{segment}*"]
    for label in ("Motives & Tactics: ", "Impulses: "):
        index = segment.find(f" {label}")
        if index >= 0:
            return [
                segment[:index],
                f"**{label.rstrip()}** {segment[index + len(label) + 1:]}",
            ]
        if segment.startswith(label):
            return [f"**{label.rstrip()}** {segment[len(label):]}"]
    if segment.startswith("Difficulty:"):
        parts = [segment]
        for splitter in (" ATK: ", " Potential Adversaries: "):
            index = segment.find(splitter)
            if index >= 0:
                parts = [segment[:index], segment[index + 1 :]]
                break
        return [STAT_LABEL.sub(r"\1**\2:**", part) for part in parts]
    if segment.startswith(("ATK:", "Experience:")):
        return [STAT_LABEL.sub(r"\1**\2:**", segment)]
    return split_feature_paragraphs(segment)


def is_plain_paragraph(segment: str) -> bool:
    return bool(segment) and segment[:1] not in "<>#-|" and not re.match(
        r"\d+\. ", segment
    )


def prettify_page(markdown: str, page_number: int) -> str:
    """Bold labels and split merged stat-block paragraphs for readability."""
    output: list[str] = []
    for segment in markdown.split("\n\n"):
        pieces = [segment]
        if segment.lstrip()[:2] == "- ":
            pieces = [bold_bullet_leads(segment)]
        elif not is_plain_paragraph(segment):
            pass
        elif 8 <= page_number <= 45:
            beastform = BEASTFORM_LINE.fullmatch(segment)
            if beastform:
                pieces = [f"*{beastform.group(1)}*", f"*{beastform.group(2)}*"]
            elif EXAMPLE_CREATURES.fullmatch(segment):
                pieces = [f"*{segment}*"]
            elif page_number == 8 and ANATOMY_LABEL.match(segment):
                pieces = [ANATOMY_LABEL.sub(r"**\1** ", segment)]
            else:
                pieces = [FEATURE_NAME.sub(r"**\1:** ", segment)]
        elif 46 <= page_number <= 92 or 183 <= page_number <= 205:
            pieces = [COLON_LEAD.sub(bold_colon_lead, segment, count=1)]
        elif 93 <= page_number <= 182:
            pieces = prettify_stat_segment(segment)
        elif page_number >= 206 and CARD_META.fullmatch(segment):
            meta = CARD_META.fullmatch(segment)
            pieces = [
                f"**Level {meta.group(1)} {meta.group(2)}**",
                f"**Recall Cost:** {meta.group(3)}",
            ]
        for piece in pieces:
            # Rejoin a paragraph that the two-column page layout split
            # mid-sentence ("...a book" / "about your secret hobby").
            if (
                output
                and is_plain_paragraph(output[-1])
                and output[-1][-1:] not in ".!?:”"
                and is_plain_paragraph(piece)
                and piece[:1].islower()
            ):
                output[-1] += " " + piece
            else:
                output.append(piece)
    return "\n\n".join(output)


def convert(pdf: Path) -> str:
    bbox_pages = extract_bbox_pages(pdf)
    layout_pages = extract_pages(pdf, layout=True)
    if len(bbox_pages) != len(layout_pages):
        raise RuntimeError(
            f"extraction page count mismatch: {len(bbox_pages)} vs "
            f"{len(layout_pages)}"
        )

    parts = [
        "<!--",
        f"Converted from {pdf.name}.",
        "PDF page boundaries are retained for completeness auditing.",
        "Wide tables are rendered as Markdown tables in reading order.",
        "-->",
    ]
    for page_number in range(1, len(bbox_pages) + 1):
        parts.append(f"<!-- PDF page {page_number} -->")
        if page_number == 2:
            parts.append(contents_to_markdown(bbox_pages[page_number - 1], page_number))
        elif page_number == 70:
            parts.append(page_70_to_markdown(bbox_pages[page_number - 1], page_number))
        elif page_number == 196:
            parts.append(page_196_to_markdown(bbox_pages[page_number - 1], page_number))
        elif page_number in LAYOUT_PAGES:
            page = strip_page_furniture(layout_pages[page_number - 1], page_number)
            parts.append(render_layout_page(page_number, page))
        else:
            markdown = blocks_to_markdown(bbox_pages[page_number - 1], page_number)
            parts.append(prettify_page(markdown, page_number))
    return "\n\n".join(parts).rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.write_text(convert(args.pdf), encoding="utf-8")


if __name__ == "__main__":
    main()
