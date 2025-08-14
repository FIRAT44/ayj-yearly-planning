# tabs/tab_fams_to_naeron.py
import pandas as pd
import streamlit as st
from datetime import datetime, time

def generate_naeron_ucus_no(date_obj, index):
    """NRS-YYYYMMDD-XXX formatında uçuş numarası oluşturur."""
    idx = int(index)
    return f"NRS-{date_obj.strftime('%Y%m%d')}-{idx:03d}"

def tab_fams_to_naeron(st, conn):
    st.subheader("🔄 FAMS → Naeron Format Dönüştürücü")

    uploaded = st.file_uploader(
        "📁 FAMS Veri Dosyasını Yükleyin (CSV veya XLSX)",
        type=["csv", "xlsx"]
    )
    if not uploaded:
        return

    # Dosyayı oku (CSV ise ';' ile ayrılmış)
    try:
        if uploaded.name.lower().endswith(".csv"):
            df = pd.read_csv(uploaded, sep=';', encoding='latin1')
        else:
            df = pd.read_excel(uploaded)
    except Exception as e:
        st.error(f"Dosya okunamadı: {e}")
        return

    # Gereksiz sütunları sil
    cols_to_drop = [
        'SAFETY', 'DAY T.', 'TACH. READING',
        'DUAL', 'DUAL.1', 'SOLO', 'SPIC', 'IR', 'LC'
    ]
    df = df.drop(columns=cols_to_drop, errors='ignore')

    # plan_tarihi tip dönüşümü
    if 'DATE' not in df.columns:
        st.error("Gerekli 'DATE' sütunu bulunamadı.")
        return
    df['plan_tarihi'] = pd.to_datetime(
        df['DATE'], dayfirst=True, errors='coerce'
    ).dt.date
    invalid_dates = df['plan_tarihi'].isnull()
    if invalid_dates.any():
        st.warning(f"{invalid_dates.sum()} satırda geçersiz 'DATE' değeri bulundu; bu satırlar atılıyor.")
        df = df[~invalid_dates]

    # Sıralama
    df = df.sort_values('plan_tarihi')

    # Uçuş numaralarını oluştur
    df['__idx'] = df.groupby('plan_tarihi').cumcount() + 1
    df['__idx'] = df['__idx'].fillna(1).astype(int)
    df['ucus_no'] = df.apply(
        lambda r: generate_naeron_ucus_no(
            datetime.combine(r['plan_tarihi'], time()),
            r['__idx']
        ), axis=1
    )
    df.drop(columns='__idx', inplace=True)

    # Yeni sütun adlarına dönüştürme ve sıralama
    rename_map = {
        'plan_tarihi': 'Uçuş Tarihi 2',
        'REG.':        'Çağrı',
        'OFF BL.':     'Off Bl.',
        'ON BL.':      'On Bl.',
        'BLOCK T.':    'Block Time',
        'FLIGHT T.':   'Flight Time',
        'IP':          'Öğretmen Pilot',
        'SP':          'Öğrenci Pilot',
        'DEPT.':       'Kalkış',
        'DEST.':       'İniş',
        'DUTY':        'Görev',
        'ENGINE':      'Engine'
    }
    df = df.rename(columns=rename_map)

    # Yeni boş IFR Süresi sütunu
    df['IFR Süresi'] = ''

    # Kolonları istenen sıraya göre düzenle
    final_cols = [
        'ucus_no', 'Uçuş Tarihi 2', 'Çağrı', 'Off Bl.', 'On Bl.',
        'Block Time', 'Flight Time', 'Öğretmen Pilot',
        'Öğrenci Pilot',
        'Kalkış', 'İniş', 'Görev', 'Engine', 'IFR Süresi'
    ]
    df = df.loc[:, [c for c in final_cols if c in df.columns]]

    st.markdown("### Naeron Formatına Dönüştürülmüş Veri")
    st.dataframe(df, use_container_width=True)

    # CSV olarak indir
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📥 Naeron Formatlı CSV İndir",
        data=csv,
        file_name="naeron_format.csv",
        mime="text/csv"
    )

    # Excel olarak indir
    import io
    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Sheet1')
    excel_data = excel_buffer.getvalue()
    st.download_button(
        label="📥 Naeron Formatlı Excel İndir",
        data=excel_data,
        file_name="naeron_format.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
        
