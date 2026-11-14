#!/usr/bin/env python3
"""Faithful text extraction of the Complete Works of Swami Vivekananda.

Source: https://www.ramakrishnavivekananda.info/vivekananda/
No writing/editing: headings, subtitles and paragraphs are preserved as-is.
One Markdown file per source volume. Raw HTML is cached for resume.
"""
import os
import re
import sys
import time
import urllib.request
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

BASE = "https://www.ramakrishnavivekananda.info/vivekananda/"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "cache")
OUT = os.path.join(ROOT, "output")

VOLUMES = [
    ("introduction", "introduction.htm", "Introduction"),
    ("volume_1", "volume_1/complete_works_v1_contents.htm", "Volume 1"),
    ("volume_2", "volume_2/volume_2_contents.htm", "Volume 2"),
    ("volume_3", "volume_3/volume_3_contents.htm", "Volume 3"),
    ("volume_4", "volume_4/volume_4_contents.htm", "Volume 4"),
    ("volume_5", "volume_5/volume_5_contents.htm", "Volume 5"),
    ("volume_6", "volume_6/volume_6_contents.htm", "Volume 6"),
    ("volume_7", "volume_7/volume_7_contents.htm", "Volume 7"),
    ("volume_8", "volume_8/volume_8_contents.htm", "Volume 8"),
    ("volume_9", "volume_9/volume_9_contents.htm", "Volume 9"),
    ("unpublished", "unpublished/unpublished_contents.htm", "Unpublished"),
    ("appendices", "appendices/appendices_contents.htm", "Appendices"),
]

SKIP_HOST_PATH = ("introduction.htm", "index.htm", "complete_works.htm", "main.css")


def cache_path(url):
    p = urlparse(url)
    rel = p.path.lstrip("/")
    return os.path.join(CACHE, rel)


def fetch(url):
    cp = cache_path(url)
    if os.path.exists(cp) and os.path.getsize(cp) > 0:
        with open(cp, "rb") as f:
            raw = f.read()
    else:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (extraction)"})
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
        os.makedirs(os.path.dirname(cp), exist_ok=True)
        with open(cp, "wb") as f:
            f.write(raw)
        time.sleep(0.2)
    # site declares iso-8859-1; fall back to latin-1 which never fails
    m = re.search(rb'charset=["\']?([\w-]+)', raw[:2000], re.I)
    enc = (m.group(1).decode("ascii", "ignore") if m else "latin-1") or "latin-1"
    try:
        return raw.decode(enc, "replace")
    except LookupError:
        return raw.decode("latin-1", "replace")


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks = []      # list of [kind, text]  kinds: h2, h4, center, p
        self.links = []       # [(href, text)] content links (nav excluded)
        self._in_nav = 0
        self._in_skip = 0
        self._link = None
        self._active_block = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = (a.get("class") or "").split()
        if tag in ("script", "style"):
            self._in_skip += 1
            return
        if self._in_skip:
            return
        if "nav" in cls:
            self._in_nav += 1
            return
        if tag == "a":
            if self._in_nav or "arrow" in cls:
                return
            if self._link is None:
                self._link = [a.get("href", ""), []]
            return
        if self._in_nav:
            return
        if tag in ("h2", "h3", "h4"):
            self._active_block = [tag, []]
            self.blocks.append(self._active_block)
            return
        if tag == "p":
            kind = "center" if "center" in cls else "p"
            self._active_block = [kind, []]
            self.blocks.append(self._active_block)
            return
        if tag == "br" and self._active_block is not None:
            self._active_block[1].append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._in_skip:
            self._in_skip -= 1
            return
        if self._in_skip:
            return
        if tag == "a":
            if self._in_nav:
                return
            if self._link is not None:
                self.links.append((self._link[0], "".join(self._link[1])))
                self._link = None
            return
        if self._in_nav:
            if tag in ("p", "div"):
                self._in_nav -= 1
            return
        if tag in ("h2", "h3", "h4", "p"):
            self._active_block = None

    def handle_data(self, data):
        if self._in_skip:
            return
        data = data.replace("\n", " ").replace("\t", " ")
        if self._link is not None:
            self._link[1].append(data)
            return
        if self._in_nav:
            return
        if self._active_block is not None:
            self._active_block[1].append(data)


def norm(text):
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n+", "\n", text)
    return text.strip()


def parse(url):
    ps = PageParser()
    ps.feed(fetch(url))
    ps.close()
    blocks = []
    for kind, parts in ps.blocks:
        t = norm("".join(parts))
        if t:
            blocks.append((kind, t))
    links = []
    for href, txt in ps.links:
        href = (href or "").strip()
        if not href or href.startswith("#") or href.lower().startswith(("mailto:", "javascript:")):
            continue
        links.append((urljoin(url, href), norm(txt)))
    return blocks, links


def in_volume(url, vol_prefix):
    return urlparse(url).path.startswith(vol_prefix)


def walk(url, vol_prefix, seen, sink, is_root=False):
    if url in seen:
        return
    seen.add(url)
    blocks, links = parse(url)
    links = [(u, t) for (u, t) in links if in_volume(u, vol_prefix) and u.lower().endswith((".htm", ".html"))]
    if links:
        for kind, t in blocks:
            if kind in ("h2", "h3", "h4"):
                if is_root and kind == "h2":
                    continue
                sink.append((kind, t))
        for u, _ in links:
            walk(u, vol_prefix, seen, sink)
    else:
        sink.extend(blocks)


def render_volume(title, sink):
    lines = [f"# Complete Works of Swami Vivekananda — {title}", ""]
    marks = {"h2": "## ", "h3": "### ", "h4": "#### "}
    for kind, t in sink:
        if kind in marks:
            lines.extend([f"{marks[kind]}{t}", ""])
        elif kind == "center":
            lines.extend([f"*{t}*", ""])
        else:
            lines.extend([t, ""])
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"
    return text


def main(only=None):
    os.makedirs(OUT, exist_ok=True)
    for key, rel, title in VOLUMES:
        if only and key not in only:
            continue
        url = urljoin(BASE, rel)
        vol_prefix = urlparse(url).path.rsplit("/", 1)[0] + "/"
        sink = []
        seen = set()
        try:
            walk(url, vol_prefix, seen, sink, is_root=True)
        except Exception as e:
            print(f"[{key}] ERROR: {e}", file=sys.stderr)
            continue
        text = render_volume(title, sink)
        fn = os.path.join(OUT, f"{key}.md")
        with open(fn, "w", encoding="utf-8") as f:
            f.write(text)
        words = len(text.split())
        print(f"[{key}] {len(seen)} pages, {words} words -> {fn}")


if __name__ == "__main__":
    only = set(sys.argv[1:]) or None
    main(only)
