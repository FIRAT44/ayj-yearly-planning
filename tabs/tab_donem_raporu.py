# tabs/tab_donem_raporu.py
import streamlit as st
import sqlite3

# Yeni sekme modüllerini import et
from tabs.donem_raporu.tab_ogrenci_plani import render_ogrenci_plani_tab
from tabs.donem_raporu.tab_donem_ozeti import render_donem_ozeti_tab
from tabs.donem_raporu.tab_grafikler import render_grafikler_tab

def tab_donem_raporu(st, conn: sqlite3.Connection):
    st.subheader("📊 Dönem Raporu")

    # Sekmeleri oluştur
    tab1, tab2, tab3 = st.tabs(["Tek Öğrenci Planı", "Dönem Özeti", "Grafikler"])

    # Her sekme için ilgili render fonksiyonunu çağır
    with tab1:
        render_ogrenci_plani_tab(st, conn)

    with tab2:
        render_donem_ozeti_tab(st, conn)

    with tab3:
        render_grafikler_tab(st, conn)