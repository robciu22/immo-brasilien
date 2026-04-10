"""
Immobiliensuche Brasilien — Streamlit Dashboard
Zeigt Kaufinserate aus Supabase mit Karte, Filtern und Tabelle.
"""

import os
import streamlit as st
import folium
import pandas as pd
from streamlit_folium import st_folium
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(
    page_title="Immobiliensuche Brasilien",
    page_icon="🏠",
    layout="wide",
)

# ── Supabase ──────────────────────────────────────────────────────────────────

@st.cache_resource
def get_supabase():
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])


@st.cache_data(ttl=3600)
def lade_inserate() -> pd.DataFrame:
    client = get_supabase()
    result = client.table("inserate").select("*").execute()
    df = pd.DataFrame(result.data)
    if df.empty:
        return df
    df["preis_brl"] = pd.to_numeric(df["preis_brl"], errors="coerce")
    df["preis_eur"] = pd.to_numeric(df["preis_eur"], errors="coerce")
    df["flaeche_m2"] = pd.to_numeric(df["flaeche_m2"], errors="coerce")
    df["distanz_meer_km"] = pd.to_numeric(df["distanz_meer_km"], errors="coerce")
    df["zimmer"] = pd.to_numeric(df["zimmer"], errors="coerce")
    df["erstmals_gesehen"] = pd.to_datetime(df["erstmals_gesehen"], errors="coerce")
    return df


# ── Sidebar Filter ─────────────────────────────────────────────────────────────

st.sidebar.title("Filter")

df_alle = lade_inserate()

if df_alle.empty:
    st.warning("Keine Daten in der Datenbank. Bitte zuerst den Spider ausführen.")
    st.stop()

# Preis
preis_min, preis_max = st.sidebar.slider(
    "Preis (€)",
    min_value=0,
    max_value=250_000,
    value=(0, 250_000),
    step=5_000,
    format="%d €",
)

# Distanz zum Meer
max_distanz = st.sidebar.slider(
    "Max. Distanz zum Meer (km)",
    min_value=1,
    max_value=100,
    value=30,
)

# Zimmer
min_zimmer = st.sidebar.selectbox("Mindest-Zimmer", [1, 2, 3, 4, 5], index=0)

# Städte
alle_staedte = sorted(df_alle["stadt"].dropna().unique().tolist())
staedte_auswahl = st.sidebar.multiselect(
    "Städte",
    options=alle_staedte,
    default=alle_staedte,
)

# Eigentumsform
eigentumsformen = sorted(df_alle["eigentumsform"].dropna().unique().tolist())
form_auswahl = st.sidebar.multiselect(
    "Eigentumsform",
    options=eigentumsformen,
    default=eigentumsformen,
)

# Condominio
nur_condominio = st.sidebar.checkbox("Nur Condominio-Objekte", value=False)

# ── Daten filtern ──────────────────────────────────────────────────────────────

df = df_alle.copy()
df = df[df["preis_eur"].between(preis_min, preis_max)]
df = df[df["distanz_meer_km"] <= max_distanz]
df = df[df["zimmer"] >= min_zimmer]
if staedte_auswahl:
    df = df[df["stadt"].isin(staedte_auswahl)]
if form_auswahl:
    df = df[df["eigentumsform"].isin(form_auswahl)]
if nur_condominio and "ist_condominio" in df.columns:
    df = df[df["ist_condominio"] == True]

# ── Header ─────────────────────────────────────────────────────────────────────

st.title("🏖️ Immobiliensuche Brasilien")
st.caption(f"Kaufobjekte bis 250.000 € in touristischen Küstenregionen")

col1, col2, col3, col4 = st.columns(4)
col1.metric("Inserate gefunden", len(df))
col2.metric("Ø Preis", f"{df['preis_eur'].mean():,.0f} €" if not df.empty else "–")
col3.metric("Günstigstes", f"{df['preis_eur'].min():,.0f} €" if not df.empty else "–")
col4.metric("Ø Distanz Meer", f"{df['distanz_meer_km'].mean():.1f} km" if not df.empty else "–")

st.divider()

# ── Hilfsfunktionen ───────────────────────────────────────────────────────────

def farbe(preis_eur):
    if preis_eur < 50_000:
        return "green"
    elif preis_eur < 100_000:
        return "orange"
    else:
        return "red"


