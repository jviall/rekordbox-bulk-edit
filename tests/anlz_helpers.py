"""Assemble ANLZ bytes for tests.

An ANLZ file is a 28-byte PMAI header followed by a flat run of tags. Building
that layout here lets a test place a tag no parser in this codebase understands,
which is the case the path rewrite has to survive.
"""

import struct

FILE_HEADER = struct.Struct(">4sIIIIII")
_TAG_HEADER = struct.Struct(">4sII")


def tag(tag_type: bytes, content: bytes) -> bytes:
    """One tag: type, header length, total length, then content."""
    return (
        _TAG_HEADER.pack(tag_type, _TAG_HEADER.size, _TAG_HEADER.size + len(content))
        + content
    )


def path_tag(path: str) -> bytes:
    """A PPTH tag holding `path`, in Rekordbox's UTF-16 big-endian layout."""
    encoded = path.encode("utf-16-be") + b"\x00\x00"
    content = struct.pack(">I", len(encoded)) + encoded
    return _TAG_HEADER.pack(b"PPTH", 16, _TAG_HEADER.size + len(content)) + content


def anlz(*tags: bytes) -> bytes:
    """A complete ANLZ file wrapping `tags`."""
    body = b"".join(tags)
    return FILE_HEADER.pack(b"PMAI", 28, 28 + len(body), 0, 0, 0, 0) + body


#: Stands in for PVB2, which pyrekordbox has no structure for and drops on a
#: parse-and-rebuild. The contents are recognizable so a test can assert they
#: came through untouched.
UNPARSED_TAG = tag(b"PVB2", b"\xde\xad\xbe\xef" * 8)
