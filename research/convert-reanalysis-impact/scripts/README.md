# Research Scripts

Read-only probes of the local rekordbox 6 library used for
`../convert-anlz-cue-impact.md`. They query `master.db` through pyrekordbox and
parse the on-disk ANLZ files. None of them writes to the database or to any ANLZ
file. Run from the repo root, for example:

```
uv run python research/convert-reanalysis-impact/scripts/anlz_census.py
```

| Script | Evidence file | Purpose |
| --- | --- | --- |
| `inventory.py` | `../evidence/01-inventory.txt` | Fixture playlists and their content rows |
| `cue_schema.py` | `../evidence/02-cue-schema.txt` | `DjmdCue` columns and cue-rich tracks |
| `cue_fields_by_format.py` | `../evidence/03-cue-fields-by-format.txt` | Cue time vs byte-seek fields per format |
| `anlz_deep.py` | `../evidence/04-anlz-deep.txt` | Raw tag walk plus parsed grid, cues, waveforms |
| `anlz_census.py` | `../evidence/05-census.txt` | Library-wide tag census and cue-emptiness proof |
| `content_columns.py` | `../evidence/06-content-columns.txt` | Stale `DjmdContent` columns after convert |
| `analysis_flags.py` | `../evidence/07-analysis-flags.txt` | `Analysed` / `AnalysisUpdated` / lock columns |