def baue_karte(daten: pd.DataFrame, zoom: int = 4, center=None, popup_offen_id=None):
    """Baut eine Folium-Karte. Falls popup_offen_id gesetzt, wird dieser Marker hervorgehoben."""
    mittelpunkt = center if center else [-15.0, -45.0]
    karte = folium.Map(location=mittelpunkt, zoom_start=zoom)

    for _, row in daten.dropna(subset=["lat", "lng"]).iterrows():
        popup_text = (
            f"<b>{row['stadt'].title()}</b><br>"
            f"R$ {row['preis_brl']:,.0f} (~{row['preis_eur']:,.0f} €)<br>"
            f"{int(row['zimmer']) if pd.notna(row['zimmer']) else '?'} Zimmer"
            f" | {int(row['flaeche_m2']) if pd.notna(row['flaeche_m2']) else '?'} m²<br>"
            f"🌊 {row['distanz_meer_km']:.1f} km zum Meer<br>"
            f"<a href='{row['url']}' target='_blank'>Inserat öffnen →</a>"
        )
        ist_ausgewaehlt = (popup_offen_id is not None and row.get("id") == popup_offen_id)
        folium.CircleMarker(
            location=[row["lat"], row["lng"]],
            radius=12 if ist_ausgewaehlt else 7,
            color="blue" if ist_ausgewaehlt else farbe(row["preis_eur"]),
            fill=True,
            fill_opacity=0.95 if ist_ausgewaehlt else 0.8,
            popup=folium.Popup(popup_text, max_width=250),
            tooltip=f"R$ {row['preis_brl']:,.0f} | {row['stadt']}",
        ).add_to(karte)

    return karte


# ── Session State für Zeilenauswahl ───────────────────────────────────────────

if "ausgewaehlte_zeile" not in st.session_state:
    st.session_state.ausgewaehlte_zeile = None

# ── Tabelle ────────────────────────────────────────────────────────────────────

st.subheader("📋 Inserate")
st.caption("Zeile anklicken → Karte springt auf das Objekt")

ausgewaehltes_inserat = None

if df.empty:
    st.info("Keine Inserate mit diesen Filtereinstellungen.")
else:
    df_anzeige = df.reset_index(drop=True)

    basis_spalten = ["stadt", "preis_brl", "preis_eur", "zimmer",
                     "flaeche_m2", "distanz_meer_km", "eigentumsform"]
    if "ist_condominio" in df_anzeige.columns:
        basis_spalten.append("ist_condominio")
    basis_spalten += ["nebenkosten_info", "erstmals_gesehen", "url"]

    anzeige = df_anzeige[basis_spalten].copy()

    spalten_namen = ["Stadt", "Preis BRL", "Preis EUR", "Zimmer",
                     "Fläche m²", "Distanz Meer km", "Eigentumsform"]
    if "ist_condominio" in df_anzeige.columns:
        spalten_namen.append("Condominio")
    spalten_namen += ["Nebenkosten", "Erstmals gesehen", "URL"]
    anzeige.columns = spalten_namen

    anzeige["Preis BRL"] = anzeige["Preis BRL"].apply(lambda x: f"R$ {x:,.0f}" if pd.notna(x) else "–")
    anzeige["Preis EUR"] = anzeige["Preis EUR"].apply(lambda x: f"{x:,.0f} €" if pd.notna(x) else "–")
    anzeige["Fläche m²"] = anzeige["Fläche m²"].apply(lambda x: f"{x:.0f}" if pd.notna(x) else "–")
    anzeige["Distanz Meer km"] = anzeige["Distanz Meer km"].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "–")
    anzeige["Stadt"] = anzeige["Stadt"].str.title()

    auswahl = st.dataframe(
        anzeige,
        use_container_width=True,
        column_config={
            "URL": st.column_config.LinkColumn("Link", display_text="Öffnen →")
        },
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
    )

    ausgewaehlte_indices = auswahl.selection.rows
    if ausgewaehlte_indices:
        ausgewaehltes_inserat = df_anzeige.iloc[ausgewaehlte_indices[0]]

st.divider()

# ── Karte ──────────────────────────────────────────────────────────────────────

if ausgewaehltes_inserat is not None and pd.notna(ausgewaehltes_inserat.get("lat")):
    # Detail-Ansicht: Karte zentriert auf ausgewähltes Inserat
    st.subheader(f"📍 {ausgewaehltes_inserat['stadt'].title()} — ausgewähltes Objekt")
    detail_karte = baue_karte(
        df,
        zoom=14,
        center=[ausgewaehltes_inserat["lat"], ausgewaehltes_inserat["lng"]],
        popup_offen_id=ausgewaehltes_inserat.get("id"),
    )
    st_folium(detail_karte, width=None, height=450, returned_objects=[], key="detail_karte")
    if st.button("← Alle Inserate anzeigen"):
        st.session_state.ausgewaehlte_zeile = None
        st.rerun()
else:
    # Übersichtskarte
    st.subheader("📍 Übersichtskarte")
    uebersicht = baue_karte(df)
    st_folium(uebersicht, width=None, height=450, returned_objects=[], key="uebersicht_karte")

st.caption("🟢 < 50k€  🟠 50–100k€  🔴 > 100k€  🔵 Ausgewählt")

# ── Footer ─────────────────────────────────────────────────────────────────────

st.divider()
st.caption(
    f"Daten: VivaReal | Letzte Aktualisierung: "
    f"{df_alle['erstmals_gesehen'].max().strftime('%d.%m.%Y') if not df_alle.empty else '–'}"
)
