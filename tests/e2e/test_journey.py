"""Ordered end-to-end journey: search → edit → convert against the macOS fixture.

Cases run in definition order; later cases observe mutations applied by earlier
ones (the DB is a single mutable working copy for the session). The story is:
read the library, narrow it with filters, edit one track via a stdin pipe, then
convert another track and verify the row swap.
"""

import json
import subprocess

import pytest

from tests.e2e.conftest import STAGED_AUDIO_DIR

pytestmark = pytest.mark.e2e

WAVE_ALPHA_TITLE = "Wave Alpha"
UNICODE_TITLE = "Üñîcödé Mañana"
EDITED_TITLE = "Mañana Edited"


def _load(p: subprocess.CompletedProcess[str]) -> dict:
    assert p.returncode == 0, f"non-zero exit ({p.returncode}); stderr:\n{p.stderr}"
    return json.loads(p.stdout)


def _tracks(p: subprocess.CompletedProcess[str]) -> list[dict]:
    return _load(p)["tracks"]


def _resolve_id(cli, *, title: str) -> str:
    matches = _tracks(cli("search", "--exact-title", title, "--print", "json"))
    assert len(matches) == 1, (
        f"expected 1 track with title {title!r}, got {len(matches)}"
    )
    return matches[0]["ID"]


# ── Group 1: read-only baseline + filter narrowing + snapshots ─────────────


def test_search_total_count(cli):
    assert len(_tracks(cli("search", "--print", "json"))) == 10


def test_search_format_flac(cli):
    assert len(_tracks(cli("search", "--format", "flac", "--print", "json"))) == 3


def test_search_format_mp3(cli):
    assert len(_tracks(cli("search", "--format", "mp3", "--print", "json"))) == 2


def test_search_artist_alpha(cli):
    """Alpha spans FLAC (track 1) + ALAC (track 3) — cross-format filter."""
    assert len(_tracks(cli("search", "--artist", "Alpha", "--print", "json"))) == 2


def test_search_playlist_lossless_only(cli):
    matches = _tracks(
        cli("search", "--exact-playlist", "Lossless Only", "--print", "json")
    )
    assert len(matches) == 6


def test_search_playlist_compressed(cli):
    matches = _tracks(
        cli("search", "--exact-playlist", "Compressed", "--print", "json")
    )
    assert len(matches) == 3


def test_search_match_all_combo(cli):
    """FLAC AND Beta → track 2 only."""
    matches = _tracks(
        cli(
            "search",
            "--format",
            "flac",
            "--artist",
            "Beta",
            "--match-all",
            "--print",
            "json",
        )
    )
    assert len(matches) == 1


def test_search_empty_result_exits_zero(cli):
    result = cli("search", "--title", "DefinitelyNotInLibrary", "--print", "json")
    assert result.returncode == 0
    assert _tracks(result) == []


def test_search_unicode_title_substring(cli):
    """`--title` is a substring match; 'Mañana' narrows to track 10's title."""
    matches = _tracks(cli("search", "--title", "Mañana", "--print", "json"))
    assert len(matches) == 1


def test_search_full_json_snapshot(cli, normalize, snapshot):
    """Locks the search JSON contract: row count, field set, ordering."""
    assert normalize(cli("search", "--print", "json").stdout) == snapshot


def test_search_ids_snapshot(cli, normalize, snapshot):
    """Locks the `--print ids` pipe contract."""
    assert normalize(cli("search", "--print", "ids").stdout) == snapshot


# ── Group 2: stdin pipe + dry-run + roundtrip (edit) ───────────────────────


def test_edit_dry_run_does_not_mutate(cli):
    track10_id = _resolve_id(cli, title=UNICODE_TITLE)
    result = cli(
        "edit",
        "Title",
        "--track-id",
        track10_id,
        "--replace",
        "X",
        "--dry-run",
        "--yes",
    )
    assert result.returncode == 0
    # The original title is still in the DB; the dry-run replacement is not.
    assert (
        len(_tracks(cli("search", "--exact-title", UNICODE_TITLE, "--print", "json")))
        == 1
    )
    assert _tracks(cli("search", "--exact-title", "X", "--print", "json")) == []


def test_edit_via_stdin_pipe(cli):
    """search --artist Théta --print ids | edit Title --replace 'Mañana Edited' --yes."""
    ids_result = cli("search", "--artist", "Théta", "--print", "ids")
    assert ids_result.returncode == 0
    assert ids_result.stdout.strip(), "expected non-empty IDs from search"
    edit_result = cli(
        "edit",
        "Title",
        "--replace",
        EDITED_TITLE,
        "--yes",
        stdin=ids_result.stdout,
    )
    assert edit_result.returncode == 0, edit_result.stderr


def test_edit_roundtrip_new_title_present(cli):
    matches = _tracks(cli("search", "--exact-title", EDITED_TITLE, "--print", "json"))
    assert len(matches) == 1
    assert matches[0]["Title"] == EDITED_TITLE


def test_edit_roundtrip_old_title_gone(cli):
    assert (
        _tracks(cli("search", "--exact-title", UNICODE_TITLE, "--print", "json")) == []
    )


# ── Group 3: dry-run + real + row-swap (convert) ───────────────────────────


def test_convert_dry_run_does_not_mutate(cli):
    track1_id = _resolve_id(cli, title=WAVE_ALPHA_TITLE)
    result = cli(
        "convert",
        "--track-id",
        track1_id,
        "--format-out",
        "mp3",
        "--dry-run",
        "--yes",
    )
    assert result.returncode == 0
    expected_output = STAGED_AUDIO_DIR / "01-flac-44_1k-16b.mp3"
    assert not expected_output.exists()
    assert len(_tracks(cli("search", "--format", "mp3", "--print", "json"))) == 2
    assert len(_tracks(cli("search", "--format", "flac", "--print", "json"))) == 3


def test_convert_flac_to_mp3_writes_new_file(cli):
    track1_id = _resolve_id(cli, title=WAVE_ALPHA_TITLE)
    result = cli("convert", "--track-id", track1_id, "--format-out", "mp3", "--yes")
    assert result.returncode == 0, result.stderr
    assert (STAGED_AUDIO_DIR / "01-flac-44_1k-16b.mp3").exists()


def test_convert_row_swap_on_same_id(cli):
    """Convert mutates the existing row in place — same ID, new format/path."""
    track1_id = _resolve_id(cli, title=WAVE_ALPHA_TITLE)
    matches = _tracks(cli("search", "--track-id", track1_id, "--print", "json"))
    assert len(matches) == 1
    track = matches[0]
    assert track["ID"] == track1_id
    assert track["FileNameL"].endswith(".mp3")


def test_convert_format_counts_shifted(cli):
    """One FLAC became one MP3 in the row swap."""
    assert len(_tracks(cli("search", "--format", "mp3", "--print", "json"))) == 3
    assert len(_tracks(cli("search", "--format", "flac", "--print", "json"))) == 2
