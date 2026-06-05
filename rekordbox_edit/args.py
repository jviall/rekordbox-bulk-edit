"""Dataclass containers for CLI argument groups.

These types are the public API of the functional layer below the CLI: callers
of `get_filtered_content` and the private command helpers receive them in lieu
of long flat parameter lists. Each `*_from_kwargs` factory packs the matching
Click parameters into its dataclass.
"""

from dataclasses import dataclass, field


@dataclass
class FilterArgs:
    """Filter inputs forwarded to `get_filtered_content`.

    Field names mirror the Click parameter names: `track_ids` holds the
    positional TRACK_IDS argument (variadic), `track_id` holds the values of
    the repeated `--track-id` option.
    """

    track_id: list[str] = field(default_factory=list)
    track_ids: list[str] = field(default_factory=list)
    title: list[str] = field(default_factory=list)
    exact_title: list[str] = field(default_factory=list)
    playlist: list[str] = field(default_factory=list)
    exact_playlist: list[str] = field(default_factory=list)
    artist: list[str] = field(default_factory=list)
    exact_artist: list[str] = field(default_factory=list)
    album: list[str] = field(default_factory=list)
    exact_album: list[str] = field(default_factory=list)
    path: list[str] = field(default_factory=list)
    exact_path: list[str] = field(default_factory=list)
    format: list[str] = field(default_factory=list)
    match_all: bool = False


def filter_args_from_kwargs(**kwargs) -> FilterArgs:
    """Pack the flat Click kwargs for the `global_click_filters` group into a FilterArgs."""
    return FilterArgs(
        track_id=list(kwargs.get("track_id") or []),
        track_ids=list(kwargs.get("track_ids") or []),
        title=list(kwargs.get("title") or []),
        exact_title=list(kwargs.get("exact_title") or []),
        playlist=list(kwargs.get("playlist") or []),
        exact_playlist=list(kwargs.get("exact_playlist") or []),
        artist=list(kwargs.get("artist") or []),
        exact_artist=list(kwargs.get("exact_artist") or []),
        album=list(kwargs.get("album") or []),
        exact_album=list(kwargs.get("exact_album") or []),
        path=list(kwargs.get("path") or []),
        exact_path=list(kwargs.get("exact_path") or []),
        format=list(kwargs.get("format") or []),
        match_all=bool(kwargs.get("match_all", False)),
    )
