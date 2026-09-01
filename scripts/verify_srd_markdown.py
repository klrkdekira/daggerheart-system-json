#!/usr/bin/env python3
"""Verify SRD.md against the source PDF extraction, page by page."""

from __future__ import annotations

import argparse
import collections
import re
import sys
import unicodedata
from pathlib import Path

from convert_srd_pdf import (
    LAYOUT_PAGES,
    bbox_page_text,
    extract_bbox_pages,
    extract_pages,
    normalize_glyphs,
    strip_page_furniture,
)


PAGE_MARKER = re.compile(r"<!-- PDF page (\d+) -->")
# Table cells and side-by-side panes are reflowed into reading order on these
# pages, so their content is compared by character count rather than sequence.
REORDERED_MARKDOWN_PAGES = {29, 30, 70, 196} | LAYOUT_PAGES
# Repaired compact tables per page, whether rendered as pipe tables or (for
# tables with column spans) HTML.
EXPECTED_TABLES = {
    26: 1,
    29: 1,
    30: 1,
    70: 1,
    91: 2,
    93: 1,
    183: 1,
    196: 2,
}
PIPE_SEPARATOR = re.compile(r"^\|(?: --- \|)+$", re.MULTILINE)


def tokenize(text: str) -> collections.Counter[str]:
    text = normalize_glyphs(text)
    tokens = re.findall(r"[^\W_]+", text.casefold(), flags=re.UNICODE)
    return collections.Counter(tokens)


def comparable_tokens(text: str) -> collections.Counter[str]:
    """Tokenize while ignoring line-wrap and typographic hyphen differences."""
    text = normalize_glyphs(text)
    text = re.sub(r"(?<=\w)[\-‐‑‒–—][ \t]*(?=\w)", "", text)
    return tokenize(text)


def alphanumeric_characters(text: str) -> collections.Counter[str]:
    text = normalize_glyphs(text).casefold()
    return collections.Counter(char for char in text if char.isalnum())


def canonical_character_sequence(text: str) -> str:
    """Remove only extraction/Markdown structure, retaining content punctuation."""
    text = normalize_glyphs(text)
    text = text.replace("•", "").replace("◦", "")
    text = re.sub(r"^(\d+)\)\s+", r"\1. ", text, flags=re.MULTILINE)
    return "".join(char for char in text if not char.isspace())


def raw_markdown_pages(markdown: str) -> dict[int, str]:
    matches = list(PAGE_MARKER.finditer(markdown))
    pages: dict[int, str] = {}
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        pages[int(match.group(1))] = markdown[start:end]
    return pages


def markdown_pages(markdown: str) -> dict[int, str]:
    pages = raw_markdown_pages(markdown)
    for page_number, page in pages.items():
        lines: list[str] = []
        for line in page.split("\n"):
            if line.startswith("|"):
                # Drop pipe-table separator rows and empty header rows, and
                # reduce data rows to their cell text.
                if re.fullmatch(r"\|[\s|:-]*", line):
                    continue
                line = line.replace("|", " ")
            lines.append(line)
        page = "\n".join(lines)
        # Emphasis markers are added during conversion; the source PDF text
        # contains no asterisks, so they can be stripped wholesale.
        page = page.replace("*", "")
        page = re.sub(r"^#{1,6}\s+", "", page, flags=re.MULTILINE)
        page = re.sub(r"^\s*-\s+", "", page, flags=re.MULTILINE)
        page = re.sub(r"^>\s+", "", page, flags=re.MULTILINE)
        page = re.sub(
            r"</?(?:table|thead|tbody|tr|th|td|br)\b[^>]*/?>",
            "\n",
            page,
        )
        pages[page_number] = page
    return pages


def unusual_characters(text: str) -> list[str]:
    result: list[str] = []
    for char in sorted(set(text), key=ord):
        if char == "\ufffd" or unicodedata.category(char) in {"Co", "Cs", "Cn"}:
            result.append(f"U+{ord(char):04X}")
    return result


