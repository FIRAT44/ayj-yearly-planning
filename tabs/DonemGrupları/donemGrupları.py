import pandas as pd
import streamlit as st
import sqlite3
import random
from collections import Counter
# dosyanın başına ekle:
from tabs.utils.grup_db import ensure_tables, save_periods, save_groups, load_periods, load_groups

ensure_tables()

def tab_donem_ogrenci_gruplama_custom(st, conn: sqlite3.Connection | None = None):
    st.subheader("👥 Dönem → Öğrencileri Gruplandır (Kişi Sayılarını Sen Belirle)")

    # ---------- Yardımcılar ----------
    def extract_name(s: str) -> str:
        s = str(s).strip()
        if " - " in s:
            return s.split(" - ", 1)[1].strip()
        if "-" in s:
            parts = s.split("-")
            if len(parts) >= 2 and any(ch.isalpha() for ch in parts[-1]):
                return parts[-1].strip()
        return s

    def normalize_isim(s: str) -> str:
        return " ".join(str(s).strip().split()).lower()

    def unique_preserve_order(items):
        seen, out = set(), []
        for it in items:
            key = normalize_isim(it)
            if key not in seen:
                seen.add(key)
                out.append(it)
        return out

    def balanced_bucket_sizes(n: int, g: int) -> list[int]:
        if g <= 0:
            return []
        base, rem = divmod(n, g)
        return [base + (1 if i < rem else 0) for i in range(g)]

    # ---------- Veri okuma ----------
    try:
        if conn is None:
            conn = sqlite3.connect("ucus_egitim.db", check_same_thread=False)
        df = pd.read_sql_query("SELECT donem, ogrenci FROM ucus_planlari", conn)
    except Exception as e:
        st.error(f"Veri okunamadı: {e}")
        return

    if df.empty or "donem" not in df.columns or "ogrenci" not in df.columns:
        st.warning("Gerekli alanlar bulunamadı (donem/ogrenci).")
        return

    df = df.dropna(subset=["donem", "ogrenci"]).copy()
    df["donem"] = df["donem"].astype("string").str.strip()
    df["ogrenci"] = df["ogrenci"].astype("string").str.strip()
    df = df[(df["donem"] != "") & (df["ogrenci"] != "")]
    if df.empty:
        st.warning("Geçerli kayıt yok.")
        return

    # ---------- Dönem seçimi + Harici dönemler ----------
    donemler = sorted(df["donem"].unique().tolist())
    donem_sec = st.selectbox("📆 Ana dönem", options=donemler, key="grupc_donem")

    with st.expander("➕ Harici Dönemlerden Öğrenci Ekle (İsteğe Bağlı)", expanded=False):
        harici_ops = [d for d in donemler if d != donem_sec]
        harici_donemler = st.multiselect("Harici dönem(ler)", options=harici_ops, key="grupc_harici_donemler")

        secili_harici_isimler = []
        if harici_donemler:
            df_harici = df[df["donem"].isin(harici_donemler)].copy()
            df_harici["isim"] = df_harici["ogrenci"].apply(extract_name).str.strip()
            tum_harici = sorted(pd.unique(df_harici["isim"]).tolist())
            hepsi = st.checkbox("Harici dönemlerden TÜM öğrencileri ekle", value=True, key="grupc_harici_tumu")
            if hepsi:
                secili_harici_isimler = tum_harici
            else:
                secili_harici_isimler = st.multiselect(
                    "Hariciden eklenecek öğrenciler",
                    options=tum_harici,
                    key="grupc_harici_ms"
                )

    # ---------- Ana dönemin öğrenci isimleri ----------
    df_d = df[df["donem"] == donem_sec].copy()
    df_d["isim"] = df_d["ogrenci"].apply(extract_name).str.strip()

    base_isimler = sorted(pd.unique(df_d["isim"]).tolist())
    isimler_birlesik = unique_preserve_order(base_isimler + list(secili_harici_isimler))
    toplam = len(isimler_birlesik)

    if toplam == 0:
        st.info("Bu dönemde (ve seçili harici dönemlerde) öğrenci yok.")
        return

    st.markdown(f"**Toplam öğrenci (birleşik):** {toplam}  &nbsp;&nbsp; "
                f"🧩 Ana dönem: {len(base_isimler)} | Harici eklenen: {max(0, toplam - len(base_isimler))}")

    # ---------- Grup hedefleri ----------
    with st.form("grupc_hedefler_form", clear_on_submit=False):
        varsayilan_sayi = st.session_state.get("grupc_count") or min(4, toplam)
        grup_sayisi = st.number_input("Kaç grup olacak?", min_value=1, max_value=max(1, toplam),
                                      value=int(varsayilan_sayi), step=1, key="grupc_count_in")

        hedef_mod = st.segmented_control("Hedef belirleme", options=["Dengeli", "Elle"], key="grupc_hedef_mod")

        if hedef_mod == "Dengeli":
            hedefler = balanced_bucket_sizes(toplam, int(grup_sayisi))
            st.caption(f"Dengeli dağılım: {hedefler}")
        else:
            # State veya dengeli öneri
            mevcut = st.session_state.get("grupc_targets")
            if not mevcut or len(mevcut) != int(grup_sayisi):
                mevcut = balanced_bucket_sizes(toplam, int(grup_sayisi))
            hedefler = []
            for i in range(int(grup_sayisi)):
                hedefler.append(st.number_input(
                    f"Grup {i+1} hedef",
                    min_value=0, max_value=toplam,
                    value=int(mevcut[i] if i < len(mevcut) else 0),
                    step=1, key=f"grupc_target_{i}"
                ))

        submitted = st.form_submit_button("🎯 Hedefleri Uygula")
        if submitted:
            # Toplam kontrolü: eşitle
            s = sum(hedefler)
            if s != toplam:
                fark = toplam - s
                hedefler[-1] = max(0, hedefler[-1] + fark)
                st.info(f"Toplam hedef {s} → öğrenci sayısı {toplam}. Son gruba {fark:+d} düzeltme yapıldı.")
            st.session_state["grupc_count"] = int(grup_sayisi)
            st.session_state["grupc_targets"] = hedefler
            st.session_state["grupc_groups"] = [[] for _ in range(int(grup_sayisi))]

    hedefler = st.session_state.get("grupc_targets")
    grup_sayisi = st.session_state.get("grupc_count")
    if not hedefler or not grup_sayisi:
        st.stop()

    # ---------- Otomatik / Manuel atama ----------
    st.markdown("### 🧮 Atama (Otomatik / Manuel)")
    c1, c2, c3, c4 = st.columns([1,1,1,2])

    with c1:
        oto_tur = st.selectbox("Otomatik dağıt", ["A-Z (alfabetik)", "Rastgele"], key="grupc_auto_type")

    with c2:
        if st.button("Öneriyi hazırla", key="grupc_auto_fill"):
            isim_kopya = isimler_birlesik.copy()
            if oto_tur == "Rastgele":
                random.shuffle(isim_kopya)
            # Slicing ile kapasiteye göre doldur
            yeni, start = [], 0
            for h in hedefler:
                yeni.append(isim_kopya[start:start+h])
                start += h
            st.session_state["grupc_groups"] = yeni

    with c3:
        if st.button("🧹 Temizle", key="grupc_clear"):
            st.session_state["grupc_groups"] = [[] for _ in range(grup_sayisi)]

    with c4:
        if st.button("✨ Kalanları Kapasiteye Dağıt", key="grupc_fill_rest"):
            atamalar = st.session_state.get("grupc_groups", [[] for _ in range(grup_sayisi)])
            secilenler = {n for g in atamalar for n in g}
            kalanlar = [n for n in isimler_birlesik if n not in secilenler]
            # Kapasite bazlı round-robin doldurma
            caps = [h - len(g) for h, g in zip(hedefler, atamalar)]
            gi = 0
            for ad in kalanlar:
                while gi < grup_sayisi and caps[gi] <= 0:
                    gi += 1
                if gi >= grup_sayisi:
                    break
                atamalar[gi].append(ad)
                caps[gi] -= 1
            st.session_state["grupc_groups"] = atamalar

    # Manuel düzenleme alanı
    atamalar = st.session_state.get("grupc_groups", [[] for _ in range(grup_sayisi)])
    for i in range(grup_sayisi):
        secili = [s for s in (atamalar[i] if i < len(atamalar) else []) if s in isimler_birlesik]
        sec = st.multiselect(
            f"Grup {i+1} (Hedef {hedefler[i]} kişi) — Atanan {len(secili)}",
            options=isimler_birlesik,
            default=secili,
            key=f"grupc_ms_{i}"
        )
        # fazla ise uyar
        if len(sec) > hedefler[i]:
            st.warning(f"Grup {i+1}: Hedef {hedefler[i]} iken {len(sec)} kişi seçildi.")
        if i < len(atamalar):
            atamalar[i] = sec
        else:
            atamalar.append(sec)
    st.session_state["grupc_groups"] = atamalar

    # ---------- Validasyon & Özet ----------
    tum_secimler = [ad for grup in atamalar for ad in grup]
    sayac = Counter(tum_secimler)
    ciftler = sorted([ad for ad, c in sayac.items() if c > 1])
    eksikler = [n for n in isimler_birlesik if n not in tum_secimler]

    cols = st.columns(3)
    with cols[0]:
        st.success("✅ Tekilleştirme uygun" if not ciftler else "⚠️ Çift atama var")
    with cols[1]:
        st.info(f"🧩 Atanan toplam: {len(tum_secimler)}")
    with cols[2]:
        st.info(f"🧑‍🎓 Kalan (atanmamış): {len(eksikler)}")

    if ciftler:
        st.error("Aynı isim birden fazla grupta: " + ", ".join(ciftler))
    if eksikler:
        with st.expander("Atanmayanları göster"):
            st.write(", ".join(eksikler))

    denge_df = pd.DataFrame({
        "Grup": [f"Grup {i+1}" for i in range(grup_sayisi)],
        "Atanan": [len(g) for g in atamalar],
        "Hedef": hedefler,
        "Fark (Atanan - Hedef)": [len(g) - hedef for g, hedef in zip(atamalar, hedefler)]
    })
    st.markdown("#### ⚖️ Dağılım Özeti")
    st.dataframe(denge_df, use_container_width=True)

    # ---------- Kayıt ----------
    st.markdown("---")
    st.markdown("### 💾 Veritabanı İşlemleri")

    colA, colB, colC = st.columns(3)
    with colA:
        if st.button("📘 Seçili dönemi donem_listesi'ne kaydet"):
            try:
                added = save_periods([donem_sec], kaynak="gruplama_ui")
                st.success(f"'{donem_sec}' kaydedildi (yeni eklenen: {added}).")
            except Exception as e:
                st.error(f"Dönem kaydı hatası: {e}")

    with colB:
        if st.button("📚 Tüm bulunan dönemleri donem_listesi'ne kaydet"):
            try:
                tum_donemler = [d for d in sorted(df['donem'].unique().tolist()) if d]
                added = save_periods(tum_donemler, kaynak="ucus_planlari_distinct")
                st.success(f"{len(tum_donemler)} dönem işlendi (yeni eklenen: {added}).")
            except Exception as e:
                st.error(f"Tüm dönemler kaydı hatası: {e}")

    with colC:
        grup_adlari = [f"Grup {i+1}" for i in range(grup_sayisi)]
        if st.button("🧩 Bu dönemin gruplarını kaydet"):
            try:
                save_groups(
                    donem=donem_sec,
                    hedefler=hedefler,
                    atamalar=atamalar,
                    grup_adlari=grup_adlari,
                    replace_existing_for_donem=True
                )
                st.success(f"'{donem_sec}' için gruplar kaydedildi.")
            except Exception as e:
                st.error(f"Gruplar kaydedilirken hata: {e}")

    st.caption("Dönem listesi: donem_bilgileri.db → donem_listesi | Gruplar: ucus_egitim.db → donem_gruplar & donem_grup_uyeleri")

    # ---------- Önizleme ----------
    with st.expander("📄 Kaydedilenleri Önizle"):
        try:
            grps, members = load_groups(donem_sec)
            if grps:
                st.write("donem_gruplar:", grps)
            if members:
                st.write("donem_grup_uyeleri (ilk 100):", members[:100])
        except Exception as e:
            st.warning(f"Önizleme yapılamadı: {e}")
