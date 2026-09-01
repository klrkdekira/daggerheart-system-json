#!/usr/bin/env python3
"""Convert the Daggerheart SRD PDF text layer to readable Markdown.

The PDF is laid out in two columns on most pages and contains several wide
tables. Poppler's reading-order extraction is used for prose. Layout-aware
extraction is used for table-heavy pages and preserved in fenced text blocks.
PDF page markers are retained as comments so the result can be audited page by
page against the source.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


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


def is_known_heading(text: str) -> bool:
    canonical = text.upper()
    return canonical == "DAGGERHEART" or canonical in CHAPTER_TITLES | SECTION_TITLES


def heading_level(text: str, page_number: int | None = None) -> int:
    canonical = text.upper()
    if canonical == "DAGGERHEART":
        return 1
    if page_number is not None and CHAPTER_STARTS.get(page_number) == canonical:
        return 2
    if canonical in CHAPTER_TITLES | SECTION_TITLES:
        return 3
    return 4


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
    return "\n\n".join(output)


def blocks_to_markdown(blocks: list[TextBlock], page_number: int) -> str:
    output: list[str] = []
    for block in bbox_page_blocks(blocks, page_number):
        text = block.text.strip()
        if not text:
            continue
        if is_heading_candidate(text) or is_known_heading(text):
            output.append(f"{'#' * heading_level(text, page_number)} {text}")
        elif text.startswith("•"):
            item = text[1:].strip()
            if item:
                output.append(f"- {item}")
        elif text.startswith("◦"):
            item = text[1:].strip()
            if item:
                output.append(f"  - {item}")
        elif re.match(r"^\d+[.)]\s+", text):
            output.append(re.sub(r"^(\d+)[.)]\s+", r"\1. ", text))
        elif text.startswith("Note:"):
            output.append(f"> {text}")
        else:
            output.append(text)
    return "\n\n".join(output)


def layout_to_markdown(page: str) -> str:
    lines = page.splitlines()
    nonempty_indents = [len(line) - len(line.lstrip()) for line in lines if line.strip()]
    common_indent = min(nonempty_indents, default=0)
    if common_indent:
        lines = [line[common_indent:] if line.strip() else "" for line in lines]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "```text\n" + "\n".join(lines) + "\n```"


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
        "Wide tables are preserved as layout-aware fenced text blocks.",
        "-->",
    ]
    for page_number in range(1, len(bbox_pages) + 1):
        parts.append(f"<!-- PDF page {page_number} -->")
        if page_number in LAYOUT_PAGES:
            page = strip_page_furniture(layout_pages[page_number - 1], page_number)
            parts.append(layout_to_markdown(page))
        else:
            parts.append(blocks_to_markdown(bbox_pages[page_number - 1], page_number))
    return "\n\n".join(parts).rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.write_text(convert(args.pdf), encoding="utf-8")


if __name__ == "__main__":
    main()
