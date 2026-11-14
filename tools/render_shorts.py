#!/usr/bin/env python3
"""Render approved shorts (extract-only clips) with the old-man voice.

SAFE BY DEFAULT: does nothing unless --render is passed.

  python3 tools/render_shorts.py --tier S --dry-run      # list plan
  python3 tools/render_shorts.py --tier S --render       # render S tier
  python3 tools/render_shorts.py --ids S004,S009 --render

Each short: verbatim span text -> tts/shorts/<id>.txt -> render_tts.py
(old man voice, house norm, R2: longform-audio/vivek/shorts/<id>.mp3).
Refuses any span containing Indic script; skips ids already in R2/marked done.
"""
import argparse
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from mine_shorts import paragraphs as talk_paras  # noqa: E402

INDIC = re.compile("[\u0900-\u097F\u0980-\u09FF\u0A00-\u0BFF\u0C00-\u0D7F]")
OUTDIR = os.path.join(ROOT, "tts", "shorts")


def chapter_paras(vol, ch, snip=None):
    text = open(os.path.join(ROOT, "output", vol + ".md"), encoding="utf-8").read()
    chaps = re.split(r"(?m)^## ", text)[1:]
    heads = [c.split("\n", 1)[0].strip() for c in chaps]
    idx = [i for i, h in enumerate(heads) if h == ch]
    if len(idx) != 1 and snip:
        idx = [i for i in idx if snip in chaps[i]]
    body = chaps[idx[0]].partition("\n")[2]
    return [t.strip() for t in re.split(r"\n\s*\n", body)
            if t.strip() and not t.strip().startswith("*")]


def short_text(r):
    ps = (chapter_paras(r["volume"], r["chapter"], r["preview"][:40])
          if "chapter" in r else talk_paras(os.path.join(ROOT, r["file"])))
    nums = [int(n) for n in re.findall(r"\d+", r["para"])]
    return " ".join(ps[i] for i in range(nums[0], nums[-1] + 1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tier", action="append", default=[])
    ap.add_argument("--ids", default="")
    ap.add_argument("--render", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    rows = [json.loads(l) for l in
            open(os.path.join(ROOT, "shorts", "ledger.jsonl"), encoding="utf-8") if l.strip()]
    ids = {i.strip() for i in a.ids.split(",") if i.strip()}
    plan = []
    for r in rows:
        if r.get("tier") == "C" and not ids:
            continue
        if ids and r["id"] not in ids:
            continue
        if a.tier and r["tier"] not in a.tier and r["id"] not in ids:
            continue
        plan.append(r)
    if not plan:
        sys.exit("nothing selected (tiers: %s, ids: %s)" % (a.tier or "all", ids or "-"))

    os.makedirs(OUTDIR, exist_ok=True)
    todo = []
    for r in plan:
        txt = short_text(r)
        if INDIC.search(txt):
            print(f"SKIP {r['id']}: Indic script in span")
            continue
        if not (60 <= len(txt.split()) / 2.5 <= 120):
            print(f"SKIP {r['id']}: duration drift ({len(txt.split())}w)")
            continue
        mark = f"/tmp/opencode/done_short_{r['id']}"
        if os.path.exists(mark):
            print(f"done  {r['id']}")
            continue
        todo.append((r, txt))

    print(f"\nplan: {len(todo)} shorts "
          f"({sum(len(t.split()) for _, t in todo)} words ≈ "
          f"{sum(len(t.split()) for _, t in todo)/2.5/60:.1f} min)")
    for r, t in todo:
        print(f"  {r['id']} [{r['tier']}] {r['sec']}s  {t[:70]}…")

    if not a.render:
        print("\n(dry run — pass --render to voice these)")
        return
    fails = []
    for r, txt in todo:
        path = os.path.join(OUTDIR, r["id"] + ".txt")
        open(path, "w", encoding="utf-8").write(txt)
        pr = subprocess.run(["python3", os.path.join(ROOT, "tools", "render_tts.py"),
                             path, "--slug", "shorts/" + r["id"]],
                            text=True)
        if pr.returncode == 0:
            open(f"/tmp/opencode/done_short_{r['id']}", "w").write("ok")
            print(f"DONE {r['id']}")
        else:
            fails.append(r["id"])
            print(f"FAIL {r['id']}")
    print(f"\nfinished: {len(todo)-len(fails)} ok, {len(fails)} failed {fails}")
    sys.exit(0 if not fails else 1)


if __name__ == "__main__":
    main()
