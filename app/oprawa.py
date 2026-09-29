"""Oprawa aplikacji; kolory danych i mapy pozostają w widokach."""

import base64
from pathlib import Path

import streamlit as st

from parkflow.miasta import LODZ, Miasto


LOGA = {"svg": "image/svg+xml", "png": "image/png"}
OPISY_LOG = {"lodz": "Łódź — kreuje"}


def _znak_miasta(miasto: Miasto) -> str:
    """Logo miasta z app/assets/<id>_logo.svg|png; bez pliku — nazwa miasta tekstem."""
    for rozszerzenie, mime in LOGA.items():
        plik = Path(__file__).parent / "assets" / f"{miasto.id}_logo.{rozszerzenie}"
        if plik.exists():
            logo = base64.b64encode(plik.read_bytes()).decode("ascii")
            return (f'<img class="pf-logo-miasta" src="data:{mime};base64,{logo}" '
                    f'alt="{OPISY_LOG.get(miasto.id, miasto.nazwa)}" />')
    return f'<span class="pf-visa" aria-label="{miasto.nazwa}">{miasto.nazwa.upper()}</span>'


def naglowek(miasto: Miasto = LODZ) -> None:
    css = (Path(__file__).parent / "assets" / "oprawa.css").read_text()
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
    st.markdown(
        f"""<header class="pf-hero">
          <div class="pf-intro">
            <span class="pf-eyebrow">MOBILNOŚĆ MIEJSKA · {miasto.nazwa.upper()}</span>
            <h1>ParkFlow<span class="pf-dot">.</span></h1>
            <p>Poziomy priorytetu P1–P4</p>
          </div>
          <div class="pf-brands" aria-label="Visa i {miasto.nazwa}">
            <span class="pf-visa" aria-label="Visa">VISA</span>
            <span class="pf-brand-divider" aria-hidden="true"></span>
            {_znak_miasta(miasto)}
          </div>
        </header>""",
        unsafe_allow_html=True,
    )


def panel_boczny(miasto: Miasto = LODZ) -> None:
    st.markdown(
        f"""<div class="pf-sidebar-brand">ParkFlow<span> / {miasto.nazwa}</span></div>
        <div class="pf-sidebar-label">PARAMETRY ANALIZY</div>""",
        unsafe_allow_html=True,
    )
