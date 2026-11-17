#!/usr/bin/env python3
"""Slice exact shorts from cached group mp3s — ZERO fish calls.

Ships the plan (29 entries: id + cached group file paths) to vps; vps concats,
house-norms and pushes each to r2:longform-audio/vivek/shorts/<id>.mp3.
Writes /tmp/opencode/done_short_<id> on success.
"""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLAN = "/tmp/opencode/shorts_slice_plan.json"

REMOTE = r'''
import json, os, re, subprocess, sys
plan = json.load(open("/tmp/vivek-tts/shorts_slice_plan.json"))
ok, fail = [], []
for e in plan:
    sid = e["id"]
    mark = f"/tmp/opencode/done_short_{sid}"
    if os.path.exists(mark):
        ok.append(sid); continue
    files = [f for f in e["files"] if os.path.exists(f)]
    if len(files) != len(e["files"]):
        fail.append((sid, "missing group files")); continue
    lst = f"/tmp/vivek-tts/slice_{sid}_list.txt"
    open(lst, "w").write("".join(f"file '{f}'\n" for f in files))
    merged = f"/tmp/vivek-tts/slice_{sid}_merged.mp3"
    r = subprocess.run(["ffmpeg","-v","error","-y","-f","concat","-safe","0",
                        "-i",lst,"-c","copy",merged], capture_output=True, text=True)
    if r.returncode != 0:
        fail.append((sid, r.stderr[-200:])); continue
    d = subprocess.run(["ffmpeg","-nostats","-v","info","-i",merged,"-af",
                        "volumedetect","-f","null","-"], capture_output=True, text=True).stderr
    m = re.search(r"mean_volume: (-?[\d.]+) dB", d)
    mean = float(m.group(1)) if m else -21.0
    gain = max(-12.0, min(12.0, -21.0 - mean))
    out = f"/tmp/vivek-tts/{sid}.mp3"
    r = subprocess.run(["ffmpeg","-v","error","-y","-i",merged,
                        "-af", f"volume={gain:+.2f}dB,alimiter=limit=0.84",
                        "-ar","44100","-ac","1","-b:a","128k", out],
                       capture_output=True, text=True)
    if r.returncode != 0:
        fail.append((sid, r.stderr[-200:])); continue
    p = subprocess.run(["rclone","copyto", out, f"r2:longform-audio/vivek/shorts/{sid}.mp3"],
                       capture_output=True, text=True)
    if p.returncode == 0:
        open(mark, "w").write("sliced")
        ok.append(sid)
        print(f"SLICED {sid} ({len(files)} groups)", flush=True)
    else:
        fail.append((sid, p.stderr[-200:]))
print(f"RESULT ok={len(ok)} fail={len(fail)}")
for f in fail: print("FAIL", f)
sys.exit(1 if fail else 0)
'''

def main():
    plan = json.load(open(PLAN))
    # skip already-done shorts
    plan = [e for e in plan if not os.path.exists(f"/tmp/opencode/done_short_{e['id']}")]
    print(f"slicing {len(plan)} shorts (fish-free)")
    if not plan:
        return
    subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "vps",
                    "mkdir -p /tmp/vivek-tts"], check=True)
    ship = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "vps",
                           "cat > /tmp/vivek-tts/shorts_slice_plan.json"],
                          input=json.dumps(plan), text=True, capture_output=True)
    if ship.returncode != 0:
        sys.exit(f"ship failed: {ship.stderr[-200:]}")
    r = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "vps",
                        "python3 -"], input=REMOTE, text=True)
    sys.exit(r.returncode)


if __name__ == "__main__":
    main()
