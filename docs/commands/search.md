# search

Find and display tracks in your Rekordbox database. `search` is read-only: it never modifies the database or your files, which makes it the safe way to rehearse a [filter](../filtering.md) before handing it to `edit` or `convert`.

## Examples

```bash
# Show all FLAC tracks by an artist
rbe search --artist "Aphex Twin" --format flac

# Get all the track IDs in a playlist
rbe search --playlist "Techno" --print ids

# Tracks that are either flac, or in this playlist
rbe search --playlist "Techno" --format flac --match-any

# Feed results to another command
rbe search --artist "Lauryn Hill" --print ids | rbe convert --yes
```

See [Filtering](../filtering.md) for the full filter language and piping recipes.

## Reference

::: mkdocs-click
    :module: rekordbox_edit.cli.search
    :command: search_command
    :prog_name: rbe search
    :depth: 1
