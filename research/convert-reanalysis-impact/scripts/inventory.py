"""Read-only inventory of the fixture playlists."""

from pyrekordbox import Rekordbox6Database
from pyrekordbox.db6 import tables

db = Rekordbox6Database()

playlists = {pl.Name: pl for pl in db.get_playlist()}
targets = ["Compressed", "Lossless Only", "CUE Analysis Playlist"]

for tname in targets:
    pl = playlists.get(tname)
    print(f"\n===== Playlist: {tname} (found={pl is not None}) =====")
    if pl is None:
        continue
    songs = (
        db.session.query(tables.DjmdSongPlaylist)
        .filter_by(PlaylistID=pl.ID)
        .order_by(tables.DjmdSongPlaylist.TrackNo)
        .all()
    )
    for sp in songs:
        c = db.get_content(ID=sp.ContentID)
        print(
            f"  ID={c.ID} type={c.FileType} name={c.FileNameL!r} "
            f"bd={c.BitDepth} sr={c.SampleRate} br={c.BitRate} "
            f"len={c.Length} anlz={c.AnalysisDataPath!r}"
        )

db.close()
