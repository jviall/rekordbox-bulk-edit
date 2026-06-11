# Filtering

Every command (`search`, `edit`, `convert`) selects tracks with the same filter options. The filters decide *which* tracks a command sees; the command's own options decide what happens to them.

## Filter Options

Repeating a filter, or combining different filters, matches tracks that satisfy *any* of them (OR logic). Pass `--match-all` to require *every* filter to match (AND logic).

| Option | Matches tracks whose... |
| --- | --- |
| `--track-id ID` | database track ID equals `ID` |
| `--title TEXT` | title contains `TEXT` |
| `--exact-title TEXT` | title is exactly `TEXT` |
| `--artist TEXT` | artist name contains `TEXT` |
| `--exact-artist TEXT` | artist name is exactly `TEXT` |
| `--album TEXT` | album name contains `TEXT` |
| `--exact-album TEXT` | album name is exactly `TEXT` |
| `--playlist TEXT` | playlist name contains `TEXT` |
| `--exact-playlist TEXT` | playlist name is exactly `TEXT` |
| `--format FMT` | file format is `FMT` (`mp3`, `flac`, `aiff`, `wav`, `m4a`) |
| `--path TEXT` | file path contains `TEXT` (matched against the folder path, filename, or both) |
| `--exact-path TEXT` | file path is exactly `TEXT` (resolved to an absolute path before matching) |

**Examples:**

```bash
# Tracks by either artist (OR)
rbe search --artist "Daft Punk" --artist "Justice"

# Tracks matching artist AND format
rbe search --artist "Aphex Twin" --format flac --match-all

# All the songs in this playlist
rbe search --exact-playlist "Main Room 2024"

# All the songs in all my "house" or "disco" playlists
rbe search --playlist "house" --playlist "disco"

# All the songs in my library that aren't in any playlist
rbe search --playlist ""

# Tracks whose path contains a folder or filename substring
rbe search --path "Favorites/" --path "track.wav"

# The track at an exact location
rbe search --exact-path "/Users/djmustard/Music/banger.mp3"
```

## Limiting Results

- `--first N`: return only the first N results
- `--last N`: return only the last N results

The two are mutually exclusive. They make a great blast radius limiter while you refine a filter: `rbe convert --artist "Crazy Frog" --first 5 --dry-run`.

## Track ID Arguments

Any positional argument that is not a defined option is interpreted as one or more track IDs:

```bash
rbe search 12345 67890
```

Track IDs can also arrive on stdin (see [Scripting and Piping](#scripting-and-piping)). Piped IDs require `--yes` or `--dry-run`, since prompting would interrupt a pipeline.

## Output Levels

All commands take `--print [silent|ids|info|debug|json]`:

- `info` (default): human-readable output
- `debug`: adds application state detail; debug logs for every run are also written to a log file (the path is shown in `--help`)
- `silent`: no output
- `ids`: print only the matching track IDs, space-separated — designed for piping
- `json`: dump the full response envelope as JSON — a list of [`Track`][rekordbox_edit.models.Track] records plus a result summary (see the response models in the [API Reference](api.md))

!!! note

    `silent`, `ids`, and `json` exist for scripting, so they require `--yes` or `--dry-run`: an interactive confirmation prompt would contradict them.

## Scripting and Piping

`--print ids` output feeds straight into another command's track-ID arguments:

```bash
# Convert all of the items found by the initial search command
rbe search --artist "Lauryn Hill" --print ids | rbe convert --yes
```

Piping composes OR and AND logic that a single command cannot express:

**AND-narrowing** — pipe a broad OR result into a second command with `--match-all` to intersect:

```bash
# (Daft Punk OR Justice) AND flac
rbe search --artist "Daft Punk" --artist "Justice" --print ids \
  | rbe search --format flac --match-all
```

**OR between AND-groups** — merge results from two commands using a subshell:

```bash
# (Daft Punk AND flac) OR (Justice AND aiff)
{ rbe search --artist "Daft Punk" --format flac --match-all --print ids; \
  rbe search --artist "Justice" --format aiff --match-all --print ids; } \
  | rbe convert --format-out mp3 --dry-run
```

For richer pipelines, `--print json` emits the same selection as structured data for `jq` or a Python script.
