# Filtering

Every command supports filtering by all of the [`FilterArgs`][rekordbox_edit.models.FilterArgs]. The filters determine which tracks a command operates on.

## Filter Options

Repeating a filter, or combining different filters, matches tracks that satisfy *any* of the provided filters. Pass `--match-all` to require *every* filter to match.

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
| `--first N` | return only the first N results |
| `--last N` | return only the last N results |

> [!TIP]
> Filters that are "exact" are case-sensitive (e.g. `--exact-artist 'HOOBASTANK'` won't match "Hoobastank") whereas their counterparts (`--artist`) are case-insensitive and match substrings. Only one of either the `--first` and `--last` filters can be provided at a time as they're mutually exclusive.


### Examples

```bash
# Tracks by either artist
rbe search --artist "Daft Punk" --artist "Justice"

# Tracks matching artist AND format
rbe search --artist "Aphex Twin" --format flac --match-all

# All the songs in this playlist
rbe search --exact-playlist "Main Room 2024"

# All the songs in all my "house" or "disco" playlists
rbe search --playlist "house" --playlist "disco"

# All the songs in my library that aren't in any playlist
rbe search --playlist ""

# The first 10 tracks whose path contains a folder or filename substring
rbe search --path "Favorites/" --path "track.wav" --first 10

# The track at an exact location
rbe search --exact-path "/Users/djmustard/Music/banger.mp3"
```

## Track ID Arguments

Any positional argument that is not a defined option is interpreted as one or more track IDs:

```bash
rbe search 12345 67890
```

Track IDs can also arrive on stdin (see [Scripting and Piping](#scripting-and-piping)). Piped IDs require `--yes` or `--dry-run`, since prompting would interrupt a pipeline.

## Output Levels

All commands take `--print [silent|ids|info|debug|json]`:

- `info` (default): human-readable output
- `debug`: adds application state detail; debug logs for every run are also written to a log file (the path to which is shown in `--help`)
- `silent`: no output at all
- `ids`: print only the matching track IDs, space-separated — designed for piping between consecutive `rbe` commands.
- `json`: dump the full response envelope as JSON — a list of [`Track`][rekordbox_edit.models.Track] records plus a result summary (see the response models in the [API Reference](api.md))

!!! note

    `silent`, `ids`, and `json` are non-interactive print modes, so they require `--yes` or `--dry-run`.

## Scripting and Piping

`--print ids` output feeds straight into another command's track-ID arguments:

```bash
# Convert all of the items found by the initial search command
rbe search --artist "Lauryn Hill" --print ids | rbe convert --yes
```

Piping allows you to compose OR and AND logic that a single command could not express by itself:

**AND-narrowing** — pipe a broad OR result into a second command with `--match-all` to intersect:

```bash
# Search all (Daft Punk OR Justice) AND flac
rbe search --artist "Daft Punk" --artist "Justice" --print ids \
  | rbe search --format flac --match-all
```

**OR between AND-groups** — merge results from two commands using a subshell:

```bash
# Convert all (Daft Punk AND flac) OR (Justice AND aiff)
{ rbe search --artist "Daft Punk" --format flac --match-all --print ids; \
  rbe search --artist "Justice" --format aiff --match-all --print ids; } \
  | rbe convert --format-out mp3 --dry-run
```

For richer pipelines, `--print json` emits the same selection as structured data for `jq` and other shell tools. Use the [API functions](/api/#functions) if you want to build a more complex python script.
