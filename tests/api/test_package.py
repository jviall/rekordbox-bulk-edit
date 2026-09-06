"""Tests for the rekordbox_edit.api package surface."""

import importlib

import pytest

import rekordbox_edit.api as api

PUBLIC_FUNCTIONS = ["search", "edit", "convert", "import_tracks", "remove"]


def test_the_public_names_are_the_whole_surface():
    assert api.__all__ == PUBLIC_FUNCTIONS


@pytest.mark.parametrize("name", PUBLIC_FUNCTIONS)
def test_every_public_name_is_a_function(name):
    """A re-export used to share its name with the submodule defining it, so
    reaching the function left the submodule unreachable (issue #212)."""
    assert callable(getattr(api, name))


@pytest.mark.parametrize(
    "module", ["_search", "_edit", "_convert", "_import", "_remove"]
)
def test_each_implementation_module_stays_reachable(module):
    """monkeypatch and other dotted-string lookups resolve by attribute chain,
    so a shadowed submodule cannot be patched by name."""
    assert getattr(api, module) is importlib.import_module(
        f"rekordbox_edit.api.{module}"
    )
