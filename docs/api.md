# API Reference

Everything the CLI does is available from Python. The public surface is the five functions in `rekordbox_edit.api` and the Pydantic models in `rekordbox_edit.models` that describe their inputs and outputs.

```python
from pyrekordbox import Rekordbox6Database
from rekordbox_edit.api import search
from rekordbox_edit.models import SearchRequest

db = Rekordbox6Database()
response = search(db, SearchRequest(artist=["Daft Punk"], format=["flac"]))
for track in response.tracks:
    print(track.ID, track.Title)
```

Different filter kinds — `artist` and `format` above — AND together by default; repeated values of the same filter OR together. Pass `match_all=True` to flatten everything into one AND, or `match_any=True` to flatten everything into one OR.

`--print json` on any CLI command emits exactly these response envelopes, so the models below also document the JSON you get when scripting.

A write command's response reaches its tracks two ways, though a dry run populates only one of them. For a write command (`edit`, `convert`, `import_tracks`, `remove`), `tracks` at the top level holds what the command actually did, and is empty for a dry run, since a dry run changes nothing. Each op describes the planned or performed state regardless: `result.edits[].track` and its equivalents. Tracks a command declined to touch are not in `tracks`. They are at `result.skipped[].track`, alongside the reason.

## Writing Safely

`edit`, `convert`, `import_tracks`, and `remove` each have checks against concurrent writes. They will refuse to run while Rekordbox is open, raising
[`RekordboxRunningError`][rekordbox_edit.errors.RekordboxRunningError], and each will grab a single-writer advisory lock for the
duration of the write to prevent concurrent writes by other rekordbox-edit processes.

## Functions

::: rekordbox_edit.api.search

::: rekordbox_edit.api.edit

::: rekordbox_edit.api.convert

::: rekordbox_edit.api.import_tracks

::: rekordbox_edit.api.remove

## Progress

`convert` encodes files one at a time and can say which one it is on, for a
caller that wants to show it. Pass any object satisfying this protocol as
`convert(..., progress=)`; how the run is displayed stays with the caller.
The other commands report nothing as they go.

::: rekordbox_edit.api.ConvertProgress

## Models

The models form three layers: the [`FilterArgs`][rekordbox_edit.models.FilterArgs] base that every command shares, the per-command requests and responses, and the lower-level domain types those req/resp models are built from. The write commands extend [`WriteFilterArgs`][rekordbox_edit.models.WriteFilterArgs] instead, which adds the requirement that at least one filter be set.

::: rekordbox_edit.models.FilterArgs

::: rekordbox_edit.models.WriteFilterArgs

### Search

::: rekordbox_edit.models.SearchRequest
    options:
      heading_level: 4

::: rekordbox_edit.models.SearchResponse
    options:
      heading_level: 4

### Edit

::: rekordbox_edit.models.EditRequest
    options:
      heading_level: 4

::: rekordbox_edit.models.EditResponse
    options:
      heading_level: 4

::: rekordbox_edit.models.EditResult
    options:
      heading_level: 4

### Convert

::: rekordbox_edit.models.ConvertRequest
    options:
      heading_level: 4

::: rekordbox_edit.models.ConvertResponse
    options:
      heading_level: 4

::: rekordbox_edit.models.ConvertResult
    options:
      heading_level: 4

### Import

::: rekordbox_edit.models.ImportRequest
    options:
      heading_level: 4

::: rekordbox_edit.models.ImportResponse
    options:
      heading_level: 4

::: rekordbox_edit.models.ImportResult
    options:
      heading_level: 4

### Remove

::: rekordbox_edit.models.RemoveRequest
    options:
      heading_level: 4

::: rekordbox_edit.models.RemoveResponse
    options:
      heading_level: 4

::: rekordbox_edit.models.RemoveResult
    options:
      heading_level: 4

### Miscellaneous

::: rekordbox_edit.models.Track
    options:
      heading_level: 4

::: rekordbox_edit.models.EditOp
    options:
      heading_level: 4

::: rekordbox_edit.models.ConvertOp
    options:
      heading_level: 4

::: rekordbox_edit.models.ImportOp
    options:
      heading_level: 4

::: rekordbox_edit.models.RemoveOp
    options:
      heading_level: 4

::: rekordbox_edit.models.SkippedTrack
    options:
      heading_level: 4

::: rekordbox_edit.models.SkipReason
    options:
      heading_level: 4

## Errors

Most errors these functions raise descend from
[`RekordboxEditError`][rekordbox_edit.errors.RekordboxEditError].
[`InputError`][rekordbox_edit.errors.InputError] also subclasses `ValueError`.
Every error a command raises on purpose is listed here, including the ones
only one command raises, such as
[`ConvertAborted`][rekordbox_edit.errors.ConvertAborted].

::: rekordbox_edit.errors
    options:
      show_root_heading: false
      show_root_toc_entry: false
