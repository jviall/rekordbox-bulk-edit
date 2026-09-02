# API Reference

Everything the CLI does is available from Python. The public surface is the four functions in `rekordbox_edit.api` and the Pydantic models in `rekordbox_edit.models` that describe their inputs and outputs.

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

## Writing Safely

`edit`, `convert`, and `import_tracks` each have checks against concurrent writes. They will refuse to run while Rekordbox is open, raising
[`RekordboxRunningError`][rekordbox_edit.errors.RekordboxRunningError], and each will grab a single-writer advisory lock for the
duration of the write to prevent concurrent writes by other rekordbox-edit processes.

## Errors

Most errors these functions raise descend from
[`RekordboxEditError`][rekordbox_edit.errors.RekordboxEditError].
[`InputError`][rekordbox_edit.errors.InputError] also subclasses `ValueError`.

::: rekordbox_edit.errors

## Functions

::: rekordbox_edit.api.search

::: rekordbox_edit.api.edit

::: rekordbox_edit.api.convert

::: rekordbox_edit.api.import_tracks

## Models

The models form three layers: the [`FilterArgs`][rekordbox_edit.models.FilterArgs] base that every command shares, the per-command requests and responses, and the lower-level domain types those req/resp models are built from.

::: rekordbox_edit.models.FilterArgs

### Search

::: rekordbox_edit.models.SearchRequest

::: rekordbox_edit.models.SearchResponse

### Edit

::: rekordbox_edit.models.EditRequest

::: rekordbox_edit.models.EditResponse

::: rekordbox_edit.models.EditResult

### Convert

::: rekordbox_edit.models.ConvertRequest

::: rekordbox_edit.models.ConvertResponse

::: rekordbox_edit.models.ConvertResult

### Import

::: rekordbox_edit.models.ImportRequest

::: rekordbox_edit.models.ImportResponse

::: rekordbox_edit.models.ImportResult

### Miscellaneous

::: rekordbox_edit.models.Track

::: rekordbox_edit.models.EditOp

::: rekordbox_edit.models.ConvertOp

::: rekordbox_edit.models.ImportOp

::: rekordbox_edit.models.SkippedTrack

::: rekordbox_edit.models.SkipReason
