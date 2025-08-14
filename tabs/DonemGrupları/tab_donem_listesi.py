# tabs/tab_donem_listesi.py
import streamlit as st
import pandas as pd
import sqlite3

# grup_db yardımcıları
try:
    from tabs.utils.grup_db import ensure_tables, load_periods, load_groups
except Exception:
    # Bu dosya import edilemiyorsa bile ekran en azından donem_listesi'nden okunabilsin
    ensure_tables = None
    load_periods = None
    load_groups = None


def _normalize_periods(p) -> list[str]:
    """
    load_periods() çıktısını (DataFrame | list[tuple] | list[dict] | list[str]) -> list[str] (sadece donem) yapar.
    """
    if p is None:
        return []

    # DataFrame ise
    if isinstance(p, pd.DataFrame):
        if "donem" in p.columns:
            return (
                p["donem"].dropna().astype(str).str.strip().tolist()
            )
        # İlk sütun donem gibi ise
        return p.iloc[:, 0].dropna().astype(str).str.strip().tolist()

    # Liste/tuple/dict karışık gelebilir
    out = []
    if isinstance(p, (list, tuple)):
        for item in p:
            # ('127','gruplama_ui','2025-08-13 ...')
            if isinstance(item, (list, tuple)) and len(item) >= 1:
                out.append(str(item[0]).strip())
            # {'donem': '127', 'kaynak': '...', 'created_at': '...'}
            elif isinstance(item, dict):
                d = str(item.get("donem", "")).strip()
                if d:
                    out.append(d)
            else:
                # Düz string gibi
                s = str(item).strip()
                if s:
                    out.append(s)
        return out

    # Başka tür gelirse string'e çevir
    s = str(p).strip()
    return [s] if s else []


def _fallback_periods_from_db() -> list[str]:
    """load_periods çalışmazsa donem_bilgileri.db → donem_listesi'nden oku."""
    try:
        conn = sqlite3.connect("donem_bilgileri.db")
        df = pd.read_sql_query("SELECT donem FROM donem_listesi", conn)
        conn.close()
        return (
            df["donem"].dropna().astype(str).str.strip().unique().tolist()
            if not df.empty else []
        )
    except Exception:
        return []


def tab_donem_listesi(st):
    st.subheader("🗂️ Kayıtlı Dönemler (grup_db)")

    # Tabloları garanti et (varsa dokunmaz)
    if ensure_tables:
        try:
            ensure_tables()
        except Exception:
            pass

    # 1) Dönemleri oku
    periods = []
    if load_periods:
        try:
            periods = _normalize_periods(load_periods())
        except Exception:
            periods = []
    if not periods:
        periods = _fallback_periods_from_db()

    # Artık hepsi string:
    periods = sorted(set(d for d in periods if d))

    if not periods:
        st.warning("Henüz kayıtlı dönem bulunamadı.")
        return

    # 2) Listeyi göster
    st.markdown("### 📃 Dönem Listesi")
    st.dataframe(pd.DataFrame({"Dönem": periods}), use_container_width=True)

    # 3) Seç ve göster (sadece seçim)
    secilen = st.selectbox("Dönem seç", options=periods, key="dl_secim")
    st.success(f"Seçilen dönem: **{secilen}**")

    # 4) İsteğe bağlı: Bu dönemin grup kayıtlarını önizle
    with st.expander("📎 Bu dönemin gruplarını ve üyelerini göster (opsiyonel)"):
        if load_groups:
            try:
                grps, members = load_groups(secilen)  # beklenen: (gruplar, uyeler)
                if grps:
                    st.markdown("**donem_gruplar**")
                    st.dataframe(pd.DataFrame(grps), use_container_width=True)
                if members:
                    st.markdown("**donem_grup_uyeleri**")
                    st.dataframe(pd.DataFrame(members), use_container_width=True)
                if not grps and not members:
                    st.info("Bu dönem için grup kaydı bulunamadı.")
            except Exception as e:
                st.info(f"Gruplar okunamadı veya tanımlı değil: {e}")
        else:
            st.caption("`load_groups` bulunamadı. Sadece dönem seçimi gösterildi.")
