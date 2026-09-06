# Filtering

Most commands support filtering by all of the [`FilterArgs`][rekordbox_edit.models.FilterArgs]. The filters determine which Rekordbox tracks a command operates on.

`search` runs unfiltered and returns the whole collection. The commands that write to existing records — `edit`, `convert`, and `remove` — require at least one filter, since an unfiltered write would match every track in the library. `--first` and `--last` bound how many tracks a filter returns rather than selecting any, so neither satisfies the requirement on its own.

## Filter Options

By default any filters provided are grouped by kind: repeating the _same_ filter with different values matches tracks that satisfy _any_ of those values (an OR), while combining _different_ filters narrows to tracks that satisfy every one of them (an AND). Pass `--match-all` to find results that match each and every filter value. Pass `--match-any` to instead match tracks that satisfy any single filter value provided.

| Option                  | Matches tracks whose...                                                                               |
| ----------------------- | ----------------------------------------------------------------------------------------------------- |
| `--track-id ID`         | database track ID equals `ID`                                                                         |
| `--title TEXT`          | title contains `TEXT`                                                                                 |
| `--exact-title TEXT`    | title is exactly `TEXT`                                                                               |
| `--artist TEXT`         | artist name contains `TEXT`                                                                           |
| `--exact-artist TEXT`   | artist name is exactly `TEXT`                                                                         |
| `--album TEXT`          | album name contains `TEXT`                                                                            |
| `--exact-album TEXT`    | album name is exactly `TEXT`                                                                          |
| `--playlist TEXT`       | playlist name contains `TEXT`                                                                         |
| `--exact-playlist TEXT` | playlist name is exactly `TEXT`                                                                       |
| `--format FMT`          | Rekordbox file type is `FMT` (`mp3`, `mp4`, `aac`, `flac`, `alac`, `wav`, `aiff`, `video`, `invalid`) |
| `--path TEXT`           | file path contains `TEXT`, case-insensitive                                                           |
| `--resolved-path TEXT`  | file path contains `TEXT` after resolving it to an absolute path, case-insensitive                    |
| `--first N`             | return only the first N results                                                                       |
| `--last N`              | return only the last N results                                                                        |

> [!TIP]
> Filters that are "exact" are case-sensitive (e.g. `--exact-artist 'HOOBASTANK'` won't match "Hoobastank") whereas their counterparts (`--artist`) are case-insensitive and match substrings.

> [!NOTE]
> Path filters match case-insensitively on every platform because the filesystems Rekordbox supports (NTFS and APFS) treat paths case-insensitively themselves.

### Examples

```bash
# Tracks by either artist (repeated filters OR together, by default)
rbe search --artist "Daft Punk" --artist "Justice"

# Tracks matching artist AND format (different filters AND together, by default)
rbe search --artist "Aphex Twin" --format flac

# Tracks that are either flac, or by Aphex Twin
rbe search --artist "Aphex Twin" --format flac --match-any

# Tracks that match both Tom Petty and The Heartbreakers
rbe search --artist "Tom Petty" --artist "The Heartbreakers" --match-all

# All the songs in this playlist
rbe search --exact-playlist "Main Room 2024"

# All the songs in any "house" or "disco" playlists
rbe search --playlist "house" --playlist "disco"

# All the songs in my library that aren't in any playlist
rbe search --playlist ""

# The first 10 tracks that either live under a "Favorites" folder or have the word "remix" somewhere in the file path
rbe search --path "Favorites/" --path "remix" --first 10

# The track at an exact location
rbe search --resolved-path "/Users/djmustard/Music/banger.mp3"

# Every track under a folder, given relative to the current directory
rbe search --resolved-path "../Music/house/"
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

## Confirmations

Every command that writes previews its plan and asks before applying it. You can change this behavior by providing one of:

- `--dry-run` prints the plan and stops. Nothing is written.
- `--interactive` (`-i`) asks about each item separately rather than once about the whole plan. It cannot be combined with `--yes` or `--dry-run`.
- `--yes` (`-y`) approves the plan and other prompts without asking.

!!! note

    Command-specific guards require providing their corresponding flag to override their default behavior. For example, providing `--yes` to the convert command will not overwrite existing files unless you explicitly provide the `--overwrite` flag.

For every command, if a check decides to skip them, the corresponding operation will be returned in the response with an explanatory [SkipReason](api.md#rekordbox_edit.models.SkipReason).

## Scripting and Piping

`--print ids` output feeds straight into another command's track-ID arguments:

```bash
# Convert all of the items found by the initial search command
rbe search --artist "Lauryn Hill" --print ids | rbe convert --format-out aiff --yes
```

**OR between AND-groups** — merge results from two commands using a subshell:

```bash
# Convert all (Daft Punk AND flac) OR (Justice AND aiff)
{ rbe search --artist "Daft Punk" --format flac --print ids; \
  rbe search --artist "Justice" --format aiff --print ids; } \
  | rbe convert --format-out mp3 --dry-run
```

For richer pipelines, `--print json` emits the same selection as a structured database dump for `jq` and other shell tools. Use the [API functions](api.md#functions) if you want to build a more complex python script.