def counter_delta(
    expected: collections.Counter[str], actual: collections.Counter[str]
) -> str:
    missing = list((expected - actual).elements())[:12]
    extra = list((actual - expected).elements())[:12]
    return f"missing={missing!r}, extra={extra!r}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    parser.add_argument("markdown", type=Path)
    args = parser.parse_args()

    reading = extract_pages(args.pdf)
    bbox = extract_bbox_pages(args.pdf)
    layout = extract_pages(args.pdf, layout=True)
    markdown = args.markdown.read_text(encoding="utf-8")
    raw_pages = raw_markdown_pages(markdown)
    rendered_pages = markdown_pages(markdown)
    failures: list[str] = []

    expected_numbers = list(range(1, len(bbox) + 1))
    if sorted(rendered_pages) != expected_numbers:
        failures.append(
            "page markers do not cover every source page exactly once: "
            f"expected 1-{len(reading)}, got {sorted(rendered_pages)!r}"
        )

    if re.search(r"^```", markdown, flags=re.MULTILINE):
        failures.append("no fenced text blocks may remain in the Markdown")

    for page_number, expected_count in EXPECTED_TABLES.items():
        page = raw_pages.get(page_number, "")
        actual_count = page.count("<table>") + len(PIPE_SEPARATOR.findall(page))
        if actual_count != expected_count:
            failures.append(
                f"page {page_number} must contain {expected_count} table(s), "
                f"found {actual_count}"
            )

    for page_number in expected_numbers:
        if page_number not in rendered_pages:
            continue
        if page_number in LAYOUT_PAGES:
            source = strip_page_furniture(layout[page_number - 1], page_number)
        else:
            source = bbox_page_text(bbox[page_number - 1], page_number)
        expected = tokenize(source)
        actual = tokenize(rendered_pages[page_number])
        if expected != actual:
            failures.append(
                f"page {page_number} token mismatch: {counter_delta(expected, actual)}"
            )
        expected_characters = canonical_character_sequence(source)
        actual_characters = canonical_character_sequence(rendered_pages[page_number])
        if page_number in REORDERED_MARKDOWN_PAGES:
            if collections.Counter(expected_characters) != collections.Counter(
                actual_characters
            ):
                failures.append(
                    f"page {page_number} normalized character-count mismatch"
                )
        elif expected_characters != actual_characters:
            failures.append(
                f"page {page_number} normalized character-sequence mismatch"
            )

        reading_source = strip_page_furniture(reading[page_number - 1], page_number)
        if (
            comparable_tokens(reading_source) != comparable_tokens(source)
            and alphanumeric_characters(reading_source)
            != alphanumeric_characters(source)
        ):
            failures.append(
                f"page {page_number} independent extraction mismatch: "
                f"{counter_delta(comparable_tokens(reading_source), comparable_tokens(source))}"
            )

    unusual = unusual_characters(markdown)
    if unusual:
        failures.append(f"unmapped or invalid Unicode characters: {', '.join(unusual)}")
    if "\f" in markdown:
        failures.append("form-feed characters remain in Markdown")
    if markdown.count("# DAGGERHEART") != 1:
        failures.append("Markdown must contain exactly one '# DAGGERHEART' title")

    if failures:
        print("Verification failed:")
        for failure in failures:
            print(f"- {failure}")
        sys.exit(1)

    reading_tokens = sum(
        sum(tokenize(strip_page_furniture(page, number)).values())
        for number, page in enumerate(reading, start=1)
    )
    bbox_tokens = sum(
        sum(tokenize(bbox_page_text(page, number)).values())
        for number, page in enumerate(bbox, start=1)
    )
    markdown_tokens = sum(
        sum(tokenize(page).values()) for page in rendered_pages.values()
    )
    print(f"Verified {len(reading)} PDF pages and {markdown_tokens:,} Markdown tokens.")
    print(f"Coordinate-ordered source contains {bbox_tokens:,} normalized tokens.")
    print(f"Reading-order source contains {reading_tokens:,} normalized tokens.")


if __name__ == "__main__":
    main()
