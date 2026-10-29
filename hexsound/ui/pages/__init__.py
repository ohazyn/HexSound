"""Telas do HexSound. Cada arquivo é uma tela (ou um conjunto de peças de lista); este __init__ mantém
`from hexsound.ui.pages import ...` funcionando como antes."""
from hexsound.ui.pages.common import fmt, h1, gbtn, ROW_ROLE, SORTS
from hexsound.ui.pages.rows import RowDelegate, TrackTable, TrackGrid, RowList, show_track_menu
from hexsound.ui.pages.library import TrackPage
from hexsound.ui.pages.albums import GroupPage, CollectionDetail
from hexsound.ui.pages.search import SearchPage
from hexsound.ui.pages.playlists import PlaylistsPage
from hexsound.ui.pages.import_page import ImportPage
from hexsound.ui.pages.credits import CreditsPage

__all__ = ["TrackPage", "GroupPage", "SearchPage", "PlaylistsPage", "ImportPage", "CreditsPage", "CollectionDetail",
           "RowDelegate", "TrackTable", "TrackGrid", "RowList", "show_track_menu", "ROW_ROLE", "SORTS", "fmt", "h1", "gbtn"]
