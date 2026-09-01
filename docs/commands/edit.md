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
rbe edit --title "Teh" Title --match "Teh" --replace "The"
```

## FolderPath

`FolderPath` repoints a track at an audio file on disk. Because several other columns are implicitly based on this path and other file metadata, the edit keeps these dependent columns consistent:

- `FileNameL` always matches the new path's file name, and `OrgFolderPath` is updated when it matched the old path.
- When the new file's size differs from the recorded `FileSize`, the file is probed and all of `FileType`, `SampleRate`, `BitDepth`, `BitRate`, `FileSize`, and `Length` are rewritten to match it.
- When the file name changes, the `PPTH` path tag inside the track's analysis (ANLZ) files is rewritten to match. All other analysis data is left alone.

By default edits will be skipped in the following cases:

- The new path's file does not exist.
- The new path points to a file whose duration doesn't match what's in rekordbox _and_ the track has cues or an analysis, since those are time-indexed and would land misaligned.
- The file's format is one Rekordbox doesn't support--this is always skipped.

Each of the first two cases is a gate with its own flag, and `edit` lists the tracks it holds back and asks about it separately: `--allow-missing` writes a path with no file behind it, updating only the path columns, and `--allow-mismatch` accepts a duration that contradicts the stored length. Passing a flag answers its question up front, so no prompt appears. `--yes` takes the default answer to every prompt, and a gate's default is no, so `--yes` on its own leaves the held-back tracks skipped and reports them.

```bash
# Relocate a library folder in bulk
rbe edit FolderPath --match "/Volumes/OldDrive/Music" --replace "/Volumes/NewDrive/Music"

# Point one track at a replacement file
rbe edit --exact-title "Acid Rain" FolderPath --replace "/Users/me/Music/acid-rain-remaster.flac"
```

## Checks

- Without flags, `edit` shows every planned change and asks once before applying. `--interactive` confirms each track individually; `--dry-run` previews without writing; `--yes` confirms the default choice for all prompts without asking. `--interactive` cannot be combined with `--yes` or `--dry-run`.
- `edit` writes exactly the tracks the preview showed. If in between the time you're prompted and later confirm a new track lands in your library that matches your filters, it won't be included. A track whose file changed in that window is skipped rather than written with stale metadata.
- **Rekordbox running:** writing while Rekordbox is open risks losing your changes, so `edit` will refuse to perform any writes. `--dry-run` is unaffected.

## Examples

```bash
# Preview a cleanup without touching the database
rbe edit --title "(Original Mix)" Title --match " (Original Mix)" --replace "" --dry-run

# Apply it, confirming each track
rbe edit --title "(Original Mix)" Title --match " (Original Mix)" --replace "" --interactive

# Pipe a search result in and edit those exact tracks
rbe search --playlist "Mislabeled" --print ids | rbe edit Title --match "  " --replace " " --yes
```

See [Filtering](../filtering.md) for the full filter language.

## Reference

<!-- prettier-ignore -->
::: mkdocs-click
    :module: rekordbox_edit.cli.edit
    :command: edit_command
    :prog_name: rbe edit
    :depth: 1
