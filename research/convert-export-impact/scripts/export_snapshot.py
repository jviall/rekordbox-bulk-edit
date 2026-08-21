"""Whole-drive snapshot of a rekordbox USB export for the convert impact test.

Captures three device stores in one read-only pass: the copied audio under
Contents/ (path, size, mtime, SHA-1), every ANLZ set under PIONEER/USBANLZ/ (raw
tag walk with a SHA-1 per tag, the device PPTH, the beat grid, and the populated
cue lists with positions), and the device databases under PIONEER/rekordbox/ as
opaque blobs (size, mtime, SHA-1). Writes evidence/export-<stage>.json.

    uv run python research/convert-export-impact/scripts/export_snapshot.py <stage> [drive_root]

Stage is a free label, e.g. r1-00-baseline, r1-20-postexport. drive_root
defaults to D:. Neither export.pdb (legacy binary) nor exportLibrary.db
(encrypted Device Library Plus) is parsed; both are watched by hash only. Diff
two stages with export_diff.py.
"""

import hashlib
import json
import shutil
import struct
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from pyrekordbox.anlz import AnlzFile

# Static, machine-independent SQLCipher key for the Device Library Plus store
# (exportLibrary.db). Shared across all Device Libraries; cipher_compatibility 4.
# Source: gist.github.com/0xdevalias/b803476793b56f7c45e6361799168eb0
DBPLUS_KEY = "r8gddnr4k847830ar6cqzbkk0el6qytmb3trbbx805jm74vez64i5o8fnrqryqls"

if len(sys.argv) < 2:
    raise SystemExit("usage: export_snapshot.py <stage> [drive_root]")

stage = sys.argv[1]
drive_root = Path(sys.argv[2] if len(sys.argv) > 2 else "D:/")
out_path = (
    Path(__file__).resolve().parent.parent / "evidence" / f"export-{stage}.json"
)

AUDIO_EXTS = {".flac", ".aiff", ".aif", ".wav", ".mp3", ".m4a", ".aac", ".alac"}
DEVICE_DB_NAMES = [
    "export.pdb", "exportExt.pdb",
    "exportLibrary.db", "exportLibrary.db-wal", "exportLibrary.db-shm",
    "playlists3.sync", "playlists3Plus.sync",
]


def jsafe(v):
    return v if isinstance(v, (int, float, str, type(None))) else str(v)


def sha1_file(path):
    h = hashlib.sha1()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def stat_blob(path):
    """Size, mtime, and SHA-1 of one file, or None if it does not exist."""
    p = Path(path)
    if not p.exists():
        return None
    st = p.stat()
    return {"size": st.st_size, "mtime": int(st.st_mtime), "sha1": sha1_file(p)}


def raw_walk(path):
    """Return (list of per-tag dicts, PPTH string) for an ANLZ file.

    Mirrors subject_snapshot.raw_walk: each tag carries type, offset, lengths,
    and a SHA-1 of its raw bytes, so any content change is detectable unparsed.
    """
    data = Path(path).read_bytes()
    len_header = struct.unpack(">I", data[4:8])[0]
    len_file = struct.unpack(">I", data[8:12])[0]
    i = len_header
    tags = []
    ppth = None
    while i + 12 <= len_file:
        ttype = data[i:i + 4].decode("ascii", "replace")
        lh = struct.unpack(">I", data[i + 4:i + 8])[0]
        lt = struct.unpack(">I", data[i + 8:i + 12])[0]
        if lt <= 0:
            tags.append({"type": ttype, "offset": i, "len_header": lh,
                         "len_tag": lt, "sha1": None})
            break
        body = data[i:i + lt]
        tags.append({"type": ttype, "offset": i, "len_header": lh,
                     "len_tag": lt, "sha1": hashlib.sha1(body).hexdigest()})
        if ttype == "PPTH":
            lp = struct.unpack(">I", data[i + 12:i + 16])[0]
            try:
                ppth = data[i + 16:i + 16 + lp - 2].decode("utf-16-be", "replace")
            except Exception:
                ppth = "<err>"
        i += lt
    return tags, ppth


def parse_grid_and_cues(anlz):
    """Beat-grid summary and device cue lists with positions from a parsed file."""
    out = {}
    try:
        pqtz = anlz.get_tag("PQTZ")
        if pqtz.count:
            times = list(pqtz.get_times())
            out["pqtz"] = {
                "beats": int(pqtz.count),
                "bpm_avg": round(float(pqtz.bpms_average), 3),
                "first_s": round(float(times[0]), 4),
                "last_s": round(float(times[-1]), 4),
            }
    except Exception:
        pass
    cuelists = []
    for tag in anlz.tags:
        name = str(getattr(tag, "name", ""))
        if "cue" not in name.lower():
            continue
        content = getattr(tag, "content", None)
        count = getattr(content, "count", None)
        entries = []
        for e in (getattr(content, "entries", None) or []):
            entries.append({
                "type": jsafe(getattr(e, "type", None)),
                "hot_cue": jsafe(getattr(e, "hot_cue", None)),
                "time": jsafe(getattr(e, "time", None)),
                "loop_time": jsafe(getattr(e, "loop_time", None)),
                "comment": jsafe(getattr(e, "comment", None)),
            })
        cuelists.append({"tag": name, "count": jsafe(count), "entries": entries})
    if cuelists:
        out["cue_lists"] = cuelists
    return out


