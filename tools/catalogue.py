#!/usr/bin/env python3
"""Build a structured catalogue + metadata from the cached Complete Works HTML.

Pure derivation: hierarchy, genre, dates and places come from the site's own
contents tree and italic subtitle lines. Nothing is invented.
Outputs: catalogue.json, catalogue.csv, INDEX.md
"""
import csv
import json
import os
import re
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import extract

ROOT = extract.ROOT
OUT = extract.OUT

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}

GENRE_RULES = [
    ("epistle", "letter"), ("letter", "letter"),
    ("poem", "poem"), ("poetry", "poem"),
    ("conversation", "conversation"), ("interview", "conversation"),
    ("sayings", "saying"), ("proverb", "saying"),
    ("notes", "notes"), ("report", "report"),
    ("appendi", "appendix"),
    ("karma-yoga", "yoga-course"), ("raja-yoga", "yoga-course"),
    ("jnana-yoga", "yoga-course"), ("bhakti-yoga", "yoga-course"),
    ("para-bhakti", "yoga-course"),
    ("address", "address"), ("lecture", "lecture"), ("discourse", "lecture"),
    ("writing", "writing"),
]


def genre_for(part_chain, title):
    hay = " ".join(part_chain + [title]).lower()
    for needle, genre in GENRE_RULES:
        if needle in hay:
            return genre
    return "chapter"


ROMAN = re.compile(r"^[IVXLC]+$")


def letter_no(title):
    return title if ROMAN.match(title.strip()) else ""


def parse_date(text):
    if not text:
        return None, None
    t = text.lower()
    # 11th September, 1893  /  11 September 1893
    m = re.search(r"(\d{1,2})(?:st|nd|rd|th)?\s+([a-z]+)\.?,?\s+(\d{4})", t)
    if m and m.group(2) in MONTHS:
        d, mo, y = int(m.group(1)), MONTHS[m.group(2)], int(m.group(3))
        try:
            return f"{y:04d}-{mo:02d}-{d:02d}", y
        except ValueError:
            pass
    # September 19, 1893
    m = re.search(r"([a-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})", t)
    if m and m.group(1) in MONTHS:
        mo, d, y = MONTHS[m.group(1)], int(m.group(2)), int(m.group(3))
        try:
            return f"{y:04d}-{mo:02d}-{d:02d}", y
        except ValueError:
            pass
    m = re.search(r"\b(1[89]\d{2})\b", t)
    if m:
        return f"{m.group(1)}", int(m.group(1))
    return None, None


def clean_place(text):
    if not text:
        return ""
    t = re.sub(r"\s+", " ", text).strip()
    t = re.sub(r"\b\d{4}\b", "", t).strip(" ,;-")
    if not t or re.match(r"^(chapter|part|book|section)\b", t, re.I) or ROMAN.match(t):
        return ""
    if parse_date(t)[0]:
        return ""
    return t




def slugify(s):
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s.lower()).strip("-")
    return s[:60]


def walk(url, vol_prefix, seen, chain, out, is_root, vol_key, place=""):
    if url in seen:
        return
    seen.add(url)
    blocks, links = extract.parse(url)
    links = [(u, t) for (u, t) in links
             if extract.in_volume(u, vol_prefix) and u.lower().endswith((".htm", ".html"))]
    heads = [t for k, t in blocks if k in ("h2", "h3")]
    h4s = [t for k, t in blocks if k == "h4"]
    centers = [t for k, t in blocks if k == "center"]
    if links:
        if is_root:
            part = chain
        else:
            part = chain + [heads[0] if heads else (h4s[0] if h4s else url)]
            declared = clean_place(h4s[0]) if h4s else ""
            if declared:
                place = declared
        for u, _ in links:
            walk(u, vol_prefix, seen, part, out, False, vol_key, place)
    else:
        part = chain
        title = heads[0] if heads else ""
        subtitle = centers[0] if centers else (h4s[0] if h4s else "")
        body_words = sum(len(t.split()) for k, t in blocks if k not in ("h2", "h3", "h4", "center"))
        iso, year = parse_date(subtitle)
        out.append({
            "volume": vol_key,
            "part": part,
            "work_group": part[0] if part else "",
            "chapter": title,
            "subtitle": subtitle,
            "genre": genre_for(part, title),
            "letter_no": letter_no(title),
            "date_text": subtitle if iso else "",
            "date_iso": iso or "",
            "year": year or "",
            "place": place,
            "words": body_words,
            "url": url,
            "slug": slugify(title) or slugify(url.rsplit("/", 1)[-1]),
        })


def main():
    catalogue = []
    for key, rel, title in extract.VOLUMES:
        url = extract.BASE + rel if not rel.startswith("http") else rel
        import urllib.parse
        url = urllib.parse.urljoin(extract.BASE, rel)
        prefix = urllib.parse.urlparse(url).path.rsplit("/", 1)[0] + "/"
        rows = []
        try:
            walk(url, prefix, set(), [], rows, True, key)
        except Exception as e:
            print(f"[{key}] ERROR: {e}", file=sys.stderr)
            continue
        catalogue.extend(rows)
        print(f"[{key}] {len(rows)} chapters")

    os.makedirs(OUT, exist_ok=True)
    for r in catalogue:
        r["part_path"] = " / ".join(r["part"])

    with open(os.path.join(OUT, "catalogue.json"), "w", encoding="utf-8") as f:
        json.dump(catalogue, f, ensure_ascii=False, indent=2)

    cols = ["volume", "work_group", "part_path", "chapter", "genre", "letter_no",
            "date_iso", "year", "place", "words", "subtitle", "slug", "url"]
    with open(os.path.join(OUT, "catalogue.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in catalogue:
            w.writerow(r)

    write_index(catalogue)
    print(f"TOTAL {len(catalogue)} chapters -> catalogue.json / catalogue.csv / INDEX.md")


def write_index(cat):
    lines = ["# Complete Works of Swami Vivekananda — Catalogue", "",
             f"{len(cat)} chapters across {len(set(r['volume'] for r in cat))} volumes.", ""]
    vols = {}
    for r in cat:
        vols.setdefault(r["volume"], []).append(r)
    for vol, rows in vols.items():
        words = sum(r["words"] for r in rows)
        lines.append(f"## {vol}  ({len(rows)} chapters, {words:,} words)")
        lines.append("")
        for r in rows:
            meta = " · ".join(x for x in [r["genre"], r["date_iso"], r["place"],
                                          f"{r['words']:,}w"] if x)
            lines.append(f"- **{r['chapter'] or r['slug']}** — {meta}")
        lines.append("")
    with open(os.path.join(OUT, "INDEX.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
