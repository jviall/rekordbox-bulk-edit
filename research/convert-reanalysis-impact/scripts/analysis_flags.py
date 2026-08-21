"""Investigate the re-analysis flags and any analysis-lock column (read-only).

Questions:
- What do Analysed / AnalysisUpdated actually contain across the library?
- Is there a 'lock' column, and how is it distributed?
- Does the Analysed value correlate with analysis depth (presence of EXT/2EX)?
"""

from collections import Counter, defaultdict

from pyrekordbox import Rekordbox6Database
from pyrekordbox.db6 import tables

db = Rekordbox6Database()

cols = [c.name for c in tables.DjmdContent.__table__.columns]
print("ALL DjmdContent columns:")
print(cols)

cand = [c for c in cols if any(k in c.lower() for k in (
    "analy", "lock", "status", "quant", "bpm", "beat", "grid", "kind"))]
print("\nCandidate flag / lock / analysis columns:", cand)

contents = db.get_content().all()
print(f"\ntotal contents: {len(contents)}")


def dist(col, max_card=20):
    vals = Counter(getattr(c, col) for c in contents)
    if len(vals) <= max_card:
        print(f"\n{col} distribution ({len(vals)} distinct): {dict(vals.most_common())}")
    else:
        print(f"\n{col}: {len(vals)} distinct values; top: {vals.most_common(8)}")


for col in ["Analysed", "AnalysisUpdated"]:
    dist(col)

for col in cand:
    if col in ("Analysed", "AnalysisUpdated"):
        continue
    try:
        dist(col)
    except Exception as e:
        print(f"{col}: error {e}")

# Cross-tab: does Analysed encode analysis depth (DAT only vs DAT+EXT vs +2EX)?
print("\nCross-tab Analysed value vs ANLZ depth:")
xtab = defaultdict(Counter)
for c in contents:
    try:
        paths = db.get_anlz_paths(c.ID)
    except Exception:
        continue
    have = [k for k in ("DAT", "EXT", "2EX") if paths.get(k)]
    depth = "+".join(have) if have else "none"
    xtab[c.Analysed][depth] += 1
for analysed_val, depths in sorted(xtab.items(), key=lambda kv: str(kv[0])):
    print(f"  Analysed={analysed_val}: {dict(depths)}")

# Show a handful of full rows for the flag columns of interest
print("\nSample rows (ID, FileType, Analysed, AnalysisUpdated):")
for c in contents[:12]:
    print(f"  ID={c.ID} type={c.FileType} Analysed={c.Analysed} "
          f"AnalysisUpdated={c.AnalysisUpdated!r}")

db.close()