def read_dbplus(rb_dir):
    """Decrypt exportLibrary.db (Device Library Plus) and read the content, cue,
    and history tables. Keys content by masterContentId (the desktop
    DjmdContent.ID) so it aligns with the desktop fixture snapshots. Returns None
    if the store is absent, or {"error": ...} if it cannot be opened."""
    src = rb_dir / "exportLibrary.db"
    if not src.exists():
        return None
    try:
        from sqlcipher3 import dbapi2 as sq
    except ImportError:
        return {"error": "sqlcipher3 not available"}
    tmp = Path(tempfile.mkdtemp())
    try:
        for suffix in ("", "-wal", "-shm"):
            p = rb_dir / f"exportLibrary.db{suffix}"
            if p.exists():
                shutil.copy2(p, tmp / p.name)
        con = sq.connect(str(tmp / "exportLibrary.db"))
        cur = con.cursor()
        cur.execute(f"PRAGMA key='{DBPLUS_KEY}'")
        cur.execute("PRAGMA cipher_compatibility=4")
        content, dev2master = {}, {}
        for r in cur.execute(
            "select content_id, masterContentId, title, fileName, path, fileType, "
            "djPlayCount, cueUpdateCount, hasModified from content"
        ):
            dev2master[r[0]] = str(r[1])
            content[str(r[1])] = {
                "device_content_id": r[0], "title": r[2], "fileName": r[3],
                "path": r[4], "fileType": r[5], "djPlayCount": r[6],
                "cueUpdateCount": r[7], "hasModified": r[8],
            }
        cues = []
        for r in cur.execute(
            "select cue_id, content_id, kind, inUsec, in150FramePerSec, cueComment from cue"
        ):
            cues.append({
                "master_content_id": dev2master.get(r[1]), "device_content_id": r[1],
                "kind": r[2], "inUsec": r[3], "in150": r[4], "comment": r[5],
            })
        hist = cur.execute("select count(*) from history_content").fetchone()[0]
        con.close()
        return {"content": content, "cues": cues, "history_content_rows": hist}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ── Contents/ audio tree ────────────────────────────────────────────────────
contents_root = drive_root / "Contents"
contents = []
for p in sorted(contents_root.rglob("*")):
    if not p.is_file() or p.suffix.lower() not in AUDIO_EXTS:
        continue
    st = p.stat()
    contents.append({
        "rel": p.relative_to(drive_root).as_posix(),
        "ext": p.suffix.lower(),
        "size": st.st_size,
        "mtime": int(st.st_mtime),
        "sha1": sha1_file(p),
    })

# ── PIONEER/USBANLZ ANLZ sets ───────────────────────────────────────────────
anlz_root = drive_root / "PIONEER" / "USBANLZ"
usbanlz = {}
for p in sorted(anlz_root.rglob("*")):
    if not p.is_file() or p.suffix.upper() not in (".DAT", ".EXT", ".2EX"):
        continue
    folder = p.parent.relative_to(anlz_root).as_posix()
    tags, ppth = raw_walk(p)
    entry = {"file": p.name, "ppth": ppth, "tags": tags}
    try:
        entry.update(parse_grid_and_cues(AnlzFile.parse_file(p)))
    except Exception as e:
        entry["parse_error"] = f"{type(e).__name__}: {e}"
    usbanlz.setdefault(folder, {})[p.suffix.upper().lstrip(".")] = entry

# ── Device databases (opaque blobs) ─────────────────────────────────────────
rb_root = drive_root / "PIONEER" / "rekordbox"
device_dbs = {name: stat_blob(rb_root / name) for name in DEVICE_DB_NAMES}

# Decrypted Device Library Plus content/cue/history (None if the store is absent)
dbplus = read_dbplus(rb_root)

snapshot = {
    "stage": stage,
    "drive_root": drive_root.as_posix(),
    "captured_at": datetime.now().isoformat(timespec="seconds"),
    "contents": contents,
    "usbanlz": usbanlz,
    "device_dbs": device_dbs,
    "dbplus": dbplus,
}

out_path.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8")

n_cues = sum(len(cl.get("entries", []))
             for folder in usbanlz.values()
             for f in folder.values()
             for cl in f.get("cue_lists", []))
print(f"Snapshot written: {out_path.name}")
print(f"  Contents: {len(contents)} audio files")
print(f"  USBANLZ: {len(usbanlz)} track folders, {n_cues} device cue entries")
present = [n for n, v in device_dbs.items() if v]
print(f"  device DBs present: {present}")
if dbplus is None:
    print("  Device Library Plus: (no exportLibrary.db)")
elif "error" in dbplus:
    print(f"  Device Library Plus: unreadable ({dbplus['error']})")
else:
    print(f"  Device Library Plus: {len(dbplus['content'])} content rows, "
          f"{len(dbplus['cues'])} cue rows, "
          f"{dbplus['history_content_rows']} history_content rows")
