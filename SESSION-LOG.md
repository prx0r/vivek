# Session log — extraction → audio pipeline (2026-11-14)

## Built

1. **Extraction** (prior commits): Complete Works of Vivekananda, 1.21M words,
   one `.md` per volume + `catalogue.json` (896 chapters: genre, date, place,
   source URL) + `INDEX.md`.
2. **Complete Talks** — 13 standalone lectures extracted as their own files
   (`output/talks/`), with block ranges recorded in `tts/talk_ranges.json`
   so volume renders exclude them (each word rendered exactly once).
3. **TTS pipeline** (`tools/batch_voices.py`) — fish law ported from
   videofactory: S2 direction tags ([break]/[long-break], prefix-only,
   stripped==original audit), `s2.1-pro-free` pinned, `sha1(voice|directed)`
   group cache, house norm −21 dB / −1.5 dB, Rule-8 vps pipeline →
   `r2:longform-audio/vivek/`.
   **Casting** (owner rule): old man `394578d8…` = the Master; granny
   `614f8afd…` = host (titles, attributions, questioner, narration).
4. **Monitoring** — `tools/tts_status.py` (console + `--serve 8612` dashboard,
   R2 sizes, ETA), per-slug notify.
5. **Shorts** — full-corpus mining (`tools/mine_shorts.py`, volume mode):
   **102 picks**, 60–120 s, standalone-checked, 15 themes →
   `shorts/ledger.jsonl` + `REVIEW.md` + `TOPICS.md` + `SHORTS.md`.
   **Manual tier review** → `shorts/TIERS.md`: **26 S / 49 A / 17 B / 10 C**
   (10 C = cut or re-span; one true duplicate S055→S044).
6. **Reuse planner** (`tools/shorts_reuse.py`) — maps each short's paragraph
   span to cached group mp3s: 28 exact / 10 approx / 64 pending (filled by
   the volume batch).

## State

- **Talks: 13/13 rendered** (6 h 37 min total, see `TALKS-INDEX.md`) +
  introduction. Volume batch running (vol_1 → … → appendices, ~5.9k groups).
- Shorts: staged, **nothing rendered** (owner gate).
- videofactory PR #5: extraction-repos notice (`docs/EXTRACTION-REPOS.md`).
- Sister repo: prx0r/ramakrishna (Gospel 1907, 82k words; Question-Led
  curation in progress).

## Next

- Volume renders to completion (~30 h remaining).
- Shorts: re-span the C-tier/approx windows, then render on approval
  (fresh fish for exactness ≈1 h for all 102; reuse slices for exact 28).
- Ramakrishna: finish `decisions.tsv` curation → build Question-Led book.
