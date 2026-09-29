"""Oprawa aplikacji; kolory danych i mapy pozostają w widokach."""

import base64
from pathlib import Path

import streamlit as st


def naglowek() -> None:
    css = (Path(__file__).parent / "assets" / "oprawa.css").read_text()
    logo = base64.b64encode(
        (Path(__file__).parent / "assets" / "lodz_logo.svg").read_bytes()
    ).decode("ascii")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
    st.markdown(
        f"""<header class="pf-hero">
          <div class="pf-intro">
            <span class="pf-eyebrow">MOBILNOŚĆ MIEJSKA · ŁÓDŹ</span>
            <h1>ParkFlow<span class="pf-dot">.</span></h1>
            <p>Poziomy priorytetu P1–P4</p>
          </div>
          <div class="pf-brands" aria-label="Visa i Łódź">
            <span class="pf-visa" aria-label="Visa">VISA</span>
            <span class="pf-brand-divider" aria-hidden="true"></span>
            <img class="pf-lodz" src="data:image/svg+xml;base64,{logo}"
                 alt="Łódź — kreuje" />
          </div>
        </header>""",
        unsafe_allow_html=True,
    )


def panel_boczny() -> None:
    st.markdown(
        """<div class="pf-sidebar-brand">ParkFlow<span> / Łódź</span></div>
        <div class="pf-sidebar-label">PARAMETRY ANALIZY</div>""",
        unsafe_allow_html=True,
    )
