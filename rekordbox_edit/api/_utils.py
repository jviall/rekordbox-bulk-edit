from pyrekordbox.db6 import DjmdContent

from rekordbox_edit.args import Track


def _track_from_content(content: DjmdContent) -> Track:
    return Track(
        ID=str(content.ID),
        Title=content.Title,
        ArtistName=content.ArtistName,
        AlbumName=content.AlbumName,
        FileNameL=content.FileNameL,
        FolderPath=content.FolderPath,
        FileType=content.FileType,
        SampleRate=content.SampleRate,
        BitDepth=content.BitDepth,
        BitRate=content.BitRate,
    )
