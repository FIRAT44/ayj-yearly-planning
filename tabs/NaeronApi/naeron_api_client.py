# naeron_api_client.py

import requests
import pandas as pd

class NaeronAPIClient:
    def __init__(self, api_base_url, api_key):
        self.base_url = api_base_url
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json"
        }

    def get_flights(self, start_date=None, end_date=None):
        url = f"{self.base_url}/flights"
        params = {}

        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date

        response = requests.get(url, headers=self.headers, params=params)
        if response.status_code == 200:
            return pd.DataFrame(response.json())
        else:
            raise Exception(f"API Hatası: {response.status_code} - {response.text}")

    def get_students(self):
        url = f"{self.base_url}/students"
        response = requests.get(url, headers=self.headers)
        if response.status_code == 200:
            return pd.DataFrame(response.json())
        else:
            raise Exception(f"API Hatası: {response.status_code} - {response.text}")
