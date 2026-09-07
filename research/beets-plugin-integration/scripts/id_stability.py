#!/usr/bin/env python3
"""Do beets item IDs survive a reimport?

Imports files as singletons into a throwaway library, records (id, path),
reimports the same items with `beet import -L`, and re-reads them. The paths
are the control: they must not change, so any ID movement is attributable to
the reimport rather than to files being relocated.
"""

import os
import shutil
import subprocess
import sys
import tempfile

CONFIG = """\
directory: {lib}
library: {db}
import:
  copy: yes
  autotag: no
  quiet: yes
  singletons: yes
paths:
  default: $artist/$title
  singleton: $artist/$title
"""


def listing(env):
    out = subprocess.run(
        ["beet", "ls", "-f", "$id\t$path"], env=env,
        capture_output=True, text=True, check=True,
    ).stdout
    rows = [ln.split("\t", 1) for ln in out.splitlines() if "\t" in ln]
    return {path: int(i) for i, path in rows}


def main(sources):
    root = tempfile.mkdtemp(prefix="beets-ids-")
    try:
        lib, inbox, bd = (os.path.join(root, d) for d in ("lib", "inbox", "bd"))
        for d in (lib, inbox, bd):
            os.makedirs(d)
        for src in sources:
            shutil.copy2(src, inbox)
        with open(os.path.join(bd, "config.yaml"), "w") as fh:
            fh.write(CONFIG.format(lib=lib, db=os.path.join(root, "library.db")))
        env = {**os.environ, "BEETSDIR": bd}

        subprocess.run(["beet", "import", "-q", inbox], env=env,
                       capture_output=True, check=True)
        before = listing(env)
        subprocess.run(["beet", "import", "-q", "-L", "path::."], env=env,
                       capture_output=True, check=True)
        after = listing(env)

        print(f"{'path (basename)':40s} {'id before':>10s} {'id after':>9s}  same?")
        moved = 0
        for path in sorted(before):
            b, a = before[path], after.get(path)
            same = b == a
            moved += not same
            print(f"{os.path.basename(path):40s} {b:>10d} "
                  f"{'gone' if a is None else a:>9} {'yes' if same else 'NO'}")
        print(f"\npaths preserved: {set(before) == set(after)}")
        print(f"ids changed:     {moved} of {len(before)}")
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    if not shutil.which("beet"):
        sys.exit("beet not on PATH")
    main(sys.argv[1:])
