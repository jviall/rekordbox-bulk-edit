#!/usr/bin/env python3
"""Can a plugin-defined field persist in the audio file across containers?

Beets flexible fields live only in the library database. `add_media_field`
(beets/plugins.py:339) instead binds a name to real tag frames, so the value
survives outside the database. This probe stamps a distinct value per file
through a plugin-declared media field, then reads each value straight out of
the file with mediafile alone, proving the value is in the tag and not merely
in the library.

A field that round-trips is a candidate carrier for a rekordbox identifier.
One that does not forces the join back onto the file path.

Usage: media_field_roundtrip.py <audio-file>...
"""

import os
import shutil
import subprocess
import sys
import tempfile

FIELD = "rbe_content_id"

# Declared identically in the plugin and in the reader, so the reader depends
# on the tag rather than on anything beets recorded.
DECLARE = f'''
from mediafile import (
    ASFStorageStyle, MediaField, MediaFile, MP3DescStorageStyle,
    MP4StorageStyle, StorageStyle,
)

FIELD = "{FIELD}"
DESCRIPTOR = MediaField(
    MP3DescStorageStyle(FIELD),
    MP4StorageStyle(f"----:com.apple.iTunes:{{FIELD}}"),
    StorageStyle(FIELD),
    ASFStorageStyle(FIELD),
)
'''

PLUGIN = DECLARE + '''
from beets.plugins import BeetsPlugin


class RbeidPlugin(BeetsPlugin):
    def __init__(self):
        super().__init__()
        self.add_media_field(FIELD, DESCRIPTOR)
'''

READER = DECLARE + '''
import sys

MediaFile.add_field(FIELD, DESCRIPTOR)
print(getattr(MediaFile(sys.argv[1]), FIELD) or "")
'''

CONFIG = """\
directory: {lib}
library: {db}
pluginpath: {plugdir}
plugins: rbeid
import:
  copy: yes
  write: yes
  autotag: no
  quiet: yes
  singletons: yes
paths:
  default: $title
  singleton: $title
"""


def beets_python() -> str:
    """The interpreter beets runs under.

    mediafile is installed alongside beets, which for a pipx or venv install is
    not the interpreter running this script. Reading the shebang of the `beet`
    entry point is the reliable way to find it.
    """
    beet = shutil.which("beet")
    if beet:
        with open(beet, "rb") as fh:
            line = fh.readline()
        if line.startswith(b"#!"):
            candidate = line[2:].strip().decode()
            if os.path.exists(candidate):
                return candidate
    return sys.executable


def main(sources: list[str]) -> int:
    python = beets_python()
    root = tempfile.mkdtemp(prefix="beets-mediafield-")
    try:
        lib, inbox, bd, plugdir = (
            os.path.join(root, d) for d in ("lib", "inbox", "bd", "plugins")
        )
        for d in (lib, inbox, bd, plugdir):
            os.makedirs(d)
        for name, body in (("rbeid.py", PLUGIN), ("read_field.py", READER)):
            with open(os.path.join(plugdir, name), "w") as fh:
                fh.write(body)
        for src in sources:
            shutil.copy2(src, inbox)
        with open(os.path.join(bd, "config.yaml"), "w") as fh:
            fh.write(CONFIG.format(
                lib=lib, db=os.path.join(root, "library.db"), plugdir=plugdir,
            ))
        env = {**os.environ, "BEETSDIR": bd}

        def beet(*args):
            return subprocess.run(["beet", *args], env=env,
                                  capture_output=True, text=True, check=True)

        beet("import", "-q", inbox)
        paths = [p for p in beet("ls", "-f", "$path").stdout.splitlines() if p]

        # `modify` writes tags by default; no separate `write` pass is needed.
        for n, path in enumerate(paths, 1):
            beet("modify", "-y", f"path:{path}", f"{FIELD}=RB{n:04d}")

        reader = os.path.join(plugdir, "read_field.py")
        print(f"{'file':34s} {'written':>8s} {'in file':>8s}  ok?")
        ok_all = True
        for n, path in enumerate(paths, 1):
            got = subprocess.run([python, reader, path],
                                 capture_output=True, text=True).stdout.strip()
            ok = got == f"RB{n:04d}"
            ok_all &= ok
            print(f"{os.path.basename(path):34s} {f'RB{n:04d}':>8s} "
                  f"{got or '(none)':>8s}  {'yes' if ok else 'NO'}")
        print(f"\nread with: {python}")
        print(f"all formats round-tripped: {ok_all}")
        return 0 if ok_all else 1
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    if not shutil.which("beet"):
        sys.exit("beet not on PATH")
    sys.exit(main(sys.argv[1:]))
