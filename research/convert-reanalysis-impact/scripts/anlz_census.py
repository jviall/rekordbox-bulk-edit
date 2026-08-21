"""Library-wide ANLZ census (read-only, fast raw-header walk).

Answers:
- Which ANLZ tag types appear, and in how many files (incl. unsupported like PVB2)?
- Are ANLZ cue lists (PCOB/PCO2) ever non-empty on this desktop library?
- Is PVBR ever non-zero? Does PVB2 ever appear, and in which files?
- Does PPTH ever store a real path vs the '?/<name>' device form?
"""

import struct as _struct
from collections import Counter, defaultdict

from pyrekordbox import Rekordbox6Database
from pyrekordbox.db6 import tables

db = Rekordbox6Database()


def walk(path):
    with open(path, "rb") as fh:
        data = fh.read()
    len_header = _struct.unpack(">I", data[4:8])[0]
    len_file = _struct.unpack(">I", data[8:12])[0]
    i = len_header
    tags = []
    while i + 12 <= len_file:
        ttype = data[i:i + 4].decode("ascii", "replace")
        lt = _struct.unpack(">I", data[i + 8:i + 12])[0]
        tags.append((ttype, i, lt, data))
        if lt <= 0:
            break
        i += lt
    return tags, data


def cue_count(data, off, ttype):
    # PCOB content starts at off+12 (after type/len_header/len_tag generic header)
    # PCOB: cue_type(4) unk(2) count(2) ...  -> count at off+12+6
    # PCO2: type(4) count(2) ...             -> count at off+12+4
    if ttype == "PCOB":
        return _struct.unpack(">H", data[off + 18:off + 20])[0]
    if ttype == "PCO2":
        return _struct.unpack(">H", data[off + 16:off + 18])[0]
    return 0


tagtype_files = Counter()      # tag type -> number of files containing it
tagtype_by_ext = defaultdict(Counter)
nonempty_anlz_cue_files = 0
pvb2_examples = []
files_scanned = 0
contents_scanned = 0
contents_missing_anlz = 0
ppth_forms = Counter()

contents = db.get_content().all()
cue_contentids = {c.ContentID for c in db.session.query(tables.DjmdCue).all()}

for c in contents:
    contents_scanned += 1
    try:
        paths = db.get_anlz_paths(c.ID)
    except Exception:
        continue
    any_file = False
    for kind, p in paths.items():
        if not p:
            continue
        try:
            tags, data = walk(p)
        except Exception:
            continue
        any_file = True
        files_scanned += 1
        ext = str(p)[-3:].upper()
        seen = set()
        for ttype, off, lt, _d in tags:
            seen.add(ttype)
            if ttype in ("PCOB", "PCO2"):
                if cue_count(data, off, ttype) > 0:
                    nonempty_anlz_cue_files += 1
            if ttype == "PVB2" and len(pvb2_examples) < 8:
                pvb2_examples.append((c.ID, c.FileType, c.FileNameL, kind, lt))
            if ttype == "PPTH":
                # read path string: content at off+12, len_path int32 then utf-16-be
                lp = _struct.unpack(">I", data[off + 12:off + 16])[0]
                try:
                    s = data[off + 16:off + 16 + lp - 2].decode("utf-16-be", "replace")
                except Exception:
                    s = "<err>"
                ppth_forms["?/..." if s.startswith("?/") else "other"] += 1
        for t in seen:
            tagtype_files[t] += 1
            tagtype_by_ext[ext][t] += 1
    if not any_file:
        contents_missing_anlz += 1

print(f"contents scanned: {contents_scanned}")
print(f"contents with no ANLZ files: {contents_missing_anlz}")
print(f"ANLZ files scanned: {files_scanned}")
print(f"contents that have DjmdCue rows: {len(cue_contentids)}")
print(f"\nANLZ files with a NON-EMPTY PCOB/PCO2 cue list: {nonempty_anlz_cue_files}")
print(f"\nPPTH path forms: {dict(ppth_forms)}")
print(f"\nPVB2 occurrences (first few): {pvb2_examples}")
print("\nTag types -> # files containing (all extensions):")
for t, n in tagtype_files.most_common():
    print(f"   {t}: {n}")
print("\nTag types by extension:")
for ext, cnt in tagtype_by_ext.items():
    print(f"   .{ext}: {dict(cnt)}")

db.close()
