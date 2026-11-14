#!/usr/bin/env python3
"""TTS batch monitor.

  python3 tools/tts_status.py               # console table
  python3 tools/tts_status.py --serve 8612  # live dashboard -> http://127.0.0.1:8612/
Regeneration: background thread every 60s (or on demand for --once/html).
"""
import json
import os
import re
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import batch_voices as bv  # noqa: E402

R2_DIR = "r2:longform-audio/vivek/"
CHARS_PER_S = 56.0   # measured 28 chars/s/worker x 2 workers


def slugs():
    talks = [f"talks/{r['slug']}" for r in
             json.load(open(os.path.join(ROOT, "tts", "talk_ranges.json")))]
    vols = (["introduction"] + [f"volume_{i}" for i in range(1, 10)]
            + ["unpublished", "appendices"])
    return talks + vols


def cached_set():
    r = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "vps",
                        "find /tmp/vivek-tts/gcache -name '*.mp3' -printf '%h/%f\\n' 2>/dev/null"],
                       capture_output=True, text=True, timeout=60)
    out = set()
    for line in r.stdout.splitlines():
        m = re.search(r"gcache/(.+)/g\d+_[a-z]+_([0-9a-f]{12})\.mp3$", line)
        if m:
            out.add((m.group(1), m.group(2)))
    return out


def r2_sizes():
    """{path: bytes} — rclone ls pads with SPACES here; 3 tries x 60s."""
    for attempt in range(3):
        r = subprocess.run(["timeout", "60", "rclone", "ls", R2_DIR],
                           capture_output=True, text=True)
        out = {}
        for l in r.stdout.splitlines():
            parts = l.split(None, 1)
            if len(parts) == 2 and parts[1].endswith(".mp3"):
                out[parts[1]] = int(parts[0])
        if out:
            return out
    return {}


