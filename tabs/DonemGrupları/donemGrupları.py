import pandas as pd
import streamlit as st
import sqlite3
import random
from collections import Counter
# dosyanın başına ekle:
from tabs.utils.grup_db import ensure_tables, save_periods, save_groups, load_periods, load_groups

# fonksiyonun içinde, en başlarda bir yerde:
ensure_tables()
def tab_donem_ogrenci_gruplama_custom(st, conn: sqlite3.Connection | None = None):
    st.subheader("👥 Dönem → Öğrencileri Gruplandır (Kişi Sayılarını Sen Belirle)")

    # --- Yardımcılar ---
    def extract_name(s: str) -> str:
        s = str(s).strip()
        if " - " in s:
            return s.split(" - ", 1)[1].strip()
        if "-" in s:
            parts = s.split("-")
            if len(parts) >= 2 and any(ch.isalpha() for ch in parts[-1]):
                return parts[-1].strip()
        return s

    def balanced_bucket_sizes(n: int, g: int) -> list[int]:
        if g <= 0:
            return []
        base = n // g
        rem = n % g
        return [base + 1 if i < rem else base for i in range(g)]

    # --- Veri okuma (hafif, gerekirse cache eklenebilir) ---
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
    if df.empty:
        st.warning("Kayıt bulunamadı.")
        return

    df = df.dropna(subset=["donem", "ogrenci"]).copy()
    df["donem"]   = df["donem"].astype("string").str.strip()
    df["ogrenci"] = df["ogrenci"].astype("string").str.strip()
    df = df[(df["donem"].str.len() > 0) & (df["ogrenci"].str.len() > 0)]
    df = df[(df["donem"] != "") & (df["ogrenci"] != "")]
    if df.empty:
        st.warning("Geçerli kayıt yok.")
        return

    # --- Dönem seçimi ---
    donemler = sorted(df["donem"].unique().tolist())
    donem_sec = st.selectbox("Dönem seç", options=donemler, key="grupc_donem")

    # Dönem değişince state sıfırlama (tek sefer)
    if st.session_state.get("grupc_donem_aktif") != donem_sec:
        st.session_state["grupc_donem_aktif"] = donem_sec
        st.session_state["grupc_targets"] = None
        st.session_state["grupc_groups"] = None
        st.session_state["grupc_count"] = None

    # --- İsim listesi (unique) ---
    df_d = df[df["donem"] == donem_sec].copy()
    df_d["isim"] = df_d["ogrenci"].apply(extract_name)
    isimler = sorted(pd.unique(df_d["isim"].str.strip()).tolist())
    toplam = len(isimler)

    if toplam == 0:
        st.info("Bu dönemde öğrenci yok.")
        return

    st.markdown(f"**Toplam öğrenci:** {toplam}")

    # --- Kilit / yeniden hesap kontrolü ---
    kilit = st.toggle("🔒 Hesaplamayı kilitle (değişiklikler otomatik uygulanmasın)", value=False, key="grupc_lock")

    # --- Grup tasarımı: form ile UYGULA'ya basılınca güncellensin ---
    with st.form("grupc_tasarim_form", clear_on_submit=False):
        varsayilan_sayi = min(4, toplam) if st.session_state.get("grupc_count") is None else st.session_state["grupc_count"]
        grup_sayisi = st.number_input("Kaç grup olacak?", min_value=1, max_value=max(1, toplam), value=varsayilan_sayi, step=1)

        # Varsayılan hedefler: önce state, yoksa dengeli
        mevcut_targets = st.session_state.get("grupc_targets")
        if not mevcut_targets or len(mevcut_targets) != int(grup_sayisi):
            mevcut_targets = balanced_bucket_sizes(toplam, int(grup_sayisi))

        st.caption("Her grup için kişi sayılarını gir. Toplamın, toplam öğrenci sayısına eşit olması tavsiye edilir.")
        hedefler = []
        for i in range(int(grup_sayisi)):
            hedef = st.number_input(
                f"Grup {i+1} kişi sayısı",
                min_value=0,
                max_value=toplam,
                value=int(mevcut_targets[i] if i < len(mevcut_targets) else 0),
                step=1,
                key=f"grupc_target_{i}"
            )
            hedefler.append(int(hedef))

        submitted = st.form_submit_button("🎯 Hedefleri Uygula")
        if submitted:
            st.session_state["grupc_count"] = int(grup_sayisi)
            # Toplam hedef kontrolü
            s = sum(hedefler)
            if s != toplam:
                # Kullanıcıya dokunmadan otomatik düzeltme: kalan/fazlayı son gruba yedir
                fark = toplam - s
                hedefler[-1] = max(0, hedefler[-1] + fark)
                st.info(f"Toplam hedef ({s}) öğrenci sayısına ({toplam}) eşit değildi. Son grupta otomatik {fark:+d} düzeltme yapıldı.")
            st.session_state["grupc_targets"] = hedefler
            # Hedefler uygulandı, mevcut atamaları temizleyelim ki yeni hedefe göre yapılabilsin
            st.session_state["grupc_groups"] = [[] for _ in range(int(grup_sayisi))]

    # Güncel hedefler ve grup sayısı
    hedefler = st.session_state.get("grupc_targets")
    grup_sayisi = st.session_state.get("grupc_count")

    if not hedefler or not grup_sayisi:
        st.stop()

    # --- Hedef özet tablo ---
    hedef_df = pd.DataFrame({"Grup": [f"Grup {i+1}" for i in range(grup_sayisi)], "Hedef": hedefler})
    st.markdown("### 🎯 Hedef Kişi Sayıları")
    st.dataframe(hedef_df, use_container_width=True)

    st.markdown("---")
    st.markdown("### 🧮 Atama (Otomatik/Manuel)")
    c1, c2, c3 = st.columns([1,1,2])

    with c1:
        oto_tur = st.selectbox("Otomatik dağıt", ["A-Z (alfabetik)", "Rastgele"], key="grupc_auto_type")

    with c2:
        if st.button("Öneriyi hazırla", key="grupc_auto_fill", disabled=kilit):
            isim_kopya = isimler.copy()
            if oto_tur == "Rastgele":
                random.shuffle(isim_kopya)  # her basışta yeni karışım
            # A-Z zaten sıralı geliyor
            yeni = []
            start = 0
            for h in hedefler:
                yeni.append(isim_kopya[start:start + h])
                start += h
            st.session_state["grupc_groups"] = yeni

    with c3:
        if st.button("🧹 Tüm atamaları temizle", key="grupc_clear", disabled=kilit):
            st.session_state["grupc_groups"] = [[] for _ in range(grup_sayisi)]

    # --- Manuel atama alanı (kilitliyken değişiklik önermiyoruz ama görüntülenir) ---
    atamalar = st.session_state.get("grupc_groups", [[] for _ in range(grup_sayisi)])
    for i in range(grup_sayisi):
        secili = atamalar[i] if i < len(atamalar) else []
        secili = [s for s in secili if s in isimler]  # temizlik
        sec = st.multiselect(
            f"Grup {i+1} (Hedef {hedefler[i]} kişi)",
            options=isimler,
            default=secili,
            key=f"grupc_ms_{i}",
            disabled=kilit
        )
        # Hedef üstüne çıkarsa uyarı (kısıtlamıyoruz, sadece uyarıyoruz)
        if len(sec) > hedefler[i]:
            st.warning(f"Grup {i+1}: Hedef {hedefler[i]} iken {len(sec)} kişi seçildi.")
        # State'e yaz
        if i < len(atamalar):
            atamalar[i] = sec
        else:
            atamalar.append(sec)

        st.caption(f"Atanan: {len(sec)} / Hedef: {hedefler[i]}")

    st.session_state["grupc_groups"] = atamalar

    # --- Validasyon & Özet ---
    tum_secimler = [ad for grup in atamalar for ad in grup]
    sayac = Counter(tum_secimler)
    ciftler = sorted([ad for ad, c in sayac.items() if c > 1])
    eksikler = sorted(list(set(isimler) - set(tum_secimler)))

    if ciftler:
        st.error(f"⚠️ Aynı isim birden fazla grupta: {', '.join(ciftler)}")
    else:
        st.success("✅ Tekilleştirme: Aynı isim birden fazla grupta yok.")

    if eksikler:
        st.warning(f"🧩 Gruplara atanmayan {len(eksikler)} kişi var.")
        with st.expander("Eksikleri göster"):
            st.write(", ".join(eksikler))
    else:
        st.info("🟢 Tüm öğrenciler bir gruba atanmış görünüyor.")

    denge_df = pd.DataFrame({
        "Grup": [f"Grup {i+1}" for i in range(grup_sayisi)],
        "Atanan": [len(g) for g in atamalar],
        "Hedef": hedefler,
        "Fark (Atanan - Hedef)": [len(g) - hedef for g, hedef in zip(atamalar, hedefler)]
    })
    st.markdown("#### ⚖️ Dağılım Özeti")
    st.dataframe(denge_df, use_container_width=True)


    st.markdown("---")
    st.markdown("### 💾 Veritabanına Kaydet")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("📘 Seçili dönemi donem_listesi'ne kaydet"):
            try:
                added = save_periods([donem_sec], kaynak="gruplama_ui")
                st.success(f"'{donem_sec}' dönemi kaydedildi (yeni eklenen: {added}).")
            except Exception as e:
                st.error(f"Dönem kaydedilirken hata: {e}")

    with c2:
        if st.button("📚 Tüm bulunan dönemleri donem_listesi'ne kaydet"):
            try:
                tum_donemler = sorted(df["donem"].astype("string").str.strip().unique().tolist())
                tum_donemler = [d for d in tum_donemler if d]
                added = save_periods(tum_donemler, kaynak="ucus_planlari_distinct")
                st.success(f"{len(tum_donemler)} dönem işlendi (yeni eklenen: {added}).")
            except Exception as e:
                st.error(f"Tüm dönemler kaydedilirken hata: {e}")

    st.caption("Dönem listesi: donem_bilgileri.db → donem_listesi")

    # --- Grupları kaydet ---
    grup_adlari = [f"Grup {i+1}" for i in range(grup_sayisi)]  # istersen düzenleme alanı da ekleyebilirsin

    if st.button("🧩 Bu dönemin gruplarını kaydet"):
        try:
            save_groups(
                donem=donem_sec,
                hedefler=hedefler,
                atamalar=atamalar,
                grup_adlari=grup_adlari,
                replace_existing_for_donem=True
            )
            st.success(f"'{donem_sec}' dönemi için gruplar kaydedildi.")
        except Exception as e:
            st.error(f"Gruplar kaydedilirken hata: {e}")

    st.caption("Gruplar: ucus_egitim.db → donem_gruplar & donem_grup_uyeleri")

    # (Opsiyonel) Kaydedileni hızlıca göster
    with st.expander("📄 Kaydedilenleri önizle"):
        try:
            grps, members = load_groups(donem_sec)
            if grps:
                st.write("donem_gruplar:", grps)
            if members:
                st.write("donem_grup_uyeleri (ilk 100):", members[:100])
        except Exception as e:
            st.warning(f"Önizleme yapılamadı: {e}")
