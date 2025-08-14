# tab_gerceklesen_kayit.py
import pandas as pd
import streamlit as st
import sqlite3
from datetime import datetime,timedelta
from tabs.plan_naeron_eslestirme_paneli import plan_naeron_eslestirme_ve_elle_duzeltme
import re
import io
from tabs.StudentMatch.matchToNaeronDb import plan_naeron_eslestirme

def tab_gerceklesen_kayit(st, conn):
    st.subheader("🛬 Gerçekleşen Uçuş Süresi Girişi")

    sekme1, sekme2 = st.tabs(["🛬 Gerçekleşen Uçuşlar - 📂 Naeron Kayıtları", "📊 Özet Panel"])

    with sekme1:
        plan_naeron_eslestirme_ve_elle_duzeltme(st)

    with sekme2:
        
        plan_naeron_eslestirme(st, conn)
        