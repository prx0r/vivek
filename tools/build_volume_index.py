#!/usr/bin/env python3
"""Build VOLUME-INDEX.md from batch STATS (run when volumes complete).

  python3 tools/build_volume_index.py
Reads /tmp/opencode/vivek_batch_all.log STATS lines, keeps the latest per slug.
"""
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG = "/tmp/opencode/vivek_batch_all.log"


def main():
    latest = {}
    for line in open(LOG, encoding="utf-8", errors="replace"):
        if line.startswith("STATS "):
            d = json.loads(line[6:])
            latest[d["slug"]] = d
    order = (["introduction", "volume_1", "volume_2", "volume_3", "volume_4",
              "volume_5", "volume_6", "volume_7", "volume_8", "volume_9",
              "unpublished", "appendices"])
    out = ["# Complete Works — rendered volume index", "",
           "English-only audio (Indic blocks skipped, see LANGUAGE-POLICY.md).",
           "R2: `r2:longform-audio/vivek/`. Old man = the Master, granny = host.", "",
           "| volume | duration | size | object |", "|---|---:|---:|---|"]
    tot = 0
    for slug in order:
        d = latest.get(slug)
        if not d:
            out.append(f"| {slug} | — | — | (not yet rendered) |")
            continue
        dur = d["duration_s"]
        tot += dur
        out.append(f"| {slug} | {int(dur//3600)}h {int(dur%3600//60)}m | "
                   f"{d['size_kb']//1024} MB | `{slug}.mp3` |")
    out.append(f"\n**Total voiced: {int(tot//3600)} h {int(tot%3600//60)} min**")
    path = os.path.join(ROOT, "VOLUME-INDEX.md")
    open(path, "w", encoding="utf-8").write("\n".join(out) + "\n")
    print(f"wrote {path} ({len(latest)} slugs seen)")


if __name__ == "__main__":
    main()
