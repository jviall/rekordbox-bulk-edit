# API Reference

Everything the CLI does is available from Python. The public surface is the three functions in `rekordbox_edit.api` and the Pydantic models in `rekordbox_edit.models` that describe their inputs and outputs.

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

## Functions

::: rekordbox_edit.api.search

::: rekordbox_edit.api.edit

::: rekordbox_edit.api.convert

## Models

The models form three layers: the [`FilterArgs`][rekordbox_edit.models.FilterArgs] base that every command shares, the per-command requests and responses, and the lower-level domain types those req/resp models are built from.

::: rekordbox_edit.models.FilterArgs
options:
heading_level: 3

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

::: rekordbox_edit.models.SkippedTrack
options:
heading_level: 4

::: rekordbox_edit.models.SkipReason
options:
heading_level: 4
