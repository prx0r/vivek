#!/usr/bin/env python3
"""Mine a talk for SHORT candidates (60–100s = 140–260 words @150wpm).

Extract-only: candidates are contiguous paragraph windows, verbatim.
Potency scoring = structural cues only (parables, questions, punch claims).
Selection/notes live in shorts/ledger.jsonl (human-curated).

  python3 tools/mine_shorts.py talks/immortality            # top candidates
  python3 tools/mine_shorts.py talks/immortality --all      # every window
  python3 tools/mine_shorts.py --list                       # all talks
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TALKS_DIR = os.path.join(ROOT, "output", "talks")
W_MIN, W_MAX = 150, 300          # 60–120 s @150 wpm (owner spec)
TOP = 8

PARABLE = re.compile(
    r"\b(there was|once|a certain|two (men|persons|blind|friends)|four (blind|men)|"
    r"an elephant|the chameleon|a man (had|went|was)|a guru|a disciple came)\b", re.I)
PUNCH = re.compile(
    r"\b(you must|mark this|remember (this|that)|know that|verily|indeed|"
    r"the (soul|atman|self) is|god is|brahman is|all (religions|paths)|"
    r"who am i|the one thing necessary|there is nothing)\b", re.I)
RQ = re.compile(r"\?")


def paragraphs(path):
    text = open(path, encoding="utf-8").read()
    out = []
    for p in re.split(r"\n\s*\n", text):
        t = p.strip()
        if not t or t.startswith("#") or t.startswith("*"):
            continue
        out.append(t)
    return out


def windows(paras):
    w, i, j, cur = [], 0, 0, []
    # grow runs; emit every window in [W_MIN, W_MAX]
    n = len(paras)
    for start in range(n):
        words = 0
        for end in range(start, n):
            words += len(paras[end].split())
            if words > W_MAX:
                break
            if words >= W_MIN:
                w.append((start, end, list(paras[start:end + 1]), words))
    return w


def score(paras, words):
    body = " ".join(paras)
    s = 0
    notes = []
    if PARABLE.search(paras[0][:400]):
        s += 3; notes.append("parable-open")
    if RQ.search(paras[0][:300]):
        s += 2; notes.append("opens-question")
    if PUNCH.search(body):
        s += 2; notes.append("punch-claims")
    if body.rstrip().endswith((".!", "?", "”", '"')):
        s += 1
    # self-containment: no dangling setup (starts mid-argument?)
    if re.match(r"^(so|and|but|then|now|thus|therefore|having|after|we see, then)\b",
                paras[0].strip(), re.I):
        s -= 2; notes.append("CONTINUATION-START")
    # prefer tighter windows slightly (60-90s sweet spot)
    if 160 <= words <= 280:
        s += 1; notes.append("sweet-duration")
    return s, notes


def mine_volume(vol, top=15):
    """Top scored windows across a whole volume, per chapter, talk-chapters skipped."""
    rngs = [r for r in json.load(open(os.path.join(ROOT, "tts", "talk_ranges.json")))
            if r["vol"] == vol]
    skip_heads = {r["heading"] for r in rngs}
    text = open(os.path.join(ROOT, "output", vol + ".md"), encoding="utf-8").read()
    cands = []
    for ch in re.split(r"(?m)^## ", text)[1:]:
        head, _, body = ch.partition("\n")
        head = head.strip()
        if head in skip_heads:
            continue                      # already mined as a Complete Talk
        paras = [t for t in re.split(r"\n\s*\n", body) if t.strip()]
        paras = [t.strip() for t in paras
                 if t.strip() and not t.strip().startswith("*")]
        if not paras:
            continue
        for start, end, ps, words in windows(paras):
            sc, notes = score(ps, words)
            if sc > 0:
                cands.append({"ch": head, "start": start, "end": end,
                              "words": words, "sec": round(words / 2.5),
                              "score": sc, "notes": notes,
                              "preview": ps[0][:100]})
    cands.sort(key=lambda c: (-c["score"], c["ch"], c["start"]))
    picked, spans = [], {}
    for c in cands:
        key = c["ch"]
        if any(not (c["end"] < a or c["start"] > b) for a, b in spans.get(key, [])):
            continue
        if sum(1 for x in picked if x["ch"] == key) >= 2:
            continue
        spans.setdefault(key, []).append((c["start"], c["end"]))
        picked.append(c)
        if len(picked) >= top:
            break
    picked.sort(key=lambda c: (c["ch"], c["start"]))
    print(f"{vol}: {len(cands)} scored windows (talk-chapters skipped) -> top {len(picked)}")
    for c in picked:
        print(f"  [{c['ch'][:44]:<44}] p{c['start']:02d}-{c['end']:02d} "
              f"{c['sec']:>3}s sc{c['score']} ({','.join(c['notes']) or '-'}) "
              f"{c['preview']}...")


def main():
    args = sys.argv[1:]
    if "--volume" in args:
        return mine_volume(args[args.index("--volume") + 1],
                           int(args[args.index("--top") + 1])
                           if "--top" in args else 15)
    if "--list" in args or not args:
        for f in sorted(os.listdir(TALKS_DIR)):
            print(f.replace(".md", ""))
        return
    slug = args[0]
    if slug.startswith("talks/"):
        slug = slug[6:]
    path = os.path.join(TALKS_DIR, slug + ".md")
    if not os.path.exists(path):
        sys.exit(f"no such talk: {slug}")
    paras = paragraphs(path)
    cands = []
    for start, end, ps, words in windows(paras):
        s, notes = score(ps, words)
        if s > 0:
            cands.append({"start": start, "end": end, "words": words,
                          "sec": round(words / 2.5), "score": s, "notes": notes,
                          "preview": ps[0][:110]})
    # overlap-suppress: keep best first
    cands.sort(key=lambda c: (-c["score"], c["start"]))
    picked, spans = [], []
    limit = 999 if "--all" in args else TOP
    for c in cands:
        if len(picked) >= limit:
            break
        if any(not (c["end"] < a or c["start"] > b) for a, b in spans):
            continue
        spans.append((c["start"], c["end"]))
        picked.append(c)
    picked.sort(key=lambda c: c["start"])
    print(f"{slug}: {len(paras)} paragraphs · {len(cands)} windows "
          f"· showing {len(picked)}")
    for c in picked:
        rng = f"p{c['start']:02d}-{c['end']:02d}"
        print(f"  [{rng}] {c['words']:>3}w {c['sec']:>3}s  score {c['score']} "
              f"({','.join(c['notes']) or '-'})  {c['preview']}...")


if __name__ == "__main__":
    main()
