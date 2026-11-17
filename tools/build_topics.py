#!/usr/bin/env python3
"""Build the 10 THEMATIC compilations (~1 h each) from the corpus.

Extract-only: whole paragraphs, ranked by theme lexicon, deduped, capped per
chapter, filled to ~9,000 words (≈1 h at 150 wpm). Each paragraph is assigned
to its single best theme (argmax) so nothing repeats across topics, and the 13
Complete Talks are excluded (already rendered standalone).

Writes output/topics/<theme>.md + topics.json + TOPICS-INDEX.md
"""
import json
import math
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import batch_voices as bv  # noqa: E402

TARGET_WORDS = 9000      # ≈ 1 h
MIN_PARA, MAX_PARA = 60, 420

THEMES = {
    "atman-the-self": ("The Self — Who You Really Are",
        "atman self soul ‘i am’ who am i consciousness witness innermost nature real being body not body deathless eternal within"),
    "maya-illusion": ("Māyā — The World as Appearance",
        "maya illusion maya unreal world appearance dream mirage ignorance delusion phenomenal nature veil"),
    "god-brahman": ("God, Brahman & the Absolute",
        "god brahman absolute infinite personal impersonal ishvara creator lord divine omnipresent one without a second"),
    "bhakti-love": ("Bhakti — The Path of Love",
        "bhakti love devotion lover beloved worship prayer surrender grace ecstasy longing heart god-love"),
    "karma-work": ("Karma-Yoga — Work & Duty",
        "karma work duty action worker duty nishkama attachment desire result motive service activity"),
    "raja-yoga-mind": ("Rāja-Yoga — Mind & Concentration",
        "raja yoga concentration meditation mind control prana breathing psychic power attention practice samadhi"),
    "death-immortality": ("Death, Immortality & What Survives",
        "death immortality die dying soul survives rebirth reincarnation after death beyond grave eternal life"),
    "character-strength": ("Character, Strength & Man-Making",
        "character strength courage fear weakness man power will virile brave hero coward weak strong"),
    "practical-vedanta": ("Practical Vedanta — Everyday Life",
        "practical vedanta daily life worldly householder business work world duties application living"),
    "unity-religions": ("One Religion, Many Paths",
        "religion religions unity tolerance sect universal all religions paths truth harmony creeds"),
}


def paragraphs_of_all():
    """Yield (volume, chapter, para_index, text) for all volumes minus talks."""
    rng = json.load(open(os.path.join(ROOT, "tts", "talk_ranges.json")))
    out = []
    for i in range(1, 10):
        slug = f"volume_{i}"
        excl = [(r["start"], r["end"]) for r in rng if r["vol"] == slug]
        blocks = bv.parse_blocks(os.path.join(ROOT, "output", slug + ".md"))
        blocks = [b for j, b in enumerate(blocks)
                  if not any(s <= j < e for s, e in excl) and not b.get("indic")]
        chapter = ""
        for b in blocks:
            if b["head"]:
                chapter = b["text"]
                continue
            out.append((slug, chapter, len(out), b["text"]))
    return out


def score(text, lexicon):
    low = " " + text.lower() + " "
    hits = 0
    for term in lexicon:
        n = low.count(" " + term + " ")
        hits += n * (2 if " " in term else 1)
    words = len(text.split())
    return hits * 1000 / max(words, 1)  # density


def main():
    lex = {k: v[1].split() for k, v in THEMES.items()}
    paras = paragraphs_of_all()
    print(f"corpus paragraphs (no talks, no Indic): {len(paras):,}")

    # score all paragraphs per theme, assign argmax
    assigned = {k: [] for k in THEMES}
    for slug, ch, idx, text in paras:
        w = len(text.split())
        if not (MIN_PARA <= w <= MAX_PARA):
            continue
        best, bs = None, 0.0
        for k, lx in lex.items():
            s = score(text, lx)
            if s > bs:
                best, bs = k, s
        if best and bs > 0:
            assigned[best].append((bs, slug, ch, idx, text, w))

    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        import numpy as np
        HAVE_SK = True
    except Exception:
        HAVE_SK = False

    manifest = []
    index = ["# Topic compilations (extract-only, ~1 h each)", ""]
    for k, (title, _) in THEMES.items():
        cand = sorted(assigned[k], key=lambda x: -x[0])
        picked, per_ch = [], {}
        vecs = []
        for bs, slug, ch, idx, text, w in cand:
            if sum(x[5] for x in picked) >= TARGET_WORDS:
                break
            if per_ch.get((slug, ch), 0) >= 5:
                continue
            if HAVE_SK and vecs:
                from sklearn.feature_extraction.text import TfidfVectorizer as TV
                v = TV().fit_transform([x[4] for x in picked] + [text])
                M = (v @ v.T).toarray()
                if max(M[-1][:-1]) >= 0.82:
                    continue
            per_ch[(slug, ch)] = per_ch.get((slug, ch), 0) + 1
            picked.append((bs, slug, ch, idx, text, w))
        # order by source for reading flow
        picked.sort(key=lambda x: (x[1], x[3]))
        total = sum(x[5] for x in picked)
        lines = [f"# {title}", ""]
        meta = (f"# {title}\n\nExtract-only compilation · {total:,} words ≈ "
                f"{total/9000:.1f} h · public domain\n\nSources:\n")
        cites = []
        for bs, slug, ch, idx, text, w in picked:
            lines.append(text)
            lines.append("")
            cites.append(f"`{slug}` · {ch[:60]}")
        # citations live in a sidecar so they are never spoken
        open(os.path.join(ROOT, "output", "topics", f"{k}.sources.md"), "w",
             encoding="utf-8").write(meta + "\n".join(cites) + "\n")
        os.makedirs(os.path.join(ROOT, "output", "topics"), exist_ok=True)
        with open(os.path.join(ROOT, "output", "topics", k + ".md"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        manifest.append({"theme": k, "title": title, "words": total,
                         "pieces": len(picked),
                         "sources": [{"volume": s, "chapter": c} for _, s, c, _, _, _ in picked]})
        index.append(f"- **{title}** — {total:,}w (~{total/9000:.1f}h), {len(picked)} pieces → `{k}.md`")
        print(f"  {k:<20} {len(picked):>3} pieces  {total:>6,}w  (~{total/9000:.1f}h)")
    with open(os.path.join(ROOT, "output", "topics", "topics.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=1)
    with open(os.path.join(ROOT, "TOPICS-INDEX.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(index) + "\n")
    print("wrote output/topics/*.md + TOPICS-INDEX.md")


if __name__ == "__main__":
    main()
