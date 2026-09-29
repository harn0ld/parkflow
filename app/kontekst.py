"""Stan współdzielony przez widoki: wynik modelu + wybór użytkownika z paska bocznego."""

from dataclasses import dataclass

import pandas as pd

from app.ustawienia import KODY_UKRYTE
from parkflow.dane import Agregaty

ETYKIETY_SEZONOW = {"lato": "Lato (VI–IX 2025)", "rok_akademicki": "Rok akademicki (X 2025 – VI 2026)"}
ETYKIETY_BLOKOW = {"07-10": "7–10", "10-13": "10–13", "13-16": "13–16", "16-19": "16–19"}

# Kolory poziomów (RGB) — wspólne dla tabeli i przyszłej mapy pydeck.
KOLORY_POZIOMOW = {"P1": (46, 158, 90), "P2": (242, 201, 76), "P3": (242, 133, 48), "P4": (214, 48, 49)}
KOLOR_NEUTRALNY = (140, 140, 150)  # kody wyłączone ze stref (zbiorcze, galerie) na mapie


NAZWY_USLUG = {
    "szybkie_uslugi": "Szybkie usługi",
    "spozywcze_male": "Małe sklepy spożywcze",
    "handel": "Handel",
    "gastronomia": "Gastronomia",
    "uslugi_osobiste": "Usługi osobiste",
    "rozrywka_kultura": "Rozrywka i kultura",
}

# Typ wizyty → grupy MCC (agregaty mają tylko grupy, nie pojedyncze MCC, więc przypisanie jest przybliżone).
# Long dwell (hotele, biura, szpitale) nie ma własnej grupy: szpitale siedzą w usługach osobistych,
# hoteli nie ma w data/mcc_groups.csv.
TYPY_WIZYT = {
    "Quick stop": ("szybkie_uslugi", "spozywcze_male"),
    "Errand": ("handel", "uslugi_osobiste"),
    "Destination": ("gastronomia", "rozrywka_kultura"),
}
WNIOSKI_TYPOW = {
    "Quick stop": "rotacja, postój 15–30 min",
    "Errand": "postój 30–60 min",
    "Destination": "postój 1–3 h",
}
# Curb-sensitive nakłada się na typy powyżej (odbiór, dostawy), więc liczymy go osobno.
CURB_SENSITIVE = ("gastronomia", "spozywcze_male")

def etykieta_spp(v) -> str:
    """Flaga SPP/bufor; pusta, dopóki pipeline nie dostanie data/spp_kody.csv."""
    if v is None or pd.isna(v):
        return "—"
    return "SPP" if bool(v) else "bufor"


@dataclass(frozen=True)
class Kontekst:
    agregaty: Agregaty
    tabela: pd.DataFrame  # parkflow.model.tabela_p(agregaty.strefy)
    sezon: str
    blok: str

    @property
    def komorki(self) -> pd.DataFrame:
        """Wiersze tabeli P dla wybranego sezonu i bloku."""
        t = self.tabela
        return t[(t["sezon"] == self.sezon) & (t["blok"] == self.blok) & ~t["kod"].isin(KODY_UKRYTE)]
