"""Regenerate src/datafuzzy/given_names.txt: common English given names.

    uv run tools/update_names.py

Source: US Social Security Administration baby names (public domain), the top 1000
per year and sex, as mirrored at github.com/hadley/data-baby-names (SSA's own site
refuses scripted downloads). Names given since 1940 are ranked by their summed
yearly share and the most common NAMES are kept.
"""

from __future__ import annotations

import csv
import io
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "src/datafuzzy/given_names.txt"
URL = ("https://raw.githubusercontent.com/hadley/data-baby-names/"
       "b6525579cf7d2816e77fa885299445d15a09c906/baby-names.csv")
SINCE = 1940
NAMES = 4000
# Names that, written inside Chinese text, are far more often a word, a month, a place
# or a company than a person.
NOT_NAMES = {
    "April", "May", "June", "August", "Summer", "Autumn", "Spring",
    "Unknown", "Baby", "Infant", "Junior", "Major", "Cash", "King", "Queen", "Prince",
    "Princess", "Royal", "Justice", "Genesis", "Destiny", "Unique", "Precious", "Miracle",
    "Liberty", "Journey", "Essence", "Heaven", "Harmony", "Serenity", "Sincere", "Noble",
    "Chance", "Brain", "Stone", "Rock", "Storm", "Star", "Sky", "Diamond", "Velvet",
    "Karma", "Ace", "Chip", "Mac", "Gay", "Dick", "Will",
    "China", "German", "Boston", "Montana", "Phoenix", "Dell",
}


def main() -> None:
    with urllib.request.urlopen(URL) as resp:
        rows = csv.DictReader(io.StringIO(resp.read().decode()))
        share: Counter[str] = Counter()
        for row in rows:
            if int(row["year"]) >= SINCE:
                share[row["name"]] += float(row["percent"])
    names = [n for n, _ in share.most_common(NAMES) if n not in NOT_NAMES]
    OUT.write_text("\n".join(sorted(names)) + "\n")
    print(f"wrote {len(names)} names to {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
