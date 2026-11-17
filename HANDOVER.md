# HANDOVER — Vivekananda / Indian corpus audio & video

Updated: 2026-11-17 · Repos: `prx0r/vivek` (this), `prx0r/ramakrishna`

## TL;DR state

| deliverable | where | state |
|---|---|---|
| Corpus extraction (1.21M words, 896-chapter catalogue) | repo `output/` | ✅ |
| 13 **Complete Talks** — audio | `r2:longform-audio/vivek/talks/*.mp3` | ✅ 6 h 37 m |
| 13 Complete Talks — **video (black)** | `…/talks/*.mp4` | ✅ 13/13 |
| 10 **topic compilations** (~0.6–1 h each) — audio | `…/topics/*.mp3` | ✅ ~8 h |
| 10 topics — **video (black)** | `…/topics/*.mp4` | ✅ 10/10 |
| **devotion / devotionactual** — video (WHITE, loudnorm −16 LUFS) | `…/devotion.mp4`, `…/devotionactual.mp4` | ✅ |
| **101 shorts** (60–120 s) — audio | `…/shorts/S*.mp3` | ✅ (S034 cut) |
| voice-QA samples | `…/samples/` | ✅ |
| Ramakrishna **Complete Sessions** (text) | `prx0r/ramakrishna/output/question-led/` | ✅ 77,468 w |

**R2 bucket `longform-audio` path `vivek/` is the master storage** (141 files ≈ 1.4 GB,
plus the 25 mp4s). Nothing else is authoritative.

## Infrastructure truth (learned the hard way)

- **hub → R2 ≈ 13 KB/s** — never stream media through the hub.
- **opencode3 = `ssh vps` (51.222.81.2)** is the encode box (per HANDOVER). Its disk is
  **tight (≈2.4 GB free, owned by the owner's work)** → jobs must be **zero-disk
  streaming**: `rclone cat … | ffmpeg … pipe:1 | rclone rcat …`. No staging, ever.
  (debz/hetzner is NOT to be used for this work.)
- Encode time reference: 8-min talk → mp4 in ~15 s on the fleet box (h264 stillimage).
- vps↔R2 is fast (≈13 MB/s push); hub↔R2 is the bottleneck.
- `/tmp` group cache on the vps (`/tmp/vivek-tts/gcache`) still holds rendered group
  mp3s; it powers fish-free short slicing.

## Tooling map (`tools/`)

| tool | purpose |
|---|---|
| `extract.py` / `catalogue.py` | corpus extraction + 896-chapter metadata |
| `build_talks.py` | 13 Complete Talks + `tts/talk_ranges.json` (volumes exclude them) |
| `batch_voices.py` | **fish pipeline**: direction tags (FISH-DIRECTION law), casting, group cache, house norm, R2 push. Sources: `references/…`
| `build_topics.py` | 10 thematic compilations (argmax assignment, dedupe, 9k-word target) |
| `mine_shorts.py` | paragraph-window mining (150–300 w), volume mode |
| `shorts_reuse.py` | maps shorts → cached group audio (fish-free slicing) |
| `slice_shorts.py` | executes the free slices (zero fish) |
| `render_shorts.py` | voices shorts (`--render`; safe by default) |
| `render_tts.py` | single-text TTS (samples, one-offs) |
| `tts_status.py` | console status + `--serve 8612` dashboard |
| `build_volume_index.py` | volume index (volumes are **paused**, see below) |

## Rulings (owner-approved, do not relitigate)

1. **Casting:** old man voice `394578d869ee4f99aa6fa500ba664528` = the Master;
   granny `614f8afd83f841048c040b2c6234d2c1` = host (titles, attributions, questioners).
2. **Model:** `fish-audio/s2.1-pro-free` only. Direction law from videofactory
   (prefix-only tags, stripped==original audit). House norm −21 dB mean / −1.5 dB peak.
3. **Language guard:** fish cannot read Devanagari/Bengali → Indic blocks are
   **never voiced** (4,452 blocks / 219,792 words skipped; `LANGUAGE-POLICY.md`).
   Sample proof: `samples/devanagari.mp3` vs `samples/sanskrit-romanised.mp3`.
4. **Product shape:** Complete Talks + 10 **topics** + shorts. **Full-volume audiobooks
   were a mistake and are permanently halted** (see `PROCESS-NOTES.md` #10). Rendered
   volume groups stay in the vps cache, unused.
5. **No overlap:** topics exclude the 13 talks; each paragraph belongs to ≤1 topic;
   shorts are unique spans; citations live in `.sources.md` sidecars (never spoken).
6. **Shorts:** 60–120 s, standalone, extract-only, tiered **S26 / A50 / B21 / C5**
   (`shorts/TIERS.md`). All rendered except the C cuts (S034 etc.).
7. **Video style:** topics/talks = black 1280×720 h264 crf28 + AAC 128k.
   devotion pair = **white** background + `loudnorm I=-16 TP=-1.5`.
8. **Global rule 9:** no deletions without written owner approval.

## Runbook

```bash
cd ~/Documents/patala/vivekananda-complete-works
python3 tools/tts_status.py                       # console status
python3 tools/tts_status.py --serve 8612          # dashboard
python3 tools/batch_voices.py --slug topics/<t> --dry-run
python3 tools/batch_voices.py --slug topics/<t>   # render audio -> R2

# zero-disk video encode (run ON opencode3; never stage):
ssh vps 'rclone cat r2:longform-audio/vivek/talks/X.mp3 \
 | ffmpeg -v error -f lavfi -i color=c=black:s=1280x720:r=1 -i pipe:0 \
     -c:v libx264 -preset veryfast -tune stillimage -pix_fmt yuv420p -crf 28 \
     -c:a aac -b:a 128k -shortest -movflags frag_keyframe+empty_moov -f mp4 pipe:1 \
 | rclone rcat r2:longform-audio/vivek/talks/X.mp4'
```

## Open items (waiting on owner)

1. **vps `/tmp` cleanup** — my leftovers ≈2.4 GB (`/tmp/vivek-staging`,
   `/tmp/vivek-tts/*_merged.*`, duplicate shorts mp3s). All regenerable / already in R2;
   needs explicit approval to delete (rule 9).
2. **Shorts → mp4?** (101 files, streaming, ~25 min) — mp3-only today.
3. **Bundle for delivery** — per-set zips (talks/topics/shorts/docs, built as streams)
   vs manifest + direct links. Nothing zipped yet (a whole-bucket zip failed on disk).
4. **Ramakrishna audio** — Complete Sessions text is ready; audio not started.
   When it starts: same fish law, old man = Ramakrishna, granny = questioners.

## Cautions

- `/tmp` markers (`done_*`, `mp4_talk_*`) are **ephemeral** — jobs are resumable from R2
  state + caches, but don't rely on markers surviving a reboot.
- Killing a local job wrapper does **not** kill the remote ffmpeg loop (orphan lesson,
  `PROCESS-NOTES.md` #3). Always verify on the remote after a kill.
- Never run more than one render stream; per-turn checks only, never sleep-poll.
