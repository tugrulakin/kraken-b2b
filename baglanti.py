import gspread
from oauth2client.service_account import ServiceAccountCredentials

# 1. Google'a kimliğimizi (VIP Kartını) gösteriyoruz
kapsam = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
kimlik = ServiceAccountCredentials.from_json_keyfile_name("sifre.json", kapsam)
client = gspread.authorize(kimlik)

# 2. Google E-Tablo dosyamızı açıyoruz
# LÜTFEN DİKKAT: Aşağıdaki tırnak içindeki adresi SİLİN ve 
# kendi Google E-Tablolar dosyanızın tarayıcıdaki tam linkini yapıştırın.
tablo_linki = "https://docs.google.com/spreadsheets/d/10Cr8YqLpwMXOglQAPz2fP8gSmZR3EkBnpIU-_XSgClM/edit?gid=0#gid=0"
tablo = client.open_by_url(tablo_linki).sheet1

# 3. Tablodaki verileri çekip ekrana yazdırıyoruz
veriler = tablo.get_all_records()
print("Bağlantı Başarılı! İşte veri tabanınızdaki ilk ürün:")
print(veriler[0])