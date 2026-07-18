import streamlit as st
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# 1. Google'a kimliğimizi (VIP Kartını) gösteriyoruz
kapsam = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_dict = json.loads(st.secrets["GSPREAD_JSON"])
kimlik = ServiceAccountCredentials.from_json_dict(creds_dict, kapsam)

# 2. İletişim kanalını (client) açıyoruz
client = gspread.authorize(kimlik)

# 3. app.py dosyasının kullanacağı Tablo ID'sini buraya yazıyoruz
TABLO_ID = "10Cr8YqLpwMXOglQAPz2fP8gSmZR3EkBnpIU-_XSgClM"