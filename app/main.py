import io
from functools import lru_cache

import folium
import streamlit as st
from geopy.geocoders import Nominatim
from PIL import Image
from streamlit_folium import st_folium

from app import search

st.set_page_config(page_title="Bird Nerd", page_icon="🐦", layout="wide")
st.title("Bird Nerd")

_geolocator = Nominatim(user_agent="bird-nerd/1.0")


@lru_cache(maxsize=256)
def _geocode(location_text: str) -> tuple[float | None, float | None]:
    try:
        loc = _geolocator.geocode(location_text.strip(), timeout=5)
        return (loc.latitude, loc.longitude) if loc else (None, None)
    except Exception:
        return None, None


def _load_thumbnail(path: str, max_size: int = 160) -> Image.Image | None:
    try:
        img = Image.open(path)
        img.thumbnail((max_size, max_size))
        return img
    except Exception:
        return None


def _render_result_cards(results: list[dict]) -> None:
    if not results:
        st.info("No results found.")
        return
    for hit in results:
        with st.container(border=True):
            cols = st.columns([1, 3])
            thumb = _load_thumbnail(hit.get("image_path", ""))
            if thumb:
                cols[0].image(thumb)
            else:
                cols[0].caption("(no image)")
            with cols[1]:
                score = hit.get("_score")
                score_str = f"  ·  similarity {score:.3f}" if score is not None else ""
                st.markdown(
                    f"**{hit.get('species_common', '—')}**"
                    f"  *({hit.get('species_scientific', '')})*{score_str}"
                )
                meta = "  ·  ".join(
                    filter(
                        None,
                        [
                            hit.get("order"),
                            hit.get("family"),
                            hit.get("observed_on"),
                        ],
                    )
                )
                if meta:
                    st.caption(meta)


def _render_map(observations: list[dict]) -> None:
    points = [
        (o["location"]["lat"], o["location"]["lon"], o.get("species_common", ""), o.get("observed_on", ""))
        for o in observations
        if o.get("location")
    ]
    if not points:
        return
    center_lat = sum(p[0] for p in points) / len(points)
    center_lon = sum(p[1] for p in points) / len(points)
    m = folium.Map(location=[center_lat, center_lon], zoom_start=7)
    for lat, lon, name, date in points:
        folium.CircleMarker(
            location=[lat, lon],
            radius=5,
            popup=f"{name}<br>{date}",
            color="#e67e22",
            fill=True,
            fill_opacity=0.7,
        ).add_to(m)
    st_folium(m, width=None, height=420, returned_objects=[])


tab_search, tab_explore = st.tabs(["Visual Search", "Explore by Location"])

# ── Tab 1: Visual Search ────────────────────────────────────────────────────

with tab_search:
    st.subheader("Find birds that look like yours")
    uploaded = st.file_uploader(
        "Upload a bird photo", type=["jpg", "jpeg", "png", "webp"], key="search_upload"
    )

    col1, col2, col3 = st.columns(3)
    location_text = col1.text_input("Location (optional)", placeholder="e.g. Yosemite, CA")
    date_input = col2.date_input("Date observed (optional)", value=None)
    radius_km = col3.slider("Search radius (km)", 10, 1000, 200, key="search_radius")

    if uploaded:
        if "search_image_bytes" not in st.session_state or st.session_state.get("search_upload_name") != uploaded.name:
            st.session_state["search_image_bytes"] = uploaded.read()
            st.session_state["search_upload_name"] = uploaded.name
        st.image(
            Image.open(io.BytesIO(st.session_state["search_image_bytes"])),
            width=240,
            caption="Your photo",
        )

    if st.button("Search", type="primary", disabled=not uploaded):
        image_bytes = st.session_state.get("search_image_bytes")
        if not image_bytes:
            st.error("Please upload an image first.")
        else:
            month = date_input.month if date_input else None
            lat, lon = _geocode(location_text) if location_text.strip() else (None, None)
            if location_text.strip() and lat is None:
                st.warning(f"Could not geocode '{location_text}' — searching without location filter.")

            with st.spinner("Searching…"):
                try:
                    results = search.search_hybrid(
                        image_bytes=image_bytes,
                        lat=lat,
                        lon=lon,
                        radius_km=radius_km if lat is not None else None,
                        month=month,
                    )
                except Exception as exc:
                    st.error(f"Search failed: {exc}")
                    results = []

            st.markdown(f"**{len(results)} result(s)**")
            _render_result_cards(results)

# ── Tab 2: Explore by Location ──────────────────────────────────────────────

with tab_explore:
    st.subheader("Browse observations near a location")

    col1, col2, col3 = st.columns(3)
    explore_location = col1.text_input("Location", placeholder="e.g. Central Park, New York", key="explore_loc")
    explore_month = col2.selectbox(
        "Month (optional)",
        options=[None, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
        format_func=lambda m: "Any" if m is None else [
            "", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
            "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"
        ][m],
        key="explore_month",
    )
    explore_radius = col3.slider("Radius (km)", 10, 500, 100, key="explore_radius")

    if st.button("Explore", type="primary", disabled=not explore_location.strip()):
        lat, lon = _geocode(explore_location)
        if lat is None:
            st.error(f"Could not geocode '{explore_location}'. Try a more specific location.")
        else:
            with st.spinner("Querying observations…"):
                try:
                    observations = search.search_esql(
                        lat=lat,
                        lon=lon,
                        radius_km=explore_radius,
                        month=explore_month,
                    )
                except Exception as exc:
                    st.error(f"Query failed: {exc}")
                    observations = []

            st.markdown(f"**{len(observations)} observation(s)** near {explore_location}")

            if observations:
                _render_map(observations)

                st.divider()
                for obs in observations:
                    thumb = _load_thumbnail(obs.get("image_path", ""))
                    with st.container(border=True):
                        cols = st.columns([1, 3])
                        if thumb:
                            cols[0].image(thumb)
                        else:
                            cols[0].caption("(no image)")
                        with cols[1]:
                            st.markdown(
                                f"**{obs.get('species_common', '—')}**"
                                f"  *({obs.get('species_scientific', '')})*"
                            )
                            meta = "  ·  ".join(
                                filter(None, [obs.get("order"), obs.get("family"), obs.get("observed_on")])
                            )
                            if meta:
                                st.caption(meta)
