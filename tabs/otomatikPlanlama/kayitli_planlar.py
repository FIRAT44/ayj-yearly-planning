import streamlit as st
import os
import pickle
import pandas as pd
import datetime

PLAN_PATH = "plan_kayitlari.pkl"

def load_plans():
    if os.path.exists(PLAN_PATH):
        with open(PLAN_PATH, "rb") as f:
            planlar = pickle.load(f)
        return planlar
    else:
        return {}

def save_plans(planlar):
    with open(PLAN_PATH, "wb") as f:
        pickle.dump(planlar, f)

def main():
    st.title("🛫 Kayıtlı Planlar (10’lu Kompakt Kart Paneli)")
    planlar = load_plans()
    if not planlar:
        st.warning("Kayıtlı hiçbir plan bulunamadı.")
        return

    plan_adi_list = list(planlar.keys())
    secili_plan = st.selectbox("📋 Planı seç:", plan_adi_list)
    if not secili_plan:
        return

    plan_df = planlar[secili_plan].reset_index(drop=True)

    # Tema algıla (yazı rengi için)
    theme = st.get_option("theme.base")
    text_color = "#F4F4F4" if theme == "dark" else "#FFF"

    # --- Filtreleme
    st.markdown("### 🔎 Filtreleme")
    colf1, colf2, colf3 = st.columns(3)
    with colf1:
        filtre_ogr = st.text_input("Öğrenci adı ara:", "")
    with colf2:
        filtre_gorev = st.text_input("Görev ara:", "")
    with colf3:
        min_tarih = pd.to_datetime(plan_df["Tarih"]).min().date()
        max_tarih = pd.to_datetime(plan_df["Tarih"]).max().date()
        tarih_aralik = st.date_input("Tarih aralığı:", value=[min_tarih, max_tarih])

    filtered_df = plan_df.copy()
    if filtre_ogr:
        filtered_df = filtered_df[filtered_df["Öğrenci"].str.contains(filtre_ogr, case=False, na=False)]
    if filtre_gorev:
        filtered_df = filtered_df[filtered_df["Görev"].str.contains(filtre_gorev, case=False, na=False)]
    if tarih_aralik and len(tarih_aralik) == 2:
        filtered_df = filtered_df[
            (pd.to_datetime(filtered_df["Tarih"]) >= pd.to_datetime(tarih_aralik[0])) &
            (pd.to_datetime(filtered_df["Tarih"]) <= pd.to_datetime(tarih_aralik[1]))
        ]

    st.markdown("### 📋 Planlar (10’lu Kompakt Kart)")

    # --- Küçük Kartlar + 10’lu Gösterim
    n_cols = 7
    cards_per_page = 14
    total_cards = len(filtered_df)
    max_page = max(1, int((total_cards-1)/cards_per_page)+1)
    page = st.number_input("Sayfa", min_value=1, max_value=max_page, step=1)
    start = (page-1)*cards_per_page
    end = min(start+cards_per_page, total_cards)

    for idx in range(start, end, n_cols):
        cols = st.columns(n_cols)
        for j in range(n_cols):
            if idx + j < end:
                row = filtered_df.iloc[idx + j]
                with cols[j]:
                    st.markdown(
                        f"""
                        <div style='
                            background: linear-gradient(140deg, #2040800D 0%, #2563EB22 100%);
                            border: 1.3px solid #2563EB22;
                            border-radius:11px;
                            box-shadow:0 1px 4px #20408022;
                            padding:10px 8px 10px 10px;
                            margin-bottom:8px;
                            min-width:120px;
                            font-size:12.7px;
                            color:{text_color};
                            transition: box-shadow 0.2s;
                            '>
                            <span style='font-size:16px;vertical-align:-3px;margin-right:5px;'>🛫</span>
                            <b>Öğrenci:</b> {row.get("Öğrenci","")}<br>
                            <b>Görev:</b> {row.get("Görev","")}<br>
                            <b>Eğitmen:</b> {row.get("Eğitmen","")}<br>
                            <b>Uçak:</b> {row.get("Uçak","")}<br>
                            <b>Tarih:</b> {row.get("Tarih","")}<br>
                            <b>Öncelikli:</b> <span style='color:#1e40af;font-weight:600'>{row.get("Öncelikli","-")}</span>
                        </div>
                        """, unsafe_allow_html=True
                    )
                    edit_col, del_col = st.columns([1, 1])
                    if edit_col.button("✏️", key=f"edit_{idx+j}"):
                        st.session_state["edit_row"] = idx + j
                    if del_col.button("🗑️", key=f"del_{idx+j}"):
                        plan_df = plan_df.drop(plan_df.index[idx + j])
                        planlar[secili_plan] = plan_df.reset_index(drop=True)
                        save_plans(planlar)
                        st.rerun()

    # --- DÜZENLEME MODALI ---
    edit_idx = st.session_state.get("edit_row", None)
    if edit_idx is not None and edit_idx < len(filtered_df):
        row = filtered_df.iloc[edit_idx]
        with st.modal("Kartı Düzenle"):
            yeni_ogrenci = st.text_input("Öğrenci", value=row.get("Öğrenci",""))
            yeni_gorev = st.text_input("Görev", value=row.get("Görev",""))
            yeni_egitmen = st.text_input("Eğitmen", value=row.get("Eğitmen",""))
            yeni_ucak = st.text_input("Uçak", value=row.get("Uçak",""))
            yeni_tarih = st.date_input("Tarih", value=pd.to_datetime(row.get("Tarih")).date())
            yeni_oncelikli = st.selectbox("Öncelikli", options=["Evet", "Hayır"], index=0 if row.get("Öncelikli","")=="Evet" else 1)
            kaydet = st.button("Kaydet ve Kapat")
            if kaydet:
                idx_real = plan_df.index[(plan_df["Öğrenci"] == row["Öğrenci"]) & (plan_df["Tarih"] == row["Tarih"]) & (plan_df["Görev"] == row["Görev"])]
                if len(idx_real) > 0:
                    idx_real = idx_real[0]
                    plan_df.at[idx_real, "Öğrenci"] = yeni_ogrenci
                    plan_df.at[idx_real, "Görev"] = yeni_gorev
                    plan_df.at[idx_real, "Eğitmen"] = yeni_egitmen
                    plan_df.at[idx_real, "Uçak"] = yeni_ucak
                    plan_df.at[idx_real, "Tarih"] = str(yeni_tarih)
                    plan_df.at[idx_real, "Öncelikli"] = yeni_oncelikli
                    planlar[secili_plan] = plan_df
                    save_plans(planlar)
                if "edit_row" in st.session_state:
                    del st.session_state["edit_row"]
                st.rerun()

    # --- Yeni Görev Ekleme
    with st.expander("➕ Yeni Görev Ekle"):
        with st.form("add_row_form"):
            yeni_ogrenci = st.text_input("Öğrenci")
            yeni_gorev = st.text_input("Görev")
            yeni_egitmen = st.text_input("Eğitmen")
            yeni_ucak = st.text_input("Uçak")
            yeni_tarih = st.date_input("Tarih", value=datetime.date.today())
            yeni_oncelikli = st.selectbox("Öncelikli", options=["Evet", "Hayır"])
            ekle = st.form_submit_button("Ekle")
        if ekle and yeni_ogrenci and yeni_gorev:
            new_row = {
                "Öğrenci": yeni_ogrenci,
                "Görev": yeni_gorev,
                "Eğitmen": yeni_egitmen,
                "Uçak": yeni_ucak,
                "Tarih": str(yeni_tarih),
                "Öncelikli": yeni_oncelikli
            }
            plan_df = pd.concat([plan_df, pd.DataFrame([new_row])], ignore_index=True)
            planlar[secili_plan] = plan_df
            save_plans(planlar)
            st.success("Yeni görev eklendi.")
            st.rerun()

    st.caption("Her sayfada 10 küçük kart görünür, düzenleyebilir, silebilir, ekleyebilirsin. Sayfa ile gezebilirsin.")
