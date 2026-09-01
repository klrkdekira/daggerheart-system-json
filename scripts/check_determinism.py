#!/usr/bin/env python3
"""Assert that a clean rebuild reproduces the checked-in corpus byte for byte."""

from __future__ import annotations

import filecmp
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def compare_trees(expected: Path, actual: Path) -> list[str]:
    differences: list[str] = []

    def walk(comparison: filecmp.dircmp) -> None:
        for name in comparison.left_only:
            differences.append(f"missing from rebuild: {comparison.left}/{name}")
        for name in comparison.right_only:
            differences.append(f"extra in rebuild: {comparison.right}/{name}")
        for name in comparison.diff_files:
            differences.append(f"differs: {comparison.left}/{name}")
        for sub in comparison.subdirs.values():
            walk(sub)

    walk(filecmp.dircmp(expected, actual, ignore=[]))
    return differences


def main() -> None:
    with tempfile.TemporaryDirectory() as scratch:
        out = Path(scratch)
        # The builder reads SRD.md and the PDF from --root and writes --out.
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "build_corpus.py"),
             "--root", str(ROOT), "--out", str(out)],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "build_indexes.py"),
             "--root", str(out)],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "build_llms.py"),
             "--root", str(out)],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        (out / "systems").mkdir()
        shutil.copy(ROOT / "systems" / "context.jsonld", out / "systems")
        for script in ("build_vocab.py", "build_record_pages.py", "build_sitemap.py"):
            subprocess.run(
                [sys.executable, str(ROOT / "scripts" / script),
                 "--root", str(out)],
                check=True,
                stdout=subprocess.DEVNULL,
            )
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "build_schemas.py"),
             "--root", str(out)],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        differences = compare_trees(ROOT / "objects", out / "objects")
        differences += compare_trees(ROOT / "systems", out / "systems")
        differences += compare_trees(ROOT / "vocab", out / "vocab")
        differences += compare_trees(ROOT / "records", out / "records")
        for name in ("llms.txt", "llms-full.txt", "sitemap.xml"):
            if (ROOT / name).read_bytes() != (out / name).read_bytes():
                differences.append(f"differs: {name}")
    if differences:
        print("Determinism check failed:")
        for difference in differences[:20]:
            print(f"- {difference}")
        sys.exit(1)
    print("Clean rebuild is byte-identical to the checked-in corpus.")


if __name__ == "__main__":
    main()
