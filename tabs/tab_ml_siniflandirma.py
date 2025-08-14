# tabs/tab_ml_siniflandirma.py
import pandas as pd
import streamlit as st
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report
import numpy as np

def tab_ml_siniflandirma(st, conn):
    st.subheader("⚠️ ML ile Revize Gerekir Mi? (Sınıflandırma)")

    df = pd.read_sql_query("SELECT * FROM ucus_planlari", conn, parse_dates=["plan_tarihi"])
    if df.empty:
        st.warning("Veri bulunamadı.")
        return

    df["plan_saat"] = pd.to_timedelta(df["sure"]).dt.total_seconds() / 3600
    df["gerceklesen_sure"] = pd.to_numeric(df["gerceklesen_sure"], errors="coerce")
    df = df.dropna(subset=["ogrenci", "plan_saat", "gerceklesen_sure"])

    # Fark hesapla ve etiketle (1: revize gerekir, 0: gerekmez)
    df["fark"] = df["plan_saat"] - df["gerceklesen_sure"]
    df["revize_gerekir"] = (df["fark"] > 0.2).astype(int)

    df["ogrenci_encoded"] = df["ogrenci"].astype("category").cat.codes
    df["gorev_encoded"] = df["gorev_tipi"].astype("category").cat.codes

    X = df[["ogrenci_encoded", "gorev_encoded", "plan_saat", "gerceklesen_sure"]]
    y = df["revize_gerekir"]

    if len(df) < 5:
        st.warning("Model eğitimi için yeterli veri yok (en az 5 satır önerilir). Lütfen daha fazla veri girin.")
        return

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    model = LogisticRegression()
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    st.markdown(f"### ✅ Doğruluk (Accuracy): `{acc*100:.2f}%`")

    ogrenci_sec = st.selectbox("Öğrenci seçin", df["ogrenci"].unique(), key="sinif_ogrenci")
    gorev_sec = st.selectbox("Görev Tipi seçin", df["gorev_tipi"].unique(), key="sinif_gorev")
    plan_sure = st.number_input("Planlanan süre (saat)", min_value=0.0, step=0.1, key="sinif_plan")
    gercek_sure = st.number_input("Gerçekleşen süre (saat)", min_value=0.0, step=0.1, key="sinif_gercek")

    if st.button("🔍 Revize Gerekir mi?", key="sinif_btn"):
        encoded_ogrenci = df[df["ogrenci"] == ogrenci_sec]["ogrenci_encoded"].iloc[0]
        encoded_gorev = df[df["gorev_tipi"] == gorev_sec]["gorev_encoded"].iloc[0]

        input_data = np.array([[encoded_ogrenci, encoded_gorev, plan_sure, gercek_sure]])
        prediction = model.predict(input_data)[0]

        if prediction == 1:
            st.warning("⚠️ Revize önerisi GEREKİYOR.")
        else:
            st.success("✅ Revize önerisi GEREKMİYOR.")