def collect():
    cached, r2 = cached_set(), r2_sizes()
    rng = json.load(open(os.path.join(ROOT, "tts", "talk_ranges.json")))
    rows, t_rem, t_done, t_all = [], 0, 0, 0
    for slug in slugs():
        src = (os.path.join(ROOT, "output", "talks", slug.split("/", 1)[1] + ".md")
               if slug.startswith("talks/") else
               os.path.join(ROOT, "output", slug + ".md"))
        exclude = None
        if re.fullmatch(r"volume_\d+", slug):
            exclude = [(r["start"], r["end"]) for r in rng if r["vol"] == slug]
        try:
            groups = bv.build_groups(src, exclude)
        except Exception as e:
            rows.append({"slug": slug, "error": str(e)})
            continue
        done = [g for g in groups if (slug, g["sha"]) in cached]
        rem = sum(g["chars"] for g in groups if (slug, g["sha"]) not in cached)
        rows.append({"slug": slug, "groups": len(groups), "done": len(done),
                     "rem": rem, "pct": (100 * len(done) // len(groups)) if groups else 100,
                     "r2": r2.get(slug + ".mp3")})
        t_all += len(groups); t_done += len(done); t_rem += rem
    eta = t_rem / CHARS_PER_S / 3600
    return rows, {"groups": t_all, "done": t_done, "rem_chars": t_rem, "eta_h": eta}


def print_table(rows, tot):
    print(f"{'slug':<28} {'groups':>6} {'done':>6} {'%':>4} {'rem_chars':>9} {'R2':>14}")
    print("-" * 74)
    for r in rows:
        if "error" in r:
            print(f"{r['slug']:<28} ERROR {r['error']}")
            continue
        r2 = f"YES {r['r2']//1048576}MB" if r["r2"] else "—"
        print(f"{r['slug']:<28} {r['groups']:>6} {r['done']:>6} {r['pct']:>4}% "
              f"{r['rem']:>9,} {r2:>14}")
    print("-" * 74)
    print(f"overall {tot['done']}/{tot['groups']} groups · "
          f"{tot['rem_chars']:,} chars left · ETA ≈ {tot['eta_h']:.1f} h")


def html_page(rows, tot):
    def bar(p):
        color = "#3fb950" if p == 100 else "#58a6ff"
        return (f'<div class="bar"><div style="width:{p}%;background:{color}"></div></div>')
    tr = []
    for r in rows:
        if "error" in r:
            tr.append(f"<tr><td>{r['slug']}</td><td colspan=5 class=err>{r['error']}</td></tr>")
            continue
        r2 = f'{r["r2"]//1048576} MB ✓' if r["r2"] else "—"
        tr.append(f'<tr><td class=s>{r["slug"]}</td><td>{r["groups"]}</td>'
                  f'<td>{r["done"]}</td><td>{bar(r["pct"])}{r["pct"]}%</td>'
                  f'<td>{r["rem"]:,}</td><td>{r2}</td></tr>')
    tp = 100 * tot["done"] // tot["groups"] if tot["groups"] else 0
    return f"""<!doctype html><meta charset=utf-8>
<meta http-equiv=refresh content=60>
<title>Vivekananda TTS batch</title>
<style>body{{background:#0d1117;color:#c9d1d9;font:14px/1.5 ui-monospace,monospace;
padding:24px;max-width:1100px;margin:auto}} h1{{font-size:18px;color:#f0f6fc}}
table{{border-collapse:collapse;width:100%}} td,th{{padding:4px 8px;text-align:left;
border-bottom:1px solid #21262d}} th{{color:#8b949e}} .s{{font-family:ui-monospace}}
.bar{{display:inline-block;width:120px;height:10px;background:#161b22;
border-radius:5px;overflow:hidden;vertical-align:middle;margin-right:6px}}
.bar div{{height:100%}} a{{color:#58a6ff}} .err{{color:#f85149}}
.sum{{margin:14px 0;color:#8b949e}} .big{{color:#f0f6fc;font-size:16px}}</style>
<h1>Vivekananda → R2 TTS batch <span style="color:#8b949e">· auto-refresh 60s ·
 {time.strftime('%H:%M:%S')}</span></h1>
<div class=big>{tot['done']} / {tot['groups']} groups ({tp}%) ·
 {tot['rem_chars']:,} chars left · ETA ≈ {tot['eta_h']:.1f} h</div>
<table><tr><th>slug</th><th>groups</th><th>done</th><th>progress</th>
<th>rem chars</th><th>R2</th></tr>{''.join(tr)}</table>
<div class=sum>cache on vps (resume-safe) · per-slug notify-send ·
 log: /tmp/opencode/vivek_batch_all.log · 2 fish workers · s2.1-pro-free</div>"""


def write(path, rows, tot):
    with open(path, "w", encoding="utf-8") as f:
        f.write(html_page(rows, tot))


def serve(port, path):
    def loop():
        while True:
            try:
                rows, tot = collect()
                write(path, rows, tot)
                print(f"[{time.strftime('%H:%M:%S')}] refreshed "
                      f"{tot['done']}/{tot['groups']}", flush=True)
            except Exception as e:
                print("refresh failed:", e, flush=True)
            time.sleep(60)
    threading.Thread(target=loop, daemon=True).start()

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path not in ("/", "/tts_status.html"):
                self.send_error(404); return
            data = open(path, "rb").read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        def log_message(self, *a):
            pass
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()


def main():
    args = sys.argv[1:]
    outdir = os.path.join(ROOT, "output")
    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, "tts_status.html")
    if "--serve" in args:
        port = int(args[args.index("--serve") + 1]) if "--serve" in args and \
            args.index("--serve") + 1 < len(args) else 8612
        rows, tot = collect()
        write(path, rows, tot)
        print(f"dashboard http://127.0.0.1:{port}/", flush=True)
        serve(port, path)
    else:
        rows, tot = collect()
        if "--html" in args:
            write(path, rows, tot)
            print("wrote", path)
        print_table(rows, tot)


if __name__ == "__main__":
    main()
