import streamlit as st


import requests
import pandas as pd
from datetime import datetime

def dereceyi_pusula_yonune(derece):
    yonler = ['K', 'KD', 'D', 'GD', 'G', 'GB', 'B', 'KB']
    index = round(derece / 45) % 8
    return yonler[index]

def ruzgar_verisi_getir():
    gun_sayisi = 2
    latitude = 41.1025
    longitude = 28.5461

    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": "wind_speed_10m,wind_direction_10m",
        "forecast_days": gun_sayisi,
        "timezone": "auto"
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        df = pd.DataFrame({
            "Zaman": data["hourly"]["time"],
            "Rüzgar Hızı (km/h)": data["hourly"]["wind_speed_10m"],
            "Rüzgar Yönü (°)": data["hourly"]["wind_direction_10m"]
        })

        df["Zaman"] = pd.to_datetime(df["Zaman"])
        df["Pusula Yönü"] = df["Rüzgar Yönü (°)"].apply(dereceyi_pusula_yonune)

        st.success(f"📍 İlk {gun_sayisi} güne ait toplam {len(df)} saatlik rüzgar verisi yüklendi.")
        
        st.subheader("🕒 İlk 48 Saatlik Rüzgar Tahmini")
        st.dataframe(df.head(48), use_container_width=True)

        st.subheader("📈 Rüzgar Hızı (km/h) Grafiği")
        st.line_chart(df.set_index("Zaman")[["Rüzgar Hızı (km/h)"]])

    except requests.exceptions.RequestException as e:
        st.error("⛔ API Hatası: " + str(e))
    except Exception as e:
        st.error("⛔ Genel Hata: " + str(e))


