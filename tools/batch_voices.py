#!/usr/bin/env python3
"""Vivekananda/Gospel batch VOICER — videofactory fish scripting, ported.

Casting (owner rule 2026-11-14):
  old man 394578d869ee4f99aa6fa500ba664528  = the Master (Vivekananda / Ramakrishna)
  granny  614f8afd83f841048c040b2c6234d2c1  = host: titles, attributions, dates,
                                              questioner (Q:), narration (M. said…)

Direction law (ported from videofactory docs/law/FISH-DIRECTION.md):
  * tags prefix, bodies NEVER rewritten; audit: stripped(directed)==canonical
  * [long-break] on headings/titles · [break] on colon-enders, beats, dialogue
    turns, and after any block lacking terminal punctuation
  * free model pinned: fish-audio/s2.1-pro-free
  * cache = sha1(voice|directed) — resume-safe, idempotent

Pipeline (Rule 8 — hub runs zero ffmpeg): groups ship to vps; fish + concat +
house norm (-21 dB / -1.5 dB) + mp3 all run there; push straight to R2.

Usage:
  python3 tools/batch_voices.py --slug volume_1        # one volume
  python3 tools/batch_voices.py --slug volume_1 --dry-run
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OLDMAN = "394578d869ee4f99aa6fa500ba664528"
GRANNY = "614f8afd83f841048c040b2c6234d2c1"
MODEL = "fish-audio/s2.1-pro-free"
R2_DIR = "r2:longform-audio/vivek/"
SSH = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "vps"]
GROUP_MAX = 1600
BEATS = {"indeed", "yes", "no", "now", "therefore", "again", "why", "what",
         "listen", "remember", "mark", "understand"}
TAG_RE = re.compile(r"\[(?:break|long-break)\]")
INDIC_RE = re.compile("[\u0900-\u097F\u0980-\u09FF\u0A00-\u0BFF\u0C00-\u0D7F]")  # Deva/Bengali/Tamil/Telugu/Kannada/Malayalam — fish cannot read these   # ONLY our tags; body brackets (refs) stay
TERMINAL = tuple(".!?:;…—”\"'")

# ---------------------------------------------------------------- direction
def canonical(md_text):
    """markdown -> spoken canon (markup dropped, content unchanged)."""
    out = []
    for p in re.split(r"\n\s*\n", md_text):
        t = p.strip()
        if not t:
            continue
        t = t.replace("*", "").replace("`", "")
        t = re.sub(r"(?m)^#+\s*", "", t)
        t = re.sub(r"[ \t]+", " ", t).strip()
        if t:
            out.append(t)
    return out


def voice_of(t, head):
    # headings + italic one-liners (attribution/date) = host; else Master
    if head:
        return "granny"
    return "oldman"


def is_beat(t):
    s = t.strip().lower().rstrip(".!?:;…")
    return s in BEATS or t.strip().endswith(":")


def parse_blocks(path):
    """markdown -> canonical spoken blocks [{head, host, text}].
    host = title OR italic one-liner (attribution/date) -> granny."""
    raw = open(path, encoding="utf-8").read()
    blocks = []
    for p in re.split(r"\n\s*\n", raw):
        t = p.strip()
        if not t:
            continue
        head = bool(re.match(r"^#+\s", t))
        ital = bool(t.startswith("*") and t.endswith("*") and len(t) > 2)
        canon = canonical(p)
        if canon:
            blocks.append({"head": head, "host": head or ital, "text": canon[0],
                           "indic": bool(INDIC_RE.search(canon[0]))})
    return blocks


def build_groups(path, exclude=None, stats=None):
    """canonical blocks -> directed groups [{voice, text, bid...}] + audit.
    Indic-script blocks are SKIPPED (fish cannot read them) and counted."""
    blocks = parse_blocks(path)
    if exclude:
        blocks = [b for i, b in enumerate(blocks)
                  if not any(s <= i < e for s, e in exclude)]
    indic = [b for b in blocks if b.get("indic")]
    if stats is not None:
        stats["indic_blocks"] = len(indic)
        stats["indic_words"] = sum(len(b["text"].split()) for b in indic)
    blocks = [b for b in blocks if not b.get("indic")]

    directed, prev_term = [], True
    for i, b in enumerate(blocks):
        d = b["text"]
        if b["head"]:
            d = "[long-break] " + d
        elif not prev_term or is_beat(d):
            d = "[break] " + d
        directed.append(d)
        prev_term = d.rstrip().endswith(TERMINAL)

    # audit invariant: tags are prefixes, bodies byte-equal
    for b, d in zip(blocks, directed):
        stripped = TAG_RE.sub("", d).strip()
        assert stripped == b["text"], f"direction rewrote body: {d[:80]!r}"

    # groups: consecutive same voice, <= GROUP_MAX
    groups, cur, cur_v, size, cur_ids = [], [], None, 0, []
    def flush():
        nonlocal cur, size, cur_ids
        if cur:
            groups.append({"voice": cur_v, "text": " ".join(cur), "blocks": list(cur_ids)})
        cur, size, cur_ids = [], 0, []
    for bi, (b, d) in enumerate(zip(blocks, directed)):
        v = "granny" if b.get("host") else "oldman"
        if cur and (v != cur_v or size + len(d) > GROUP_MAX):
            flush()
        cur_v = v
        cur.append(d)
        cur_ids.append(bi)
        size += len(d) + 1
    flush()
    for i, g in enumerate(groups):
        g["gid"] = i
        g["voice_id"] = GRANNY if g["voice"] == "granny" else OLDMAN
        g["sha"] = hashlib.sha1(f'{g["voice_id"]}|{g["text"]}'.encode()).hexdigest()[:12]
        g["chars"] = len(g["text"])
    return groups

# ---------------------------------------------------------------- remote
REMOTE = r'''
import json, os, re, subprocess, sys, time, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor
slug = sys.argv[1]
D = "/tmp/vivek-tts"
_sub = os.path.dirname(slug)
if _sub:
    os.makedirs(f"{D}/{_sub}", exist_ok=True)
G = json.load(open(f"{D}/groups/{slug}.json"))
CACHE = f"{D}/gcache/{slug}"
os.makedirs(CACHE, exist_ok=True)
log = lambda m: print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)

key = None
for p in [os.path.expanduser("~/.config/opencode/.env"), "/home/ubuntu/.config/opencode/.env"]:
    try:
        for line in open(p):
            if line.startswith("FISH_API_KEY="):
                key = line.split("=", 1)[1].strip(); break
    except OSError: pass
    if key: break
assert key, "no FISH_API_KEY on remote"

def fish(voice, text):
    body = json.dumps({"model": "fish-audio/s2.1-pro-free", "input": text,
                       "voice": voice, "response_format": "wav",
                       "speed": 1.0, "temperature": 0.7}).encode()
    req = urllib.request.Request("https://api.fish.audio/compat/v1/audio/speech",
        data=body, headers={"Authorization": "Bearer " + key,
                            "Content-Type": "application/json"})
    last = None
    for a in range(5):
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}: {e.read()[:150]}"
            if e.code in (429, 500, 502, 503):
                time.sleep(10 * (a + 1)); continue
            raise RuntimeError(last)
        except Exception as e:
            last = str(e); time.sleep(10 * (a + 1))
    raise RuntimeError(f"fish failed: {last}")

def render_group(g):
    fn = f"{CACHE}/g{g['gid']:03d}_{g['voice']}_{g['sha']}.mp3"
    if os.path.exists(fn) and os.path.getsize(fn) > 1000:
        return fn, "cached"
    t0 = time.time()
    raw = fish(g["voice_id"], g["text"])
    wav = f"/tmp/fishg_{g['sha']}.wav"
    open(wav, "wb").write(raw)
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", wav,
                        "-ar", "44100", "-ac", "1", "-b:a", "192k", fn],
                       capture_output=True, text=True)
    os.unlink(wav)   # own temp; hub Rule 8 = all encode on this box anyway
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-200:])
    return fn, f"rendered {time.time()-t0:.0f}s"

done, failed, t_start = 0, [], time.time()
def work(g):
    global done
    try:
        fn, how = render_group(g)
        done += 1
        log(f"  [{done}/{len(G)}] g{g['gid']:03d} {g['voice']} {how}")
        return fn
    except Exception as e:
        failed.append({"gid": g["gid"], "err": str(e)})
        log(f"  FAIL g{g['gid']:03d}: {e}")
        return None

with ThreadPoolExecutor(max_workers=4) as ex:
    fns = list(ex.map(work, G))
if failed:
    print("GROUP_FAILURES " + json.dumps(failed), flush=True)
    sys.exit(2)

# concat in order + house norm + final mp3
lst = f"{D}/{slug}_list.txt"
open(lst, "w").write("".join(f"file '{f}'\n" for f in fns))
merged = f"{D}/{slug}_merged.mp3"
r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0",
                    "-i", lst, "-c", "copy", merged], capture_output=True, text=True)
assert r.returncode == 0, r.stderr[-300:]

def mean_db(path):
    r = subprocess.run(["ffmpeg", "-nostats", "-v", "info", "-i", path,
                        "-af", "volumedetect", "-f", "null", "-"],
                       capture_output=True, text=True)
    m = re.search(r"mean_volume: (-?[\d.]+) dB", r.stderr)
    return float(m.group(1)) if m else None

before = mean_db(merged)
gain = max(-12.0, min(12.0, -21.0 - before)) if before is not None else 0.0
final = f"{D}/{slug}.mp3"
r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", merged,
                    "-af", f"volume={gain:+.2f}dB,alimiter=limit=0.84",
                    "-ar", "44100", "-ac", "1", "-b:a", "128k", final],
                   capture_output=True, text=True)
assert r.returncode == 0, r.stderr[-300:]
dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                      "-of", "default=nw=1:nk=1", final],
                     capture_output=True, text=True).stdout.strip()

dst = "r2:longform-audio/vivek/" + slug + ".mp3"
p = subprocess.run(["rclone", "copyto", final, dst], capture_output=True, text=True)
push = "ok" if p.returncode == 0 else "FAIL: " + p.stderr[-300:]
stats = {"slug": slug, "groups": len(G), "wall_min": round((time.time()-t_start)/60, 1),
         "duration_s": round(float(dur or 0)), "size_kb": os.path.getsize(final)//1024,
         "mean_before": before, "gain_db": round(gain, 2), "push": push}
open(f"{D}/{slug}.stats.json", "w").write(json.dumps(stats, indent=2))
print("STATS " + json.dumps(stats), flush=True)
sys.exit(0 if push == "ok" else 3)
'''

# ---------------------------------------------------------------- local
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", required=True)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    slug = a.slug
    if slug.startswith("talks/"):
        src = os.path.join(ROOT, "output", "talks", slug.split("/", 1)[1] + ".md")
    elif slug.startswith("topics/"):
        src = os.path.join(ROOT, "output", "topics", slug.split("/", 1)[1] + ".md")
    else:
        src = os.path.join(ROOT, "output", slug + ".md")
    exclude = None
    rng_path = os.path.join(ROOT, "tts", "talk_ranges.json")
    if re.fullmatch(r"volume_\d+", slug) and os.path.exists(rng_path):
        exclude = [(r["start"], r["end"]) for r in json.load(open(rng_path))
                   if r["vol"] == slug]
    gstats = {}
    groups = build_groups(src, exclude, gstats)
    if gstats.get("indic_blocks"):
        with open(os.path.join(ROOT, "tts", "skipped_indic.jsonl"), "a") as _f:
            _f.write(json.dumps({"slug": slug, **gstats}) + "\n")
        print(f"  language guard: skipped {gstats['indic_blocks']} Indic blocks "
              f"({gstats['indic_words']} words) — fish cannot read them")
    n_gr = sum(1 for g in groups if g["voice"] == "granny")
    chars = sum(g["chars"] for g in groups)
    print(f"{slug}: {len(groups)} groups ({n_gr} granny host / {len(groups)-n_gr} master), "
          f"{chars:,} directed chars (~{chars/1600:.0f} fish calls est.)"
          + (f" [talks excluded: {len(exclude)}]" if exclude else ""))
    if a.dry_run:
        for g in groups[:6]:
            print(f"  [{g['voice']}] {g['text'][:70]}")
        return
    gj = json.dumps(groups, ensure_ascii=False)
    gdir = "/tmp/vivek-tts/groups"
    rel = os.path.dirname(slug)
    subprocess.run(SSH + ["mkdir", "-p", gdir + ("/" + rel if rel else "")], check=True)
    # ship groups via ssh stdin (scp sftp-mode can't read stdin)
    ship = subprocess.run(SSH + [f"cat > {gdir}/{slug}.json"],
                          input=gj, text=True, capture_output=True)
    if ship.returncode != 0:
        sys.exit(f"ship failed: {ship.stderr[-300:]}")
    r = subprocess.run(SSH + ["python3", "-", slug], input=REMOTE, text=True)
    if r.returncode != 0:
        print(f"REMOTE FAILED exit={r.returncode}", file=sys.stderr)
        sys.exit(r.returncode)
    v = subprocess.run(["timeout", "30", "rclone", "ls", R2_DIR + slug + ".mp3"],
                       capture_output=True, text=True)
    print("R2 VERIFY:", v.stdout.strip() or v.stderr.strip())
    if not v.stdout.strip():
        sys.exit("object not found in R2")


if __name__ == "__main__":
    main()
