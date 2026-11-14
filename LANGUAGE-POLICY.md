# Language policy — Indic script never reaches TTS

**Decision (owner, 2026-11-14):** the fish voices cannot read Devanagari,
Bengali, or any Indic script — rendered audio mangles it. Therefore
**Indic-script blocks are never sent to TTS**. The English text around them is
unaffected; the markdown keeps everything (extraction fidelity is unchanged),
only the *audio path* skips non-Latin blocks.

## How the guard works

- `tools/batch_voices.py` — `INDIC_RE` matches U+0900–U+0D7F (Devanagari,
  Bengali, Gurmukhi, Gujarati, Tamil, Telugu, Kannada, Malayalam).
  `parse_blocks()` flags each block; `build_groups()` drops flagged blocks
  before direction/grouping, and records counts to
  `tts/skipped_indic.jsonl`.
- `tools/build_talks.py` — talk files are extracted **without** Indic blocks
  (so the 13 talks re-render clean).
- Audit invariant untouched: stripping our direction tags still equals the
  (now Indic-free) block text.

## Scope of the skip (measured 2026-11-14)

| file | Indic blocks | words skipped |
|---|---:|---:|
| volume_1 | 235 | 1,130 |
| volume_3 | 68 | 16,247 |
| volume_4 | 330 | 20,361 |
| volume_5 | 786 | 39,881 |
| volume_6 | 1,219 | 56,122 |
| volume_7 | 1,274 | 70,228 |
| volume_8 | 403 | 11,866 |
| volume_9 | 131 | 2,949 |
| talks/thoughts-on-the-gita | 6 | 1,008 |
| **total** | **4,452** | **219,792** |

Volumes 5–7 are letter volumes with Bengali passages in the source; the
English commentary around them is still voiced. Groups collapse accordingly
(e.g. volume_7: 657 → 270 groups).

## Consequences

- Audio is English-only by design; non-Latin quotations are silent gaps in the
  narration (they are rare per page and surrounded by English).
- `thoughts-on-the-gita` was re-rendered after the guard (its old audio
  contained garbled Deva).
- Shorts: full corpus re-scanned — zero Indic spans remain (S034, which
  contained Deva, is permanently CUT).
- The 3 voice samples (`r2:longform-audio/vivek/samples/`) document the
  failure mode: `devanagari.mp3` is the "before".

## Not allowed

- Transliterating Devanagari for TTS without owner sign-off (that would be
  editing, even if mechanical).
- Rendering Indic blocks on a future model without re-testing a sample first.
