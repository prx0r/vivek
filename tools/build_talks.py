#!/usr/bin/env python3
"""Extract the 13 standalone Complete Talks from the volume files + their block ranges.

Writes: output/talks/<slug>.md  (whole section, verbatim, own ## heading)
        tts/talk_ranges.json     (vol, slug, start/end canonical block indices)
Volume renders then EXCLUDE these ranges — each word rendered exactly once.
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from batch_voices import parse_blocks  # noqa: E402

# (volume, exact heading in volume md, slug)
TALKS = [
    ("volume_2", "THE NECESSITY OF RELIGION", "necessity-of-religion"),
    ("volume_2", "THE REAL NATURE OF MAN", "real-nature-of-man"),
    ("volume_2", "MAYA AND ILLUSION", "maya-and-illusion"),
    ("volume_2", "IMMORTALITY", "immortality"),
    ("volume_2", "THE ATMAN", "atman"),
    ("volume_2", "THE POWERS OF THE MIND", "powers-of-the-mind"),
    ("volume_3", "THE FREE SOUL", "free-soul"),
    ("volume_4", "CHRIST, THE MESSENGER", "christ-the-messenger"),
    ("volume_4", "THE CLAIMS OF RELIGION", "claims-of-religion"),
    ("volume_4", "THE GREAT TEACHERS OF THE WORLD", "great-teachers"),
    ("volume_4", "THE RAMAYANA", "ramayana"),
    ("volume_4", "THOUGHTS ON THE GITA", "thoughts-on-the-gita"),
    ("volume_4", "IS THE SOUL IMMORTAL?", "is-the-soul-immortal"),
]


def main():
    out = os.path.join(ROOT, "output", "talks")
    os.makedirs(out, exist_ok=True)
    ranges, missing = [], []
    for vol, heading, slug in TALKS:
        blocks = parse_blocks(os.path.join(ROOT, "output", vol + ".md"))
        hits = [i for i, b in enumerate(blocks) if b["head"] and b["text"] == heading]
        if len(hits) != 1:
            missing.append((vol, heading, len(hits)))
            continue
        start = hits[0]
        end = next((i for i in range(start + 1, len(blocks)) if blocks[i]["head"]),
                   len(blocks))
        lines = []
        skipped_indic = 0
        for b in blocks[start:end]:
            if b.get("indic"):
                skipped_indic += 1
                continue
            if b["head"]:
                lines.append("## " + b["text"])
            elif b.get("host"):
                lines.append("*" + b["text"] + "*")   # keep italic so reparse knows granny
            else:
                lines.append(b["text"])
        with open(os.path.join(out, slug + ".md"), "w", encoding="utf-8") as f:
            f.write("\n\n".join(lines) + "\n")
        words = sum(len(b["text"].split()) for b in blocks[start + 1:end]
                    if not b.get("indic"))
        ranges.append({"vol": vol, "slug": slug, "heading": heading,
                       "start": start, "end": end, "words": words})
        print(f"{vol}  {slug:<24} blocks {start}-{end - 1}  {words:>6,}w  ~{words/150:.0f} min")
        if skipped_indic:
            print(f"           ↳ language guard: dropped {skipped_indic} Indic block(s)")
    if missing:
        print(f"MISSING/AMBIGUOUS: {missing}", file=sys.stderr)
        sys.exit(1)
    with open(os.path.join(ROOT, "tts", "talk_ranges.json"), "w", encoding="utf-8") as f:
        json.dump(ranges, f, indent=1)
    print(f"\n{len(ranges)} talks, {sum(r['words'] for r in ranges):,} words "
          f"-> output/talks/ + tts/talk_ranges.json")


if __name__ == "__main__":
    main()
