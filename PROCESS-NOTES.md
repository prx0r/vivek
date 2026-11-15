# PROCESS NOTES — extraction → audio pipeline

Append-only engineering log for the Vivekananda corpus work. Covers decisions,
runbook, and every mistake made (so nobody re-makes them).

## 1. What this repo is

- `output/volume_1..9.md`, `introduction.md`, `unpublished.md`, `appendices.md`
  — verbatim extraction of the Complete Works (1.21M words) from
  ramakrishnavivekananda.info, built by `tools/extract.py` (cached HTML crawl,
  recursive contents → chapters, page-number comments dropped).
- `output/catalogue.{json,csv}` + `INDEX.md` — 896 chapters with genre
  (letter 255 / report 109 / lecture 91 / yoga-course 82 / notes 86 /
  conversation 70 / poem 64 / address 19 / writing 21 / saying 4 / chapter 95),
  parsed dates, places, word counts, source URLs (`tools/catalogue.py`).
- `output/talks/*.md` — the 13 **Complete Talks**, extracted by
  `tools/build_talks.py`, ranges recorded in `tts/talk_ranges.json` so volume
  renders exclude them (each word rendered once).
- `shorts/` — 102 extract-only 60–120 s highlights: `ledger.jsonl`,
  `REVIEW.md` (full text), `TOPICS.md`, `TIERS.md`, `SHORTS.md`.
- `LANGUAGE-POLICY.md` — though never voiced (see §5).

## 2. TTS pipeline

`tools/batch_voices.py` — renders one slug (`talks/<name>` or `volume_N`) and
pushes straight to R2:

- fish law ported from videofactory's `docs/law/FISH-DIRECTION.md`:
  `[break]` / `[long-break]` prefix-only tags, **audit invariant**
  (`stripped(directed) == canonical`), model pinned `fish-audio/s2.1-pro-free`
  (free tier), group cache `sha1(voice|directed)` on vps.
- **Casting** (owner rule): old man `394578d869ee4f99aa6fa500ba664528` = the
  Master; granny `614f8afd83f841048c040b2c6234d2c1` = host (titles, italic
  attributions like "(Delivered in America)", questioners, narration).
- Groups: consecutive same-voice blocks, ≤1600 chars, whole paragraphs only.
- Direction: headings → `[long-break]`; colon-enders/beats → `[break]`;
  a `[break]` prefix after any block lacking terminal punctuation.
- **Rule 8**: hub runs zero ffmpeg. vps does fish → ffmpeg concat → house norm
  (−21 dB mean, −1.5 dB peak, gain clamp ±12) → mp3 128k → `rclone` to
  `r2:longform-audio/vivek/<slug>.mp3`.

Monitoring: `tools/tts_status.py` (console) and `--serve 8612` (dashboard,
R2 sizes, ETA). Per-slug `notify-send` on DONE/FAILED.

Runbook:

```bash
python3 tools/batch_voices.py --slug talks/immortality --dry-run   # plan
python3 tools/batch_voices.py --slug volume_1                      # render
python3 tools/tts_status.py                                        # progress
bash /tmp/opencode/vivek_batch_all.sh                              # full queue (flock-guarded)
```

Overnight resilience: per-slug done markers `/tmp/opencode/done_<slug>`,
3 retry rounds, watchdog `/tmp/opencode/vivek_watchdog.sh` (restarts driver if
absent), completion marker `/tmp/opencode/vivek_batch_complete`.

## 3. Complete Talks (rendered)

13 talks, 6 h 37 m total, in `r2:longform-audio/vivek/talks/` — see
`TALKS-INDEX.md`. `thoughts-on-the-gita` was re-rendered after the Indic guard
(19:06 → 12:05).

## 4. Shorts methodology

- `tools/mine_shorts.py`: paragraph windows 150–300 words (=60–120 s at
  150 wpm), structural potency scoring (parable openers, opening questions,
  punch claims), `CONTINUATION-START` detection; `--volume` mode skips the 13
  talk ranges and splits by chapter.
- Curation is mine (manual): every pick read in full, then tiered
  **S26 / A50 / B21 / C5** in `TIERS.md`; duplicates flagged (only true dup:
  S055 → keeper S044); 5 C-tier picks re-spanned to complete sentences, one
  (S034) remains cut (inline Devanagari).
- `tools/shorts_reuse.py` maps each short's paragraph span onto cached group
  mp3s: exact fish-free slices (28), approx straddles (10), pending until the
  volume batch caches those groups (64).
- Nothing is rendered without owner approval.

## 5. Language guard (Indic script)

Fish cannot read Devanagari/Bengali (proved by `samples/devanagari.mp3`).
`INDIC_RE` (U+0900–U+0D7F) flags blocks in `parse_blocks`; `build_groups`
drops them and logs to `tts/skipped_indic.jsonl`. Corpus-wide: **4,452 blocks
/ 219,792 words skipped** (vol 5–7 are letter volumes with Bengali passages).
Effect: volume 7 groups 657 → 270; audio is English-only by design. The
markdown keeps everything — extraction fidelity untouched.

## 6. Mistakes log (append-only)

1. **scp cannot read stdin in OpenSSH 9 sftp mode** — `scp - remote:path` fails
   (255). Use `ssh remote 'cat > path'` with stdin.
2. **rclone `ls` pads with SPACES here, not tabs** — a `"\t" in line` filter
   silently emptied the R2 column. Parse `split(None, 1)`.
3. **Killing a driver orphans the ssh child** — the remote python keeps
   rendering (it once raced the new job). Always `pkill -f "python3 - <slug>"`
   on the vps as well.
4. **`pgrep -f <pattern>` matches the calling shell** if the pattern appears in
   its own argv — a kill loop once killed the caller. Kill explicit PIDs.
5. **Two drivers race** when a watchdog and a manual launch overlap — solved
   with `flock -n` + done markers (one lock file `/tmp/opencode/vivek_batch.lock`).
6. **Pilot `render_tts.py` had `NameError: PEAK_LIMIT`** — remote f-string
   referenced a local constant. Hardcode `0.84` in the remote script.
7. **Wikisource headings carry NBSP** — chapter matching needed
   `replace("\xa0"," ")` + whitespace collapse, plus snippet disambiguation for
   duplicate chapter titles (e.g. "RECORDED BY MISS S. E. WALDO" × 2).
8. **Shorts spans shift when source text changes** — dropping Indic blocks from
   the gita talk invalidated two spans (S034/S035). Always relocate spans after
   re-extraction (match by preview text), never trust stored indices.
9. **A single chapter can be one giant block** (Gospel Ch XI = 4,442 words) —
   paragraph-granular curation is impossible there; see the ramakrishna repo's
   process notes.

## 7. State at last update

- Talks 13/13 in R2; volume batch running (guard on), ETA ~35–40 h.
- Shorts: 102 tiered, staged, reuse-planned; awaiting approval.

10. **2026-11-15 — rendered full volumes without confirming the product.**
    The agreed deliverables were the 13 Complete Talks (done) and ten ~1 h
    THEMATIC compilations. Instead I queued all 12 volumes (~134 h of text) as
    a "batch"; hours were spent on volume_1, finalizes were interrupted by
    restarts, and nothing listenable landed for volumes. Root cause: I let the
    mechanics (slug queue) define the product. **Rule: render the smallest
    useful artifact first, and confirm the product shape before any long
    queue.** Volumes are now permanently out of the queue; the deliverable
    order is: Complete Talks (done) → shorts (shortest) → topic compilations.
    Volume groups already rendered stay in the vps cache in case they are ever
    wanted.
