# remove

Delete tracks from your Rekordbox collection, optionally removing the source files as well.

```bash
rbe remove [OPTIONS] [TRACK-IDS]...
```

## What Gets Deleted

`remove` deletes the track's database row, every record that references it, and the track's analysis and artwork files. If that removal leaves an artist, album, genre, or label with no tracks behind it, that record is deleted too, so the library doesn't accumulate empty metadata over time.

### Removing the Audio Source

Removing a track from the library does not touch the audio file it points to. Pass `--delete-source` to delete that file as well.

`--delete-source` will delete all matching track files **permanently**.

## This Cannot Be Undone

> [!CAUTION]
> **This command cannot be undone**. There is no undo for `remove`. Even if you re-import your files, any analysis or other Rekordbox metadata like playlists and play counts will be lost. Run with `--dry-run` first and review the plan before committing to it, and back up your library before removing in bulk.

## Checks

- Without flags, `remove` shows every planned removal and asks once before applying. See [Confirmations](../filtering.md#confirmations) for how `--dry-run`, `--interactive`, and `--yes` change that.
- `remove` deletes exactly the tracks the preview showed. A track whose row vanished between the preview and your confirmation is skipped rather than removed; a track whose row changed is still removed as planned.
- `remove` requires at least one filter, the same as `edit` and `convert`, so an unfiltered invocation cannot match the whole library. `--first` and `--last` bound how many tracks a filter returns rather than selecting any, so neither counts on its own.
- **Rekordbox running:** writing while Rekordbox is open risks losing your changes, so `remove` will refuse to perform any writes. `--dry-run` is unaffected.

## Examples

```bash
# Preview what a removal would do
rbe remove --artist "Unknown Artist" --dry-run

# Remove tracks matching a filter, confirming once
rbe remove --title "(Demo)" --exact-title "Demo Loop"

# Confirm each track individually, and remove its source file too
rbe remove --playlist "Duplicates" --interactive --delete-source

# Remove a piped-in set of tracks without prompting
rbe search --resolved-path "/Volumes/OldDrive" --print ids | rbe remove --yes --print ids
```

See [Filtering](../filtering.md) for the full filter language.

## Reference

<!-- prettier-ignore -->
::: mkdocs-click
    :module: rekordbox_edit.cli.remove
    :command: remove_command
    :prog_name: rbe remove
    :depth: 1
