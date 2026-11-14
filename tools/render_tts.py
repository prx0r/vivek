#!/usr/bin/env python3
"""Render a Vivekananda talk to TTS and push straight to R2.

Model: fish-audio/s2.1-pro-free (free API, pro model)
Voice: 394578d869ee4f99aa6fa500ba664528   (alt: granny 614f8afd83f841048c040b2c6234d2c1)

Rule 8: the HUB runs zero ffmpeg — the whole fish→concat→norm→encode pipeline
runs on vps, then pushes directly to R2 (vps→R2 is ~13MB/s; hub pull ~13KB/s).

Usage:
  python3 tools/render_tts.py tts/immortality.txt --slug immortality
  python3 tools/render_tts.py tts/foo.txt --slug foo --voice 614f8afd83f841048c040b2c6234d2c1
"""
import argparse
import os
import re
import subprocess
import sys

SSH = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "vps"]
VOICE = "394578d869ee4f99aa6fa500ba664528"
VOICE_ALT = "614f8afd83f841048c040b2c6234d2c1"  # granny
MODEL = "fish-audio/s2.1-pro-free"
R2_DIR = "r2:longform-audio/vivek/"
CHUNK = 1600  # max chars per fish call
TARGET_MEAN_DB = -21.0   # house norm (HANDOVER tts batch law)
PEAK_LIMIT = "0.84"      # -1.5 dBFS
GAIN_CLAMP = 12.0

REMOTE = r'''
import json, os, re, subprocess, sys, time, urllib.request, urllib.error
slug, voice = sys.argv[1], sys.argv[2]
D = "/tmp/vivek-tts"
CACHE = f"{D}/cache/{slug}"
os.makedirs(CACHE, exist_ok=True)
log = lambda m: (print(m, flush=True))

# key
key = None
for p in [os.path.expanduser("~/.config/opencode/.env"), "/home/ubuntu/.config/opencode/.env"]:
    try:
        for line in open(p):
            if line.startswith("FISH_API_KEY="):
                key = line.split("=", 1)[1].strip(); break
    except OSError:
        pass
    if key: break
assert key, "no FISH_API_KEY on remote"

# text: strip markdown emphasis, light clean
raw = open(f"{D}/{slug}.txt", encoding="utf-8").read()
raw = raw.replace("*", "").replace("`", "")
raw = re.sub(r"(?m)^#.*$", "", raw)
raw = re.sub(r"[ \t]+", " ", raw)

# chunk at sentence boundaries, <= CHUNK chars
sents = re.split(r"(?<=[.!?;:])\s+", raw)
chunks, cur = [], ""
for s in sents:
    if len(cur) + len(s) + 1 > 1600 and cur:
        chunks.append(cur.strip()); cur = s
    else:
        cur = (cur + " " + s).strip()
if cur.strip():
    chunks.append(cur.strip())
log(f"chunks: {len(chunks)}")

def sha12(t):
    import hashlib
    return hashlib.sha1(f"{voice}|{t}".encode()).hexdigest()[:12]

def fish(text):
    body = json.dumps({
        "model": "fish-audio/s2.1-pro-free",
        "input": text,
        "voice": voice,
        "response_format": "wav",
        "speed": 1.0,
        "temperature": 0.7,
    }).encode()
    req = urllib.request.Request(
        "https://api.fish.audio/compat/v1/audio/speech",
        data=body,
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    last = None
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}: {e.read()[:200]}"
            time.sleep(5 * (attempt + 1))
        except Exception as e:
            last = str(e); time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"fish failed: {last}")

def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        raise RuntimeError(f"{cmd}\n{r.stderr[-500:]}")
    return r

wavs = []
for i, ch in enumerate(chunks, 1):
    h = sha12(ch)
    wav = f"{CACHE}/{i:03d}_{h}.wav"
    wavs.append(wav)
    if os.path.exists(wav) and os.path.getsize(wav) > 1000:
        log(f"  [{i}/{len(chunks)}] cached")
        continue
    raw_wav = f"/tmp/fish_{h}.wav"
    open(raw_wav, "wb").write(fish(ch))
    run(["ffmpeg", "-v", "error", "-y", "-i", raw_wav, "-ar", "44100", "-ac", "1", wav])
    log(f"  [{i}/{len(chunks)}] done ({os.path.getsize(wav)//1024} KB)")

# concat (identical format after resample)
lst = f"{D}/{slug}_list.txt"
open(lst, "w").write("".join(f"file '{w}'\n" for w in wavs))
merged = f"{D}/{slug}_merged.wav"
run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", merged])

def mean_db(path):
    r = subprocess.run(["ffmpeg", "-nostats", "-v", "info", "-i", path,
                        "-af", "volumedetect", "-f", "null", "-"],
                       capture_output=True, text=True)
    m = re.search(r"mean_volume: (-?[\d.]+) dB", r.stderr)
    return float(m.group(1)) if m else None

before = mean_db(merged)
gain = max(-12.0, min(12.0, -21.0 - before)) if before is not None else 0.0
normed = f"{D}/{slug}_norm.wav"
run(["ffmpeg", "-v", "error", "-y", "-i", merged,
     "-af", f"volume={gain:+.2f}dB,alimiter=limit=0.84",
     "-ar", "44100", "-ac", "1", normed])
after = mean_db(normed)

mp3 = f"{D}/{slug}.mp3"
run(["ffmpeg", "-v", "error", "-y", "-i", normed, "-ar", "44100", "-ac", "1",
     "-b:a", "128k", mp3])
dur = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
           "-of", "default=noprint_wrappers=1:nokey=1", mp3]).stdout.strip()
size = os.path.getsize(mp3)

dst = "r2:longform-audio/vivek/" + slug + ".mp3"
p = subprocess.run(["rclone", "copyto", mp3, dst], capture_output=True, text=True)
push = "ok" if p.returncode == 0 else "FAIL: " + p.stderr[-300:]

stats = {"slug": slug, "voice": voice, "model": "fish-audio/s2.1-pro-free",
         "chunks": len(chunks), "duration_s": float(dur or 0),
         "size_kb": size // 1024, "mean_db_before": before,
         "mean_db_after": after, "gain_db": round(gain, 2), "r2_push": push}
open(f"{D}/{slug}.stats.json", "w").write(json.dumps(stats, indent=2))
print("STATS " + json.dumps(stats), flush=True)
sys.exit(0 if push == "ok" else 1)
'''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("text")
    ap.add_argument("--slug", required=True)
    ap.add_argument("--voice", default=VOICE)
    a = ap.parse_args()

    # ship text to vps
    rdir = os.path.dirname(a.slug)
    subprocess.run(SSH + ["mkdir", "-p", "/tmp/vivek-tts" + ("/" + rdir if rdir else "")], check=True)
    subprocess.run(["scp", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
                    a.text, f"vps:/tmp/vivek-tts/{a.slug}.txt"], check=True)
    print(f"shipped {a.text} -> vps:/tmp/vivek-tts/{a.slug}.txt")

    r = subprocess.run(SSH + ["python3", "-", a.slug, a.voice],
                       input=REMOTE, text=True)
    if r.returncode != 0:
        print("REMOTE FAILED", file=sys.stderr)
        sys.exit(r.returncode)

    # verify from hub: object exists in R2
    v = subprocess.run(["timeout", "30", "rclone", "ls", R2_DIR + a.slug + ".mp3"],
                       capture_output=True, text=True)
    print("R2 VERIFY:", v.stdout.strip() or v.stderr.strip())
    if not v.stdout.strip():
        sys.exit("object not found in R2")


if __name__ == "__main__":
    main()
