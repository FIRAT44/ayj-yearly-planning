#rom tabs.NaeronApi.naeron_api_client import NaeronAPIClient

def naeron_api_use():
    # st.title("📡 NAERON API Kullanımı")
    # st.info("Bu sekme, NAERON API'sinden veri çekmek için kullanılabilir. Aşağıdaki örnek kodu inceleyebilirsiniz.")

    import requests
    import pandas as pd

    # 1. API URL
    url = "https://api.naeron.com:3110/v1/tableNames"

    # 2. API Key yok çünkü bu public ama senin sistemde buraya eklenir:
    headers = {
        "Accept": "application/json",
        "x-api-key":"H4sIAAAAAAAAA1M1MkqszEot0ctLTC3Kz9NLzs9VNTICAL+no2wWAAAA"
        # "Authorization": "Bearer YOUR_API_KEY"  ← gerçek API’de bu olacak
    }

    # 3. GET isteği gönder
    response = requests.get(url, headers=headers)

    # 4. JSON veriyi al
    if response.status_code == 200:
        data = response.json()
        df = pd.DataFrame(data)
        # 5. DataFrame olarak yazdır
        # tüm verileri bir json dosyasına kaydetmek istersen:
        df.to_json("naeron_api_data.json", orient="records", lines=True)
        print("Veri Başarıyla Alındı!")
        print("İlk 5 kayıt:")
        # st.write(df.head())  # Streamlit ile görüntülemek için
        print(df)  # İlk 5 kaydı yazdır
        # st.dataframe(df.head())
        # st.success("API'den veriler başarıyla çekildi. Konsolda çıktıları görebilirsiniz.")
        # st.info("Bu sekme, NAERON API'sinden veri çekmek için kullanılabilir. Aşağıdaki örnek kodu inceleyebilirsiniz.")
        
    else:
        print("Hata:", response)
    
naeron_api_use()
    # # Naeron API ayarları
    # API_BASE_URL = "https://api.naeron.com"       # örnek
    # API_KEY = "senin_gizli_api_keyin"             # API Key burada

    # api = NaeronAPIClient(API_BASE_URL, API_KEY)


    # # 🛬 Uçuş verileri
    # try:
    #     df_ucuslar = api.get_flights(start_date="2024-01-01", end_date="2024-12-31")
    #     print(df_ucuslar.head())
    # except Exception as e:
    #     print("Hata:", e)

    # # 👨‍🎓 Öğrenci verileri
    # try:
    #     df_ogrenciler = api.get_students()
    #     print(df_ogrenciler.head())
    # except Exception as e:
    #     print("Hata:", e)

    # st.success("API'den veriler başarıyla çekildi. Konsolda çıktıları görebilirsiniz.")
    # st.info("Bu sekme, NAERON API'sinden veri çekmek için kullanılabilir. Aşağıdaki örnek kodu inceleyebilirsiniz.")
    