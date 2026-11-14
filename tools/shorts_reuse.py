#!/usr/bin/env python3
"""Shorts REUSE planner: can each short be cut from already-cached group audio
(fish-free), and is the cut EXACT (paragraph-boundary aligned) or APPROX?

Maps each short's paragraph span → the group(s) covering it (groups are whole
paragraphs and cached as mp3 by sha1(voice|directed) on vps).

  python3 tools/shorts_reuse.py            # availability table + totals
Nothing renders here — this only reports.
"""
import json
import os
import re
import sys
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import batch_voices as bv  # noqa: E402
from tts_status import cached_set  # noqa: E402


def body_block_index(path, chapter, para_range, preview=""):
    """chapter-local paragraph index → index into parse_blocks(path).
    Handles nbsp/whitespace differences and duplicate chapter titles
    (disambiguates via the entry's preview text)."""
    blocks = bv.parse_blocks(path)
    occ, cur = [], None
    for i, b in enumerate(blocks):
        if b["head"]:
            cur = {"head": b["text"], "body": []}
            occ.append(cur)
            continue
        if b.get("host") and not b["head"]:
            continue                      # italic line: not part of numbering
        if cur is not None:
            cur["body"].append(i)
    norm = lambda x: re.sub(r"\s+", " ", (x or "").replace("\xa0", " ")).strip()
    if chapter:
        cands = [o for o in occ if norm(o["head"]) == norm(chapter)]
        if not cands:
            cands = [o for o in occ if norm(o["head"]).startswith(norm(chapter)[:30])]
    else:
        cands = occ[:1]
    if len(cands) != 1 and preview:
        pv = norm(preview[:40]).lower()
        by_pv = [o for o in cands
                 if any(norm(blocks[i]["text"]).lower().startswith(pv)
                        for i in o["body"])]
        if by_pv:
            cands = by_pv
    if len(cands) != 1:
        raise RuntimeError(f"chapter {chapter!r}: {len(cands)} occurrences")
    nums = [int(n) for n in re.findall(r"\d+", para_range)]
    body = cands[0]["body"]
    return blocks, body[nums[0]], body[nums[-1]]


def filtered_pos(orig_lo, orig_hi, blocks, exclude):
    """positions of orig indices within the filtered (exclude-removed) list"""
    keep = [i for i in range(len(blocks))
            if not any(s <= i < e for s, e in (exclude or []))]
    rank = {orig: pos for pos, orig in enumerate(keep)}
    return rank[orig_lo], rank[orig_hi], keep


def main():
    rows = [json.loads(l) for l in open(os.path.join(ROOT, "shorts", "ledger.jsonl"),
                                         encoding="utf-8") if l.strip()]
    cached = cached_set()
    rng = json.load(open(os.path.join(ROOT, "tts", "talk_ranges.json")))
    srcs = sorted({r["file"].replace("output/", "").replace(".md", "") for r in rows})
    groups_by_slug = {}
    for slug in srcs:
        src = os.path.join(ROOT, "output", slug + ".md")
        excl = None
        if re.fullmatch(r"volume_\d+", slug):
            excl = [(x["start"], x["end"]) for x in rng if x["vol"] == slug]
        groups_by_slug[slug] = bv.build_groups(src, excl)

    stats = {"exact": [], "approx": [], "pending": []}
    print(f"{'id':<6} {'slug':<26} {'status':<16} note")
    print("-" * 88)
    for r in rows:
        slug = r["file"].replace("output/", "").replace(".md", "")
        path = os.path.join(ROOT, "output", slug + ".md")
        excl = None
        if re.fullmatch(r"volume_\d+", slug):
            excl = [(x["start"], x["end"]) for x in rng if x["vol"] == slug]
        try:
            blocks, o_lo, o_hi = body_block_index(path, r.get("chapter", ""),
                                                   r["para"], r.get("preview", ""))
            p_lo, p_hi, _keep = filtered_pos(o_lo, o_hi, blocks, excl)
        except Exception as e:
            print(f"{r['id']:<6} {slug:<26} {'ERROR':<16} {e}")
            continue
        gs = groups_by_slug[slug]
        # covering group run
        gi = None
        for i, g in enumerate(gs):
            if g["blocks"][0] <= p_lo <= g["blocks"][-1]:
                gi = i
                break
        if gi is None:
            print(f"{r['id']:<6} {slug:<26} {'ERROR':<16} span not in groups")
            continue
        gj = gi
        while gs[gj]["blocks"][-1] < p_hi:
            gj += 1
        run = gs[gi:gj + 1]
        exact = run[0]["blocks"][0] == p_lo and run[-1]["blocks"][-1] == p_hi
        all_cached = all((slug, g["sha"]) in cached for g in run)
        if exact:
            extra_w = 0
        else:
            span = (list(range(run[0]["blocks"][0], p_lo)) +
                    list(range(p_hi + 1, run[-1]["blocks"][-1] + 1)))
            extra_w = sum(len(blocks[i]["text"].split()) for i in span)
        if not all_cached:
            status, note = "PENDING", f"{sum(1 for g in run if (slug,g['sha']) in cached)}/{len(run)} groups cached — batch will fill it"
            stats["pending"].append(r["id"])
        elif exact:
            status, note = "READY-EXACT", f"{len(run)} group(s), fish-free"
            stats["exact"].append(r["id"])
        else:
            status, note = "READY-APPROX", f"leaks ±{extra_w}w (~{round(extra_w/2.5)}s) from straddling group(s)"
            stats["approx"].append(r["id"])
        print(f"{r['id']:<6} {slug:<26} {status:<16} {note}")

    print("-" * 88)
    print(f"TOTALS: exact {len(stats['exact'])} · approx {len(stats['approx'])} · "
          f"pending {len(stats['pending'])} · of {len(rows)}")
    missing_groups = 0
    print(f"\nfish-free path: vps-side concat of cached group mp3s per range "
          f"(still gated on owner approval)")


if __name__ == "__main__":
    main()
