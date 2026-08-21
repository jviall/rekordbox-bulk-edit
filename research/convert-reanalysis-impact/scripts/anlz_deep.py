"""Deep ANLZ inspection: raw tag walk (incl. unsupported tags) + parsed fields."""

import struct as _struct

import numpy as np
from pyrekordbox import Rekordbox6Database

db = Rekordbox6Database()

TARGETS = [
    ("real MP3 w/ cues", 131718786),
    ("real FLAC w/ cues", 80401918),
    ("real AAC/m4a w/ cues", 211711899),
]


def raw_walk(path):
    """Yield (tag_type, len_header, len_tag) for every tag, including ones
    pyrekordbox cannot parse."""
    with open(path, "rb") as fh:
        data = fh.read()
    # File header: type(4) len_header(4) len_file(4) ...
    len_header = _struct.unpack(">I", data[4:8])[0]
    len_file = _struct.unpack(">I", data[8:12])[0]
    i = len_header
    out = []
    while i < len_file:
        ttype = data[i:i + 4].decode("ascii", "replace")
        lh = _struct.unpack(">I", data[i + 4:i + 8])[0]
        lt = _struct.unpack(">I", data[i + 8:i + 12])[0]
        out.append((ttype, lh, lt))
        if lt <= 0:
            break
        i += lt
    return out


for label, cid in TARGETS:
    c = db.get_content(ID=cid)
    dur = c.Length or 0
    print(f"\n########## {label} ID={cid} type={c.FileType} "
          f"name={c.FileNameL!r} len={dur}s ##########")
    paths = db.get_anlz_paths(cid)
    files = db.read_anlz_files(cid)

    for kind, p in paths.items():
        if not p:
            continue
        print(f"\n  === {kind} : ...{str(p).split('USBANLZ')[-1]}")
        print("      raw tags (type, len_header, len_tag):")
        for t, lh, lt in raw_walk(p):
            print(f"        {t}  lh={lh} lt={lt}")

    # Parsed details (pick from whichever file holds them)
    for p, anlz in files.items():
        if "PQTZ" in anlz and anlz.get_tag("PQTZ").count:
            t = anlz.get_tag("PQTZ")
            times = t.get_times()
            print(f"\n  PQTZ beats={t.count} bpm_avg={t.bpms_average:.2f} "
                  f"first={times[0]:.3f}s last={times[-1]:.3f}s")
        for tag in anlz.getall_tags("PCO2"):
            ents = tag.content.entries
            rows = [(e.time, e.loop_time, e.color_id, e.comment) for e in ents]
            print(f"  PCO2 obj_type={tag.content.type} count={len(ents)}")
            for tm, lt, col, com in rows:
                print(f"       time={tm}ms loop_time={lt} color={col} comment={com!r}")
        for tag in anlz.getall_tags("PCOB"):
            ents = tag.content.entries
            if ents:
                rows = [(e.time, e.loop_time) for e in ents]
                print(f"  PCOB cue_type={tag.content.cue_type} count={len(ents)} {rows}")
        if "PVBR" in anlz:
            idx = np.array(anlz.get_tag("PVBR").content.idx, dtype=np.uint64)
            print(f"  PVBR nonzero={int((idx>0).sum())}/400 max={int(idx.max())}")
        if "PWV3" in anlz:
            le = anlz.get_tag("PWV3").content.len_entries
            print(f"  PWV3 len_entries={le}  dur*150={dur*150}  ratio={le/(dur*150):.3f}")
        if "PWV5" in anlz:
            le = anlz.get_tag("PWV5").content.len_entries
            print(f"  PWV5 len_entries={le}  dur*150={dur*150}")
        if "PSSI" in anlz:
            t = anlz.get_tag("PSSI")
            kinds = [e.kind for e in t.content.entries]
            print(f"  PSSI phrases={t.content.len_entries} end_beat={t.content.end_beat} kinds={kinds}")

db.close()
