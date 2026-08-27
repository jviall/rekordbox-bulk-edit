# edit

Bulk-edit a metadata field on tracks in your Rekordbox database.

```bash
rbe edit [OPTIONS] [TRACK-IDS]... FIELD
```

`FIELD` specifies the [DjmdContent](https://pyrekordbox.readthedocs.io/en/latest/formats/db6.html#djmdcontent) column to change. The editable fields are `Title`, `Comment`, `ArtistName`, `AlbumName`, `Rating`, and `FolderPath`.

`--replace` supplies the new value. On its own it overwrites the whole field; add `--match PATTERN` to find that literal text within the field and replace only that portion:

```bash
# Rename one track outright
rbe edit --exact-title "Untitled 3" Title --replace "Acid Rain"

# Fix a typo across many titles (substring replacement)
rbe edit --title "Teh" Title --match "Teh" --replace "The" --multi
```

## FolderPath

`FolderPath` repoints a track at an audio file on disk. Because the database row carries more than the path, the edit keeps the dependent columns consistent:

- `FileNameL` always follows the new path's file name, and `OrgFolderPath` follows when it matched the old path.
- When the new file's size differs from the recorded `FileSize`, the file is probed and the technical columns (`FileType`, `SampleRate`, `BitDepth`, `BitRate`, `FileSize`, `Length`) are rewritten to describe it. A byte-identical file, the usual case when relocating a library, needs no probe and no sync.
- When the file name changes, the `PPTH` path tag inside the track's analysis (ANLZ) files is rewritten to match. Beat grids, cues, and waveforms are indexed by time and are never touched, and the `Analysed` flag is left alone so Rekordbox does not re-analyze.

Two safety checks hold a track back, and both can be overridden. A path whose file does not exist is skipped; overriding writes only the path columns, with nothing to probe. A file whose duration contradicts the track's stored length by more than a second is skipped when the track has cues or an analysis, since those are time-indexed and would land misaligned. In the default flow `edit` lists held-back tracks and asks once whether to include them; in scripted runs (`--yes`) they stay skipped unless you pass `--force`. A file whose format Rekordbox cannot play is always skipped.

```bash
# Relocate a library folder in bulk
rbe edit FolderPath --match "/Volumes/OldDrive/Music" --replace "/Volumes/NewDrive/Music" --multi

# Point one track at a replacement file
rbe edit --exact-title "Acid Rain" FolderPath --replace "/Users/me/Music/acid-rain-remaster.flac"
```

## Guardrails

- **Preview and confirm by default.** Without flags, `edit` shows every planned change and asks once before applying. `--interactive` confirms each track individually; `--dry-run` previews without writing; `--yes` confirms the default choice for all prompts without asking.
- **Single-track by default.** When filters match more than one track, `edit` refuses unless you pass `--multi`. This prevents an unintentionally broad filter from making unintended edits across your library.
- **Rekordbox running:** editing while Rekordbox is open risks corrupting your database. By default `edit` warns; in a non-interactive mode (e.g. `--print ids`) it throws an error.

## Examples

```bash
# Preview a cleanup without touching the database
rbe edit --title "(Original Mix)" Title --match " (Original Mix)" --replace "" --multi --dry-run

# Apply it, confirming each track
rbe edit --title "(Original Mix)" Title --match " (Original Mix)" --replace "" --multi --interactive

# Pipe a search result in and edit those exact tracks
rbe search --playlist "Mislabeled" --print ids | rbe edit Title --match "  " --replace " " --multi --yes
```

See [Filtering](../filtering.md) for the full filter language.

## Reference

::: mkdocs-click
    :module: rekordbox_edit.cli.edit
    :command: edit_command
    :prog_name: rbe edit
    :depth: 1
