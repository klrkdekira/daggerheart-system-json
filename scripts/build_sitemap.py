#!/usr/bin/env python3
"""Generate sitemap.xml: the exact published URL inventory."""

from __future__ import annotations

import argparse
from pathlib import Path

from build_corpus import BASE, COLLECTIONS

# Deterministic lastmod: the publication date of the source SRD 2.0 PDF.
LASTMOD = "2026-08-25"

FIXED = [
    "",
    "llms.txt",
    "llms-full.txt",
    "vocab/",
    "vocab/terms.json",
    "objects/daggerheart-system-data.jsonld",
    "objects/daggerheart-system-data.bundle.jsonld",
    "objects/search-index.json",
    "objects/collection-index.json",
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    root = args.root
    urls = [BASE + suffix for suffix in FIXED]
    for collection, _ in COLLECTIONS:
        for path in sorted((root / "objects" / collection).glob("*.jsonld")):
            urls.append(f"{BASE}records/{collection}/{path.stem}/")
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    lines.extend(
        f"  <url><loc>{url}</loc><lastmod>{LASTMOD}</lastmod></url>" for url in urls
    )
    lines.append("</urlset>")
    (root / "sitemap.xml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote sitemap.xml with {len(urls)} URLs")


if __name__ == "__main__":
    main()
