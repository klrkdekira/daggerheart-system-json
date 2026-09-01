"""Render the SRD's table-heavy layout pages as structured Markdown.

Each page in convert_srd_pdf.LAYOUT_PAGES is extracted with pdftotext -layout
and rendered here into headings, prose, lists, and Markdown tables. The PDF
lays these pages out in fixed-width columns; cells are recovered by mapping
character positions onto the column origins of each table's header row.
Tables that continue from a previous page have no header row in the source,
so they are rendered with an empty header row rather than invented labels.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


TOLERANCE = 3

TRAIT_LABELS = {
    "AGILITY",
    "STRENGTH",
    "FINESSE",
    "INSTINCT",
    "PRESENCE",
    "KNOWLEDGE",
}

TRAIT_WORDS = {
    "Agility",
    "Strength",
    "Finesse",
    "Instinct",
    "Presence",
    "Knowledge",
    "Spellcast",
}


def spans(line: str) -> list[tuple[int, str]]:
    """Return (start, text) runs separated by two or more spaces."""
    return [
        (match.start(), match.group())
        for match in re.finditer(r"\S+(?: \S+)*", line)
    ]


def words(line: str) -> list[tuple[int, str]]:
    return [(match.start(), match.group()) for match in re.finditer(r"\S+", line)]


def join_fragments(fragments: list[str]) -> str:
    """Join wrapped cell fragments, healing hyphenation and tiered values."""
    result = ""
    for fragment in fragments:
        if not result:
            result = fragment
        elif fragment.startswith("Tier ") and result.startswith("Tier "):
            result += "<br>" + fragment
        elif result.endswith("-") and fragment[:1].islower():
            result += fragment
        else:
            result += " " + fragment
    return result


@dataclass
class Table:
    headers: list[str]
    starts: list[int]
    mode: str = "left"
    key: int | None = 1
    row_start: object = None
    rows: list[list[list[str]]] = field(default_factory=list)

    def cells(self, line: str) -> list[str]:
        columns = [""] * len(self.starts)
        if self.mode == "center":
            centers = [
                start + len(header) / 2
                for start, header in zip(self.starts, self.headers)
            ]
            for start, text in spans(line):
                middle = start + len(text) / 2
                index = min(
                    range(len(centers)), key=lambda i: abs(centers[i] - middle)
                )
                columns[index] += (" " if columns[index] else "") + text
        else:
            for start, text in words(line):
                index = 0
                for column, origin in enumerate(self.starts):
                    if start >= origin - TOLERANCE:
                        index = column
                columns[index] += (" " if columns[index] else "") + text
        return columns

    def add_line(self, line: str) -> None:
        columns = self.cells(line)
        # A long weapon name can run to within one space of its trait (e.g.
        # "Fighting Cloak Presence"), pulling the trait into the name column.
        if self.headers[1:2] == ["Trait"] and not columns[1]:
            name_words = columns[0].split()
            if len(name_words) > 1 and name_words[-1] in TRAIT_WORDS:
                columns[1] = name_words[-1]
                columns[0] = " ".join(name_words[:-1])
        if self.row_start is not None:
            is_new = self.row_start(columns)
        elif self.key is not None:
            is_new = bool(columns[self.key])
        else:
            is_new = True
        if is_new or not self.rows:
            self.rows.append([[] for _ in self.starts])
        for cell, text in zip(self.rows[-1], columns):
            if text:
                cell.append(text)

    def markdown(self) -> str:
        if any(self.headers):
            header_row = "| " + " | ".join(self.headers) + " |"
        else:
            header_row = "|" + " |" * len(self.starts)
        lines = [header_row, "|" + " --- |" * len(self.starts)]
        for row in self.rows:
            cells = [join_fragments(cell) for cell in row]
            if any("|" in cell for cell in cells):
                raise RuntimeError(f"table cell contains a pipe: {cells!r}")
            lines.append(("| " + " | ".join(cells) + " |").replace("|  ", "| "))
        return "\n".join(lines)


def table_from_header(
    line: str,
    *,
    mode: str = "left",
    key: int | None = 1,
    row_start: object = None,
) -> Table:
    parts = spans(line)
    table = Table(
        headers=[text for _, text in parts],
        starts=[start for start, _ in parts],
        mode=mode,
        key=key,
        row_start=row_start,
    )
    if table.headers and table.headers[0].upper() in {"ROLL", "RESULT"}:
        table.key = 0
    return table


def headerless_table(line: str, *, key: int | None = 0) -> Table:
    parts = spans(line)
    table = Table(
        headers=[""] * len(parts),
        starts=[start for start, _ in parts],
        key=key,
    )
    table.add_line(line)
    return table


def merge_header_line(table: Table, line: str) -> None:
    """Fold a wrapped header line (e.g. 'PROFILE') into its columns."""
    for start, text in spans(line):
        index = 0
        for column, origin in enumerate(table.starts):
            if start >= origin - TOLERANCE:
                index = column
        table.headers[index] += " " + text


def armor_table(header_line: str) -> Table:
    """Build a table for the two-line 'Base Thresholds / Base Score' header."""
    table = table_from_header(header_line, key=0)
    for index, header in enumerate(table.headers):
        if header in {"Thresholds", "Score"}:
            table.headers[index] = f"Base {header}"
    return table


def two_columns(lines: list[str], cut: int) -> tuple[list[str], list[str]]:
    for line in lines:
        if len(line) > cut and line[cut - 1] != " " and line[cut] != " ":
            raise RuntimeError(f"column cut {cut} splits a word: {line!r}")
    left = [line[:cut].rstrip() for line in lines]
    right = [line[cut:].rstrip() for line in lines]
    return left, right


def find_cut(lines: list[str], marker: str) -> int:
    for line in lines:
        index = line.find(marker)
        if index > 0:
            return index
    raise RuntimeError(f"marker not found for column cut: {marker!r}")


def index_of(lines: list[str], text: str) -> int:
    for index, line in enumerate(lines):
        if line.strip() == text:
            return index
    raise RuntimeError(f"landmark line not found: {text!r}")


def is_caps_heading(text: str) -> bool:
    stripped = text.strip()
    if not 2 < len(stripped) < 60:
        return False
    letters = [char for char in stripped if char.isalpha()]
    return bool(letters) and all(not char.islower() for char in letters)


def reflow(fragments: list[str]) -> str:
    return join_fragments(
        [fragment.strip() for fragment in fragments if fragment.strip()]
    )


@dataclass
class Flow:
    """Convert one column (or full-width band) of layout text to Markdown."""

    headings: dict[str, int] = field(default_factory=dict)
    caps_level: int = 4
    indent_subheads: bool = False
    tables: dict[str, dict] = field(default_factory=dict)

    def render(self, lines: list[str]) -> list[str]:
        blocks: list[str] = []
        paragraph: list[str] = []
        bullets: list[list[str]] = []
        table: Table | None = None
        heading: list[str] = []
        heading_level = self.caps_level

        def flush() -> None:
            nonlocal table
            if heading:
                blocks.append(f"{'#' * heading_level} {' '.join(heading)}")
                heading.clear()
            if paragraph:
                blocks.append(reflow(paragraph))
                paragraph.clear()
            if bullets:
                blocks.append("\n".join(f"- {reflow(item)}" for item in bullets))
                bullets.clear()
            if table is not None:
                blocks.append(table.markdown())
                table = None

        for line in lines:
            stripped = line.strip()
            indent = len(line) - len(line.lstrip())
            if not stripped:
                if heading:
                    flush()
                elif paragraph and paragraph[-1][-1:] in ".!?:":
                    flush()
                continue
            level = self.headings.get(stripped)
            if level is not None:
                flush()
                heading.append(stripped)
                heading_level = level
                flush()
                continue
            first_word = stripped.split()[0]
            if table is None and first_word in self.tables:
                flush()
                options = dict(self.tables[first_word])
                if options.pop("headerless", False):
                    table = headerless_table(line, **options)
                else:
                    table = table_from_header(line, **options)
                continue
            if table is not None:
                if is_caps_heading(stripped) or stripped in self.headings:
                    flush()
                else:
                    table.add_line(line)
                    continue
            if is_caps_heading(stripped):
                if paragraph or bullets:
                    flush()
                if not heading:
                    heading_level = self.caps_level
                    if self.indent_subheads and indent >= 2:
                        heading_level = self.caps_level + 1
                heading.append(stripped)
                continue
            if heading:
                flush()
            if stripped.startswith("•"):
                if paragraph:
                    flush()
                bullets.append([stripped[1:].strip()])
                continue
            if bullets:
                if indent >= 2:
                    bullets[-1].append(stripped)
                    continue
                flush()
            paragraph.append(stripped)
        flush()
        return blocks


def is_paragraph(block: str) -> bool:
    return not block.startswith(("#", "-", "|", ">"))


def flow_columns(lines: list[str], cut: int, left: Flow, right: Flow) -> list[str]:
    left_lines, right_lines = two_columns(lines, cut)
    blocks = left.render(left_lines)
    right_blocks = right.render(right_lines)
    # A paragraph can flow from the bottom of the left column into the top
    # of the right column; rejoin it when the break is mid-sentence.
    if (
        blocks
        and right_blocks
        and is_paragraph(blocks[-1])
        and blocks[-1][-1:] not in ".!?:"
        and is_paragraph(right_blocks[0])
        and right_blocks[0][:1].islower()
    ):
        blocks[-1] += " " + right_blocks.pop(0)
    return blocks + right_blocks


EQUIPMENT_TITLE_LEVELS = {
    "PRIMARY WEAPON TABLES": 4,
    "SECONDARY WEAPON TABLES": 4,
    "ARMOR TABLES": 4,
    "Physical Weapons": 6,
    "Magic Weapons": 6,
}


def equipment_markdown(
    lines: list[str],
    headings: dict[str, int],
    *,
    tier_level: int = 5,
    continuation: bool = False,
) -> list[str]:
    """Walk a weapons/armor/loot page: headings, notes, prose, and tables."""
    blocks: list[str] = []
    paragraph: list[str] = []
    paragraph_indent = 0
    table: Table | None = None
    pending_armor_header = False

    def flush() -> None:
        nonlocal table, pending_armor_header
        if paragraph:
            text = reflow(paragraph)
            if paragraph_indent >= 1:
                text = f"> {text}"
            blocks.append(text)
            paragraph.clear()
        if table is not None:
            blocks.append(table.markdown())
            table = None
        pending_armor_header = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if paragraph:
                flush()
            continue
        level = headings.get(stripped)
        if level is None and re.fullmatch(r"TIER \d \(LEVELS? [^)]+\)", stripped):
            level = tier_level
        if level is not None:
            flush()
            blocks.append(f"{'#' * level} {stripped}")
            continue
        parts = spans(line)
        if pending_armor_header:
            flush()
            table = armor_table(line)
            continue
        if [text for _, text in parts] == ["Base", "Base"]:
            flush()
            pending_armor_header = True
            continue
        if table is None and parts[0][1] in {"Name", "ROLL"} and len(parts) >= 3:
            flush()
            table = table_from_header(line)
            continue
        if table is None and continuation and not blocks and not paragraph:
            table = headerless_table(line, key=1)
            continue
        if table is not None:
            reach = parts[0][0] + len(parts[0][1])
            beyond = table.starts[min(2, len(table.starts) - 1)]
            if len(parts) == 1 and parts[0][0] <= table.starts[0] + TOLERANCE and (
                reach > beyond
            ):
                flush()
            else:
                table.add_line(line)
                continue
        indent = len(line) - len(line.lstrip())
        if paragraph and abs(indent - paragraph_indent) >= 2:
            flush()
        if not paragraph:
            paragraph_indent = indent
        paragraph.append(stripped)
    flush()
    return blocks


def loot_pane_markdown(lines: list[str]) -> list[str]:
    """Render one pane of a ROLL/Loot/description table."""
    return equipment_markdown(lines, {})


def split_loot_panes(lines: list[str]) -> list[str]:
    """Render a page region holding two side-by-side loot tables."""
    header_line = next(
        line
        for line in lines
        if len([True for _, text in spans(line) if text.upper() == "ROLL"]) == 2
    )
    cut = [start for start, text in spans(header_line) if text.upper() == "ROLL"][
        1
    ] - 1
    left, right = two_columns(lines, cut)
    return loot_pane_markdown(left) + loot_pane_markdown(right)


def trait_tables_markdown(lines: list[str], *, level: int = 5) -> list[str]:
    """Render the roll-benchmark tables labeled with rotated trait names."""
    blocks: list[str] = []
    label: str | None = None
    table: Table | None = None

    def flush() -> None:
        nonlocal label, table
        if table is not None:
            if label is None:
                raise RuntimeError("trait table without a trait label")
            blocks.append(f"{'#' * level} {label}")
            blocks.append(table.markdown())
            label = None
            table = None

    for line in lines:
        parts = spans(line)
        if not parts:
            continue
        if parts[0][1] in TRAIT_LABELS:
            if table is not None and label is not None:
                flush()
            label = parts[0][1]
            start = parts[0][0]
            line = line[:start] + " " * len(parts[0][1]) + line[start + len(parts[0][1]) :]
            parts = spans(line)
            if not parts:
                continue
        if parts[0][1] == "roll":
            if label is not None and table is not None:
                flush()
            elif table is not None:
                raise RuntimeError("trait table without a trait label")
            table = table_from_header(line, key=0)
            continue
        if table is None:
            raise RuntimeError(f"unexpected line outside trait table: {line!r}")
        table.add_line(line)
    flush()
    return blocks


def bullet_positions(lines: list[str]) -> list[int]:
    positions: list[int] = []
    for line in lines:
        for match in re.finditer("•", line):
            position = match.start()
            if not any(abs(position - seen) <= TOLERANCE for seen in positions):
                positions.append(position)
    return sorted(positions)


def bullet_list_markdown(lines: list[str], *, level: int = 5) -> list[str]:
    """Render a multi-column bullet list with embedded tier headings."""
    cuts = [max(position - 1, 0) for position in bullet_positions(lines)]
    blocks: list[str] = []
    for index, cut in enumerate(cuts):
        end = cuts[index + 1] if index + 1 < len(cuts) else None
        column = [line[cut:end].rstrip() for line in lines]
        blocks.extend(Flow(caps_level=level).render(column))
    return blocks


def merge_list_blocks(blocks: list[str]) -> list[str]:
    """Join consecutive bullet blocks split across page columns."""
    merged: list[str] = []
    for block in blocks:
        if merged and block.startswith("- ") and merged[-1].startswith("- "):
            merged[-1] += "\n" + block
        else:
            merged.append(block)
    return merged


def benchmark_table(lines: list[str]) -> Table:
    table: Table | None = None
    for line in lines:
        if not line.strip():
            continue
        if table is None:
            table = table_from_header(line, mode="center", key=None)
        else:
            table.add_line(line)
    if table is None:
        raise RuntimeError("benchmark table is empty")
    return table


def join(blocks: list[str]) -> str:
    return "\n\n".join(blocks)


# --- per-page renderers -----------------------------------------------------


def weapons_page(lines: list[str]) -> str:
    return join(equipment_markdown(lines, EQUIPMENT_TITLE_LEVELS))


def page_71(lines: list[str]) -> str:
    return join(
        equipment_markdown(
            lines,
            {"Heavy Frame Models": 5, "Arcane Frame Models": 5},
        )
    )


def page_72(lines: list[str]) -> str:
    tables_start = index_of(lines, "ARMOR TABLES")
    intro = lines[:tables_start]
    two_col_start = next(
        index for index, line in enumerate(intro) if line.strip().startswith("•")
    )
    cut = find_cut(intro, "While unarmored,")
    blocks = Flow(headings={"ARMOR": 3}).render(intro[:two_col_start])
    blocks += flow_columns(
        intro[two_col_start:],
        cut,
        Flow(caps_level=5),
        Flow(caps_level=5),
    )
    blocks += equipment_markdown(lines[tables_start:], EQUIPMENT_TITLE_LEVELS)
    return join(blocks)


def armor_continuation_page(lines: list[str]) -> str:
    return join(
        equipment_markdown(lines, EQUIPMENT_TITLE_LEVELS, continuation=True)
    )


def rarity_intro_blocks(lines: list[str], headings: dict[str, int]) -> list[str]:
    """Render the shared intro shape of the loot and consumables sections."""
    bullets_start = next(
        index for index, line in enumerate(lines) if line.strip().startswith("•")
    )
    cut = find_cut(lines, "• Rare (3d12 or 4d12):")
    blocks = Flow(headings=headings).render(lines[:bullets_start])
    blocks += merge_list_blocks(
        flow_columns(lines[bullets_start:], cut, Flow(), Flow())
    )
    return blocks


def page_75(lines: list[str]) -> str:
    table_title = index_of(lines, "Core Set Items")
    blocks = rarity_intro_blocks(lines[:table_title], {"LOOT": 3, "ITEMS": 4})
    blocks.append("##### Core Set Items")
    blocks += equipment_markdown(lines[table_title + 1 :], {})
    return join(blocks)


def loot_page(lines: list[str]) -> str:
    return join(equipment_markdown(lines, {"Additional Items": 5}))


def page_80(lines: list[str]) -> str:
    table_title = index_of(lines, "Core Set Consumables")
    blocks = rarity_intro_blocks(lines[:table_title], {"CONSUMABLES": 3})
    blocks.append("##### Core Set Consumables")
    header_index = next(
        index
        for index in range(table_title + 1, len(lines))
        if lines[index].split() and lines[index].split()[0] == "ROLL"
    )
    for line in lines[table_title + 1 : header_index]:
        if line.strip():
            blocks.append(f"> {line.strip()}")
    blocks += split_loot_panes(lines[header_index:])
    return join(blocks)


def consumables_panes_page(lines: list[str]) -> str:
    blocks: list[str] = []
    start = 0
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped == "Additional Consumables":
            blocks.append("##### Additional Consumables")
            start = index + 1
        elif stripped.startswith("The following table includes"):
            blocks.append(f"> {stripped}")
            start = index + 1
        else:
            break
    blocks += split_loot_panes(lines[start:])
    return join(blocks)


def page_84(lines: list[str]) -> str:
    cut = find_cut(lines, "GOLD")
    left, right = two_columns(lines, cut)
    blocks = loot_pane_markdown(left)
    optional = index_of(right, "Optional Rule: Gold Coins")
    blocks += Flow().render(right[:optional])
    quote_lines = [line.strip() for line in right[optional:] if line.strip()]
    blocks.append(f"> {quote_lines[0]}\n> {reflow(quote_lines[1:])}")
    return join(blocks)


def page_88(lines: list[str]) -> str:
    benchmarks = index_of(lines, "DIFFICULTY BENCHMARKS")
    agility_start = next(
        index
        for index, line in enumerate(lines)
        if index > benchmarks
        and spans(line)
        and spans(line)[0][1] in {"roll", "AGILITY"}
    )
    cut = find_cut(lines[:benchmarks], "If you find yourself")
    blocks = flow_columns(
        lines[:benchmarks],
        cut,
        Flow(tables={"Incidental": {"headerless": True}}),
        Flow(),
    )
    blocks.append("#### DIFFICULTY BENCHMARKS")
    middle = lines[benchmarks + 1 : agility_start]
    cut = find_cut(middle, "When a player makes")
    blocks += flow_columns(middle, cut, Flow(), Flow())
    blocks += trait_tables_markdown(lines[agility_start:])
    return join(blocks)


def page_89(lines: list[str]) -> str:
    return join(trait_tables_markdown(lines))


def page_90(lines: list[str]) -> str:
    bottom = next(
        index
        for index, line in enumerate(lines)
        if line.startswith("GIVING ADVANTAGE AND")
    )
    blocks = trait_tables_markdown(lines[:bottom])
    cut = find_cut(lines[bottom:], "If an adversary has advantage")
    blocks += flow_columns(
        lines[bottom:],
        cut,
        Flow(indent_subheads=True),
        Flow(caps_level=5),
    )
    return join(blocks)


def page_95(lines: list[str]) -> str:
    list_heading = index_of(lines, "ADVERSARIES BY TIER")
    blocks = ["#### ADVERSARY STAT BLOCK BENCHMARKS"]
    blocks.append(benchmark_table(lines[1:list_heading]).markdown())
    blocks.append("#### ADVERSARIES BY TIER")
    body = lines[list_heading + 1 :]
    list_start = next(
        index for index, line in enumerate(body) if "•" in line or "TIER" in line
    )
    blocks += Flow().render(body[:list_start])
    blocks += merge_list_blocks(bullet_list_markdown(body[list_start:]))
    return join(blocks)


def page_96(lines: list[str]) -> str:
    return join(merge_list_blocks(bullet_list_markdown(lines)))


def page_159(lines: list[str]) -> str:
    benchmarks = index_of(lines, "BENCHMARK STATISTICS FOR ENVIRONMENTS BY TIER")
    stat_blocks = index_of(lines, "ENVIRONMENT STAT BLOCKS BY TIER")
    blocks = ["#### ADAPTING ENVIRONMENTS"]
    cut = find_cut(lines[1:benchmarks], "framework is there")
    blocks += flow_columns(lines[1:benchmarks], cut, Flow(), Flow())
    blocks.append("#### BENCHMARK STATISTICS FOR ENVIRONMENTS BY TIER")
    blocks.append(benchmark_table(lines[benchmarks + 1 : stat_blocks]).markdown())
    blocks.append("#### ENVIRONMENT STAT BLOCKS BY TIER")
    body = lines[stat_blocks + 1 :]
    list_start = next(
        index for index, line in enumerate(body) if "TIER 1" in line
    )
    blocks += Flow().render(body[:list_start])
    blocks += merge_list_blocks(bullet_list_markdown(body[list_start:]))
    return join(blocks)


def page_191(lines: list[str]) -> str:
    return join(
        equipment_markdown(
            lines,
            {
                "EVERYDAY HERO STARTING EQUIPMENT": 3,
                "Primary Physical Weapons": 4,
                "Primary Magic Weapons": 4,
            },
        )
    )


def page_192(lines: list[str]) -> str:
    feasts = next(
        index for index, line in enumerate(lines) if line.startswith("Feasts")
    )
    blocks = equipment_markdown(
        lines[:feasts],
        {"Secondary Weapons": 4, "Armor": 4},
    )
    cut = find_cut(lines[feasts:], "When a PC acquires an ingredient,")
    blocks += flow_columns(
        lines[feasts:],
        cut,
        Flow(headings={"Feasts": 3}),
        Flow(
            headings={"Hit Points to Ingredients Guide": 5},
            tables={"maximum": {"mode": "center", "key": 0}},
        ),
    )
    return join(blocks)


def page_193(lines: list[str]) -> str:
    cut = find_cut(lines, "Once preparation is complete,")
    return join(
        flow_columns(
            lines,
            cut,
            Flow(
                headings={"Environmental Ingredients Guide": 5},
                indent_subheads=True,
                tables={"hope": {"mode": "center", "key": 0}},
            ),
            Flow(
                headings={"What kind of ingredient is it?": 5},
                indent_subheads=True,
                tables={"result": {"key": 0}},
            ),
        )
    )


def page_194(lines: list[str]) -> str:
    cut = find_cut(lines, "ADVANCED FEASTING")
    left, right = two_columns(lines, cut)
    blocks = Flow(
        headings={"What’s interesting about it?": 5},
        tables={"result": {"key": 0}},
    ).render(left)
    header = next(
        index for index, line in enumerate(right) if line.split()[:1] == ["NAME"]
    )
    profile = index_of(right, "PROFILE")
    restaurants = index_of(right, "RESTAURANTS")
    table = table_from_header(
        right[header],
        row_start=lambda cells: bool(re.match(r"[A-Z][^:]*:", cells[2])),
    )
    merge_header_line(table, right[profile])
    for line in right[profile + 1 : restaurants]:
        if line.strip():
            table.add_line(line)
    blocks += Flow(headings={"Example Special Ingredients": 5}).render(
        right[:header]
    )
    blocks.append(table.markdown())
    blocks += Flow().render(right[restaurants:])
    return join(blocks)


def page_197(lines: list[str]) -> str:
    return join(
        equipment_markdown(
            lines,
            {
                "WESTERN CAMPAIGNS": 3,
                "WEAPONS & LOOT": 4,
                "Primary Weapons": 5,
                "Secondary Weapons": 5,
            },
        )
    )


def page_201(lines: list[str]) -> str:
    return join(
        equipment_markdown(
            lines,
            {
                "MONSTER HUNTING CAMPAIGNS": 3,
                "MONSTER HUNTING EQUIPMENT": 4,
                "Primary Weapons": 5,
                "Secondary Weapons": 5,
                "Armor": 5,
            },
        )
    )


RENDERERS = {
    **{page: weapons_page for page in range(56, 70)},
    71: page_71,
    72: page_72,
    73: armor_continuation_page,
    74: weapons_page,
    75: page_75,
    76: loot_page,
    77: loot_page,
    78: loot_page,
    79: loot_page,
    80: page_80,
    81: consumables_panes_page,
    82: consumables_panes_page,
    83: consumables_panes_page,
    84: page_84,
    88: page_88,
    89: page_89,
    90: page_90,
    95: page_95,
    96: page_96,
    159: page_159,
    191: page_191,
    192: page_192,
    193: page_193,
    194: page_194,
    197: page_197,
    201: page_201,
}


def render_layout_page(page_number: int, page_text: str) -> str:
    lines = page_text.splitlines()
    indents = [len(line) - len(line.lstrip()) for line in lines if line.strip()]
    common_indent = min(indents, default=0)
    if common_indent:
        lines = [line[common_indent:] for line in lines]
    return RENDERERS[page_number](lines)
