import streamlit as st
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# 1. Google'a kimliğimizi (VIP Kartını) gösteriyoruz
kapsam = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_dict = json.loads(st.secrets["GSPREAD_JSON"])
kimlik = ServiceAccountCredentials.from_json_dict(creds_dict, kapsam)
# ----------------------------------------

client = gspread.authorize(kimlik)

# 2. Google E-Tablo dosyamızı açıyoruz
tablo_linki = "https://docs.google.com/spreadsheets/d/10Cr8YqLpwMXOglQAPz2fP8gSmZR3EkBnpIU-_XSgClM/edit?gid=0#gid=0"
tablo = client.open_by_url(tablo_linki).sheet1

# 3. Tablodaki verileri çekip ekrana yazdırıyoruz
# (Web'de olduğumuz için print yerine st.write kullanmak daha iyidir)
veriler = tablo.get_all_records()
