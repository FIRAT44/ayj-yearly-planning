import pandas as pd
import streamlit as st

def last_flight_style_factory(today: pd.Timestamp):
    def _style(val):
        t = pd.to_datetime(val, errors="coerce")
        if pd.isna(t) or t > today:
            return ""
        days = (today - t.normalize()).days
        if days >= 15: return "background-color:#ffcccc; color:#000; font-weight:600;"
        if days >= 10: return "background-color:#fff3cd; color:#000;"
        return ""
    return _style

def render_pivot(pivot: pd.DataFrame, today: pd.Timestamp):
    styled = pivot.style.applymap(
        last_flight_style_factory(today),
        subset=pd.IndexSlice[:, ["Son Uçuş Tarihi (Naeron)"]]
    )
    st.dataframe(styled, use_container_width=True)
