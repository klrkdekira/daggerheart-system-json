"""Structural regression fixtures for the extraction pipeline."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import build_corpus  # noqa: E402


def load(collection: str, slug: str) -> dict:
    path = ROOT / "objects" / collection / f"{slug}.jsonld"
    return json.loads(path.read_text())


class ExtractionFixtures(unittest.TestCase):
    def test_adversary_stat_decomposition(self) -> None:
        record = load("adversaries", "acid-burrower")
        self.assertEqual(record["tier"], 1)
        self.assertEqual(record["role"], "Solo")
        self.assertEqual(record["difficulty"], 14)
        self.assertEqual(record["thresholds"], "8/15")
        self.assertEqual(record["hitPoints"], 8)
        self.assertEqual(record["stress"], 3)
        self.assertEqual(record["standardAttack"]["name"], "Claws")
        self.assertEqual(record["standardAttack"]["damage"], "1d12+2 phy")
        kinds = [feature["kind"] for feature in record["features"]]
        self.assertEqual(kinds, ["Passive", "Action", "Action", "Reaction"])

    def test_minion_none_thresholds(self) -> None:
        record = load("adversaries", "jagged-knife-lackey")
        self.assertEqual(record["thresholds"], "None")

    def test_environment_adversary_links(self) -> None:
        record = load("environments", "abandoned-grove")
        self.assertEqual(record["category"], "Exploration")
        slugs = {ref["@id"].rsplit("/", 1)[1] for ref in record["potentialAdversaries"]}
        self.assertIn("bear", slugs)
        self.assertIn("young-dryad", slugs)

    def test_weapon_trait_column_repair(self) -> None:
        # "Fighting Cloak Presence" prints with a single space before the trait.
        record = load("weapons", "fighting-cloak")
        self.assertEqual(record["trait"], "Presence")
        self.assertEqual(record["category"], "secondary")

    def test_tiered_weapon_damage(self) -> None:
        record = load("weapons", "revolver")
        self.assertEqual(record["variant"], "western")
        self.assertEqual(len(record["tieredDamage"]), 4)
        self.assertTrue(record["tieredDamage"][0].startswith("Tier 1:"))

    def test_armor_continuation_table(self) -> None:
        # Page 73 continues the Tier 2 armor table without a header row.
        record = load("armor", "stormthread-habit")
        self.assertEqual(record["tier"], 2)
        self.assertEqual(record["baseThresholds"], "9 / 20")

    def test_loot_rolls_are_complete(self) -> None:
        for collection in ("items", "consumables"):
            rolls: dict[str, list[int]] = {"core-set": [], "expansion": []}
            for path in (ROOT / "objects" / collection).glob("*.jsonld"):
                record = json.loads(path.read_text())
                rolls[record["itemSet"]].append(record["roll"])
            for values in rolls.values():
                self.assertEqual(sorted(values), list(range(1, 61)))

    def test_domain_card_across_group_boundary(self) -> None:
        # The appendix column layout carries Blade cards past the BONE heading.
        record = load("domain-cards", "reapers-strike")
        self.assertTrue(record["domain"]["@id"].endswith("/domains/blade"))
        self.assertEqual(record["level"], 9)

    def test_class_relationships(self) -> None:
        record = load("classes", "druid")
        self.assertEqual(record["startingEvasion"], 10)
        self.assertEqual(len(record["subclasses"]), 2)
        domains = {ref["@id"].rsplit("/", 1)[1] for ref in record["domains"]}
        self.assertEqual(domains, {"arcana", "sage"})

    def test_subclass_stages(self) -> None:
        record = load("subclasses", "warden-of-renewal")
        stages = {feature["stage"] for feature in record["features"]}
        self.assertEqual(stages, {"foundation", "specialization", "mastery"})

    def test_beastform_statistics(self) -> None:
        record = load("beastforms", "agile-scout")
        self.assertEqual(record["traitBonus"], "Agility +1")
        self.assertEqual(record["evasionBonus"], 2)
        self.assertEqual(record["attack"]["damage"], "d4 phy")
        self.assertEqual(record["advantageOn"], ["deceive", "locate", "sneak"])

    def test_table_rows_link_their_section(self) -> None:
        record = load("weapons", "greatsword")
        self.assertTrue(
            record["fromSection"]["@id"].endswith("/rules/primary-weapon-tables")
        )

    def test_html_page_links(self) -> None:
        record = load("sources", "daggerheart-srd-2-0")
        self.assertTrue(record["htmlPage"]["@id"].endswith(
            "/records/sources/daggerheart-srd-2-0/"
        ))
        page = ROOT / "records" / "sources" / "daggerheart-srd-2-0" / "index.html"
        self.assertTrue(page.is_file())

    def test_source_digests(self) -> None:
        import hashlib

        record = load("sources", "daggerheart-srd-2-0")
        digest = hashlib.sha256((ROOT / "SRD.md").read_bytes()).hexdigest()
        self.assertEqual(record["contentDigest"], f"sha256:{digest}")
        self.assertEqual(record["pdfDigest"], build_corpus.PDF_DIGEST)


class HelperFixtures(unittest.TestCase):
    def test_slugify(self) -> None:
        self.assertEqual(build_corpus.slugify("JACK-O’-LANTERN"), "jack-o-lantern")
        self.assertEqual(
            build_corpus.slugify("FALLEN WARLORD: REALM-BREAKER"),
            "fallen-warlord-realm-breaker",
        )

    def test_title_name(self) -> None:
        self.assertEqual(build_corpus.title_name("DEMON OF WRATH"), "Demon of Wrath")
        self.assertEqual(
            build_corpus.title_name("WILL-O’-THE-WISPS"), "Will-O’-The-Wisps"
        )

    def test_feature_parsing(self) -> None:
        features, preamble = build_corpus.parse_features([
            "**Spit Acid - Action:** Make an attack.",
            "A follow-up paragraph.",
            "**Slow - Passive:** No spotlight.",
        ])
        self.assertEqual(preamble, [])
        self.assertEqual(features[0]["name"], "Spit Acid")
        self.assertEqual(features[0]["kind"], "Action")
        self.assertIn("follow-up", features[0]["rulesText"])
        self.assertEqual(features[1]["kind"], "Passive")


if __name__ == "__main__":
    unittest.main()
