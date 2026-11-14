# Vivekananda — Complete Works (extraction)

Faithful, machine-readable extraction of *The Complete Works of Swami
Vivekananda* from https://www.ramakrishnavivekananda.info/vivekananda/

Pure extraction: no writing, no editing, no paraphrase. The source's own
chapter hierarchy, headings, subtitles and paragraphs are preserved; only
navigation, page-number comments and HTML boilerplate are stripped.

## Contents

- `output/` — one Markdown file per source volume:
  `introduction.md`, `volume_1.md` … `volume_9.md`, `unpublished.md`,
  `appendices.md`
- `output/catalogue.json` / `output/catalogue.csv` — per-chapter metadata
  (volume, work group, genre, date, place, word count, source URL)
- `output/INDEX.md` — human-readable catalogue grouped by volume
- `tools/extract.py` — scraper (ISO-8859-1, recursive contents → chapters,
  raw HTML cached under `cache/` for resumable runs)
- `tools/catalogue.py` — derives the structured catalogue from the cached HTML

## Run

```bash
python3 tools/extract.py          # writes output/*.md (uses cache/ when present)
python3 tools/catalogue.py        # writes output/catalogue.{json,csv}, INDEX.md
```

## Metadata fields

| field | meaning |
|---|---|
| `volume` | source volume file |
| `work_group` / `part_path` | contents-tree part (e.g. *Addresses at the Parliament*, *Karma-Yoga*, *Epistles*) |
| `chapter` | chapter heading |
| `genre` | derived from part: address / lecture / yoga-course / letter / poem / conversation / saying / notes / report / appendix |
| `date_iso`, `year` | parsed from the italic subtitle where present |
| `place` | only when the part header declares it (e.g. *Chicago 1893*) |
| `words` | body word count |
| `url`, `slug` | source link and slug |

## Source & rights

Text source: `ramakrishnavivekananda.info`. Swami Vivekananda died in 1902;
these writings are in the public domain. This repository is an extraction of
that public-domain text and claims nothing beyond it. `cache/` (raw HTML) is
not committed.
