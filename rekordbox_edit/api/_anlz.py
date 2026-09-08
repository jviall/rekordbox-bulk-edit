"""Byte-level reading and rewriting of the path tag in ANLZ analysis files.

An ANLZ file is a 28-byte header followed by a flat run of tags, each carrying
its own length and none referring to another's position. Rewriting the stored
path is therefore a splice: replace the PPTH tag, correct the file length, and
every other byte survives.

That byte preservation is the point. `pyrekordbox`'s `AnlzFile.save()` rebuilds
a file from the tags its parser recognized and silently discards the rest, which
loses `PVB2`, the seek index Rekordbox writes for FLAC tracks.
"""

import struct

#: type, len_header, len_file, then four values this module does not interpret.
_FILE_HEADER = struct.Struct(">4sIIIIII")
#: type, len_header, len_tag. Every tag starts with these, whatever follows.
_TAG_HEADER = struct.Struct(">4sII")
_MAGIC = b"PMAI"
_PATH_TAG = b"PPTH"
#: PPTH holds its path after the tag header and a 4-byte character count.
_PATH_OFFSET = _TAG_HEADER.size + 4
#: The path is stored UTF-16 big-endian with a terminating null character.
_TERMINATOR = b"\x00\x00"


class AnlzFormatError(ValueError):
    """The bytes given are not a well-formed ANLZ file."""


def _walk_tags(data: bytes):
    """Yield `(offset, tag_type, len_tag)` per tag, without reading contents.

    Walking by declared length rather than by parsing means a tag this codebase
    has no structure for is still traversable.
    """
    if len(data) < _FILE_HEADER.size:
        raise AnlzFormatError("shorter than an ANLZ file header")
    magic, len_header = _FILE_HEADER.unpack_from(data, 0)[:2]
    if magic != _MAGIC:
        raise AnlzFormatError(f"expected {_MAGIC!r} magic, found {magic!r}")

    offset = len_header
    while offset + _TAG_HEADER.size <= len(data):
        tag_type, _len_tag_header, len_tag = _TAG_HEADER.unpack_from(data, offset)
        if len_tag <= 0 or offset + len_tag > len(data):
            raise AnlzFormatError(
                f"tag {tag_type!r} at offset {offset} declares length {len_tag}, "
                f"which overruns the {len(data)}-byte file"
            )
        yield offset, tag_type, len_tag
        offset += len_tag


def _find_path_tag(data: bytes) -> tuple[int, int]:
    for offset, tag_type, len_tag in _walk_tags(data):
        if tag_type == _PATH_TAG:
            return offset, len_tag
    raise AnlzFormatError(f"no {_PATH_TAG.decode()} tag in this file")


def _build_path_tag(path: str) -> bytes:
    encoded = path.encode("utf-16-be") + _TERMINATOR
    content = struct.pack(">I", len(encoded)) + encoded
    return (
        _TAG_HEADER.pack(_PATH_TAG, _PATH_OFFSET, _TAG_HEADER.size + len(content))
        + content
    )


def read_path(data: bytes) -> str:
    """The path held in the file's PPTH tag."""
    offset, _len_tag = _find_path_tag(data)
    (len_path,) = struct.unpack_from(">I", data, offset + _TAG_HEADER.size)
    start = offset + _PATH_OFFSET
    return data[start : start + len_path - len(_TERMINATOR)].decode("utf-16-be")


def set_path(data: bytes, path: str) -> bytes:
    """Return `data` with its PPTH tag holding `path`, all other bytes kept."""
    offset, len_tag = _find_path_tag(data)
    spliced = data[:offset] + _build_path_tag(path) + data[offset + len_tag :]

    magic, len_header, _stale_len, *trailing = _FILE_HEADER.unpack_from(spliced, 0)
    header = _FILE_HEADER.pack(magic, len_header, len(spliced), *trailing)
    return header + spliced[_FILE_HEADER.size :]
