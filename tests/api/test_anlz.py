"""Byte-level ANLZ path rewriting."""

import struct

import pytest
from pyrekordbox.anlz.file import AnlzFile

from tests.anlz_helpers import FILE_HEADER, UNPARSED_TAG, anlz, path_tag, tag

from rekordbox_edit.api._anlz import AnlzFormatError, read_path, set_path


class TestSetPath:
    def test_writes_a_path_rekordbox_can_read_back(self):
        data = anlz(path_tag("?/old name.flac"))

        result = set_path(data, "?/new name.mp3")

        # Verified through pyrekordbox's own parser, not our reader, so this
        # asserts the output is well-formed rather than merely self-consistent.
        assert AnlzFile.parse(result).get("path") == "?/new name.mp3"

    def test_preserves_tags_the_parser_does_not_understand(self):
        data = anlz(path_tag("?/old.flac"), UNPARSED_TAG)

        result = set_path(data, "?/new.mp3")

        assert UNPARSED_TAG in result

    def test_writing_the_same_path_leaves_bytes_unchanged(self):
        data = anlz(path_tag("?/song.flac"), UNPARSED_TAG)

        assert set_path(data, "?/song.flac") == data

    def test_updates_len_file_when_the_path_length_changes(self):
        data = anlz(path_tag("?/short.flac"), UNPARSED_TAG)

        result = set_path(data, "?/a considerably longer name.flac")

        assert FILE_HEADER.unpack_from(result, 0)[2] == len(result)

    def test_rewrites_a_file_pyrekordbox_cannot_parse(self):
        # A PQTZ tag whose content is too short for its struct: pyrekordbox
        # raises, but the tag run is still walkable by declared length.
        data = anlz(path_tag("?/old.flac"), tag(b"PQTZ", b"\x00"))
        with pytest.raises(Exception):
            AnlzFile.parse(data)

        result = set_path(data, "?/new.mp3")

        assert read_path(result) == "?/new.mp3"

    def test_rejects_a_file_that_is_not_anlz(self):
        with pytest.raises(AnlzFormatError):
            set_path(b"NOPE" + b"\x00" * 40, "?/new.mp3")

    def test_rejects_a_file_with_no_path_tag(self):
        with pytest.raises(AnlzFormatError):
            set_path(anlz(UNPARSED_TAG), "?/new.mp3")

    def test_rejects_a_tag_that_overruns_the_file(self):
        good = anlz(path_tag("?/old.flac"))
        # Declare a tag length past the end of the buffer.
        corrupt = bytearray(good)
        struct.pack_into(">I", corrupt, 28 + 8, 9999)
        with pytest.raises(AnlzFormatError):
            set_path(bytes(corrupt), "?/new.mp3")


class TestReadPath:
    def test_returns_the_stored_path(self):
        assert read_path(anlz(path_tag("?/song.flac"))) == "?/song.flac"

    def test_rejects_a_file_with_no_path_tag(self):
        with pytest.raises(AnlzFormatError):
            read_path(anlz(UNPARSED_TAG))
