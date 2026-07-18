import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import time
import json
import baglanti

# ==========================================
# 💎 ZIRHLI MATEMATİK VE FORMATLAMA MOTORU
# ==========================================
def to_float(val):
    """Google Sheets'ten gelen her türlü metin/sayı karmaşasını saf sayıya çevirir."""
    if isinstance(val, (int, float)):
        return float(val)
    if not val or pd.isna(val):
        return 0.0
        
    # TL, Boşluk ve Sembolleri temizle
    val = str(val).strip().replace(" TL", "").replace("₺", "").replace(" ", "")
    if not val:
        return 0.0
        
    # Hem virgül hem nokta varsa (Örn: 1.250,50 veya 1,250.50)
    if "," in val and "." in val:
        last_comma = val.rfind(",")
        last_dot = val.rfind(".")
        if last_comma > last_dot: # Virgül ondalık (TR Format)
            val = val.replace(".", "").replace(",", ".")
        else: # Nokta ondalık (US Format)
            val = val.replace(",", "")
    elif "," in val:
        # Sadece virgül varsa TR formatında ondalıktır (Örn: 1250,50)
        val = val.replace(",", ".")
    elif "." in val:
        # Sadece nokta varsa. Acaba binlik ayracı mı (1.500) yoksa ondalık mı (1500.50)?
        parts = val.split(".")
        if len(parts) == 2 and len(parts[1]) == 3:
            # Noktadan sonra tam 3 rakam varsa bu binlik ayracıdır (1.500 -> 1500)
            val = val.replace(".", "")
        elif len(parts) > 2:
            # Birden fazla nokta varsa kesin binlik ayracıdır (1.250.000)
            val = val.replace(".", "")
            
    try:
        res = float(val)
        return 0.0 if pd.isna(res) else res
    except:
        return 0.0

def format_tl(deger):
    """Saf sayıları şık Türk Lirası formatına çevirir."""
    try:
        float_deger = to_float(deger)
        usd_format = f"{float_deger:,.2f}"
        tr_format = usd_format.replace(",", "X").replace(".", ",").replace("X", ".")
        return f"{tr_format} TL"
    except:
        return str(deger)
    
def st_zırhlı_detay_goster(detay_df):
    """Hem Admin hem Müşteri panellerinde standart detay ve dip toplam gösterir."""
    # Hesaplamalar
    ara_toplam_ham = detay_df["Miktar"] * detay_df["Gizli_Birim_Fiyat"]
    # Kdv sütununu kontrol et (bazen Kdv, bazen KDV Oranı olarak gelebilir)
    kdv_oran = detay_df["Kdv"] if "Kdv" in detay_df.columns else detay_df["KDV Oranı"]
    kdv_tutari_ham = ara_toplam_ham * (kdv_oran / 100)
    kdvli_toplam_ham = ara_toplam_ham + kdv_tutari_ham
    
    # Gösterilecek tabloyu hazırla
    gosterilecek_liste = detay_df.copy()
    gosterilecek_liste["Birim Fiyatı"] = detay_df["Gizli_Birim_Fiyat"].apply(format_tl)
    gosterilecek_liste["Ara Toplam"] = ara_toplam_ham.apply(format_tl)
    gosterilecek_liste["KDV'li Toplam"] = kdvli_toplam_ham.apply(format_tl)
    
    # Sütunları düzenle ve göster
    kolonlar = ["Kategori", "Alt Kategori", "Miktar", "Ürün Adı", "Açıklama", "Birim Fiyatı", "Kdv", "Ara Toplam", "KDV'li Toplam"]
    st.dataframe(gosterilecek_liste[kolonlar], use_container_width=True, hide_index=True)
    
    # Dip toplam metrikleri
    c1, c2, c3 = st.columns(3)
    c1.metric("Ara Toplam", format_tl(ara_toplam_ham.sum()))
    c2.metric("Toplam KDV", format_tl(kdv_tutari_ham.sum()))
    c3.metric("Genel Toplam", format_tl(kdvli_toplam_ham.sum()))
# ------------------------    

# Hatalı Kütüphane Formatını Ezip Ham Veri Çeken Özel Fonksiyon
@st.cache_data(ttl=300) # 🌟 VERİLERİ 5 DAKİKA HAFIZAYA ALIR (429 Hatasını Önler)
def get_records_cached(_sheet, sheet_title):
    raw = _sheet.get_all_values()
    if len(raw) > 1:
        headers = raw[0]
        num_cols = len(headers)
        records = []
        for row in raw[1:]:
            # Satır kısa kaldıysa boşlukla tamamla
            padded_row = row + [""] * (num_cols - len(row))
            records.append(dict(zip(headers, padded_row)))
        return records
    return []

def get_records_raw(sheet):
    # Eski kodlarının hiçbirini değiştirmene gerek kalmaması için köprü görevi görür
    return get_records_cached(sheet, sheet.title)

# Sayfa ayarları
st.set_page_config(
    page_title="Kraken B2B", 
    layout="wide",
    initial_sidebar_state="expanded" 
)

# ==========================================
# 🧠 OTURUM VE HAFIZA YÖNETİMİ
# ==========================================
if "giris_yapildi" not in st.session_state:
    st.session_state.giris_yapildi = False
if "liste_onaylandi" not in st.session_state:
    st.session_state.liste_onaylandi = False
if "editor_key" not in st.session_state:
    st.session_state.editor_key = 0

def yat_degisti():
    st.session_state.liste_onaylandi = False
    st.session_state.editor_key += 1

# ==========================================
# 🔌 GOOGLE SHEETS BAĞLANTI ALTYAPISI
# ==========================================
client = baglanti.client
TABLO_ID = baglanti.TABLO_ID

# ⚠️ BURAYA GOOGLE SHEETS ID'NİZİ YAPIŞTIRIN
TABLO_ID = "10Cr8YqLpwMXOglQAPz2fP8gSmZR3EkBnpIU-_XSgClM"

# ==========================================
# 🔑 1. AŞAMA: KULLANICI GİRİŞ EKRANI
# ==========================================
if not st.session_state.giris_yapildi:
    st.title("⚓ Kraken B2B - Giriş")
    st.write("Lütfen devam etmek için kullanıcı bilgilerinizi giriniz.")
    
    kullanici_adi = st.text_input("Kullanıcı Adı").strip()
    sifre = st.text_input("Şifre", type="password").strip()
    
    if st.button("Giriş Yap", use_container_width=True):
        with st.spinner("Sistem yetkileriniz kontrol ediliyor, lütfen bekleyin..."):
            try:
                kullanici_tablosu = client.open_by_key(TABLO_ID).worksheet("Kullanıcılar")
                kullanicilar_df = pd.DataFrame(get_records_raw(kullanici_tablosu))
                
                kontrol = kullanicilar_df[
                    (kullanicilar_df["Kullanıcı_Adı"].astype(str) == kullanici_adi) & 
                    (kullanicilar_df["Şifre"].astype(str) == sifre)
                ]
                
                if not kontrol.empty:
                    st.session_state.giris_yapildi = True
                    st.session_state.rol = kontrol.iloc[0]["Rol"]
                    st.session_state.kullanici_adi = kontrol.iloc[0]["Kullanıcı_Adı"]
                    
                    # Gercek_İsim sütununu kontrol edip hafızaya alıyoruz
                    if "Gercek_İsim" in kontrol.columns:
                        st.session_state.gercek_isim = str(kontrol.iloc[0]["Gercek_İsim"])
                    else:
                        st.session_state.gercek_isim = st.session_state.kullanici_adi
                        
                    st.success("Giriş başarılı! Yönlendiriliyorsunuz...")
                    time.sleep(1) 
                    st.rerun()
                else:
                    st.error("Kullanıcı adı veya şifre hatalı! Lütfen tekrar deneyin.")
            except Exception as e:
                st.error(f"Veritabanı bağlantı hatası: {e}")
    st.stop()

# ==========================================
# ⚓ 2. AŞAMA: ANA UYGULAMA VE VERİ ÇEKME
# ==========================================
try:
    dosya = client.open_by_key(TABLO_ID)
    tablo_urunler = dosya.sheet1
    tablo_yatlar = dosya.worksheet("Yatlar")
    
    try:
        tablo_siparisler = dosya.worksheet("Siparisler")
    except:
        st.error("Google Sheets dosyanızda 'Siparisler' adında bir sekme bulunamadı! Lütfen oluşturun.")
        st.stop()
        
    ham_veriler = get_records_raw(tablo_urunler)
    orijinal_df = pd.DataFrame(ham_veriler) if ham_veriler else pd.DataFrame()
    
    yat_verileri = get_records_raw(tablo_yatlar)
    yatlar_df = pd.DataFrame(yat_verileri) if yat_verileri else pd.DataFrame(columns=["Acente_Kullanici_adi", "Yat_Adi"])
    
    siparis_verileri = get_records_raw(tablo_siparisler)
    siparisler_df = pd.DataFrame(siparis_verileri) if siparis_verileri else pd.DataFrame(columns=[
        "Siparis_ID", "Tarih", "Hesap_Sahibi", "Yat_Adi", "Siparis_Detayi", "Toplam_Tutar", "Durum"
    ])
except Exception as e:
    st.error(f"Veri yüklenirken hata oluştu: {e}")
    st.stop()

# MATEMATİK ZIRHI UYGULANIYOR
orijinal_df = orijinal_df.rename(columns={
    "Urun_ID": "Ürün Kodu", "Kategori": "Kategori", "Alt_Kategori": "Alt Kategori",
    "Urun_Adi": "Ürün Adı", "Aciklama": "Açıklama", "Birim_Fiyat": "Gizli_Birim_Fiyat",
    "Kdv": "KDV Oranı"
})
if not orijinal_df.empty:
    orijinal_df["Gizli_Birim_Fiyat"] = orijinal_df["Gizli_Birim_Fiyat"].apply(to_float)
    orijinal_df["KDV Oranı"] = orijinal_df["KDV Oranı"].apply(to_float)

# ==========================================
# 🚪 3. AŞAMA: SOL MENÜ
# ==========================================
st.sidebar.markdown("### 👤 Oturum Bilgileri")
# Sol menüyü de kişiselleştirilmiş isme göre güncelliyoruz
st.sidebar.write(f"**Kullanıcı:** {st.session_state.gercek_isim}")
st.sidebar.write(f"**Yetki Sınıfı:** {st.session_state.rol}")
st.sidebar.info("Bu paneli sol üst köşedeki çarpı (X) veya ok (>) işaretinden kapatabilirsiniz.")
st.sidebar.markdown("---")

# ==========================================
# 🛥️ 4. AŞAMA: ANA EKRAN KİMLİK BİLGİSİ VE ÇIKIŞ
# ==========================================
st.title("⚓ Kraken B2B")

ust_kolon1, ust_kolon2 = st.columns([8, 2]) 
with ust_kolon1:
    # Anahtar ikonu kalıyor, rol ve oturum sahibi ifadeleri kalkıyor
    st.markdown(f"##### 🔑 {st.session_state.gercek_isim}")
with ust_kolon2:
    if st.button("🚪 Çıkış Yap", use_container_width=True):
        st.session_state.giris_yapildi = False
        st.session_state.liste_onaylandi = False
        st.rerun()

st.markdown("---")

# ==========================================
# 🗂️ 5. AŞAMA: SEKMELİ NAVİGASYON (TABS)
# ==========================================

# ==========================================
# 👑 YÖNETİM (ADMIN) PANELİ
# ==========================================
# Güvenli rol kontrolü: Eğer rol Admin ise bu blok çalışır
if st.session_state.get("rol") == "Admin":
    st.title("👑 Yönetim Paneli")
    
    # 3 Ana Sekmeyi Oluşturuyoruz
    admin_sekme1, admin_sekme2, admin_sekme3 = st.tabs([
        "📦 Sipariş Yönetimi", 
        "🏷️ Ürün & Fiyatlar", 
        "👥 Kullanıcı İşlemleri"
    ])
    
    # --- 1. SEKME: SİPARİŞ YÖNETİMİ ---
    with admin_sekme1:
        siparis_alt_sekme1, siparis_alt_sekme2 = st.tabs(["📥 Onay Bekleyenler", "✅ Onaylanmış Siparişler"])
        
        with siparis_alt_sekme1:
            bekleyenler = siparisler_df[siparisler_df["Durum"] == "Gonderis"].copy()
            if bekleyenler.empty:
                st.info("Şu an onay bekleyen bir sipariş bulunmuyor.")
            else:
                bekleyenler["Toplam Tutar"] = bekleyenler["Toplam_Tutar"].apply(format_tl)
                
                st.write("### 📥 Onay Bekleyen Siparişler")
                event = st.dataframe(
                    bekleyenler[["Siparis_ID", "Yat_Adi", "Hesap_Sahibi", "Toplam Tutar"]], 
                    use_container_width=True,
                    selection_mode="single-row",
                    on_select="rerun"
                )

                if event.selection.rows:
                    secili_index = event.selection.rows[0]
                    secili_satir = bekleyenler.iloc[secili_index]
                    
                    st.divider()
                    st.markdown(f"#### 📄 Sipariş No: `{secili_satir['Siparis_ID']}` | 🛥️ Yat: `{secili_satir['Yat_Adi']}` | 👤 Acente: `{secili_satir['Hesap_Sahibi']}`")
                    
                    try:
                        detay_dict = json.loads(secili_satir["Siparis_Detayi"])
                        detay_df = pd.DataFrame(detay_dict)
                        
                        kdv_kolonlari = [col for col in detay_df.columns if 'kdv' in col.lower()]
                        if kdv_kolonlari:
                            detay_df.rename(columns={kdv_kolonlari[0]: "Kdv"}, inplace=True)
                        else:
                            detay_df["Kdv"] = 0.0
                            
                        detay_df["Miktar"] = pd.to_numeric(detay_df["Miktar"], errors="coerce").fillna(0).astype(int)
                        detay_df["Gizli_Birim_Fiyat"] = detay_df["Gizli_Birim_Fiyat"].apply(to_float)
                        detay_df["Kdv"] = pd.to_numeric(detay_df["Kdv"].astype(str).str.replace(',', '.'), errors="coerce").fillna(0).astype(int)
                        
                        ara_toplam_ham = detay_df["Miktar"] * detay_df["Gizli_Birim_Fiyat"]
                        kdv_tutari = ara_toplam_ham * (detay_df["Kdv"] / 100)
                        kdvli_toplam_ham = ara_toplam_ham + kdv_tutari
                        
                        gosterilecek_liste = detay_df.copy()
                        gosterilecek_liste["Kdv"] = detay_df["Kdv"].astype(int)
                        gosterilecek_liste["Birim Fiyatı"] = detay_df["Gizli_Birim_Fiyat"].apply(format_tl)
                        gosterilecek_liste["Ara Toplam"] = ara_toplam_ham.apply(format_tl)
                        gosterilecek_liste["KDV'li Toplam"] = kdvli_toplam_ham.apply(format_tl)
                        
                        gosterilecek_liste = gosterilecek_liste[["Kategori", "Alt Kategori", "Miktar", "Ürün Adı", "Açıklama", "Birim Fiyatı", "Kdv", "Ara Toplam", "KDV'li Toplam"]]
                        
                        toplam_satiri = pd.DataFrame([{
                            "Kategori": "", "Alt Kategori": "", "Miktar": "", "Ürün Adı": "➡️ GENEL TOPLAM", 
                            "Açıklama": "", "Birim Fiyatı": "", "Kdv": "", 
                            "Ara Toplam": format_tl(ara_toplam_ham.sum()), 
                            "KDV'li Toplam": format_tl(kdvli_toplam_ham.sum())
                        }])
                        gosterilecek_liste = pd.concat([gosterilecek_liste, toplam_satiri], ignore_index=True)
                        
                        st.dataframe(gosterilecek_liste, hide_index=True, use_container_width=True)
                        
                        islem_col1, islem_col2 = st.columns(2)
                        with islem_col1:
                            if st.button("✅ Siparişi Onayla", type="primary", use_container_width=True):
                                raw_sip = tablo_siparisler.get_all_values()
                                headers = raw_sip[0]
                                durum_col_idx = headers.index("Durum") + 1
                                for idx, row_val in enumerate(raw_sip[1:]):
                                    if row_val[headers.index("Siparis_ID")] == secili_satir["Siparis_ID"]:
                                        tablo_siparisler.update_cell(idx + 2, durum_col_idx, "Bitmis")

                                        # --- PDF OLUŞTURMA VE MAIL GÖNDERME BLOĞU ---
                                        def siparisi_pdf_yap_ve_mail_at(siparis_id, detay_df, mail_adresi):
                                            from fpdf import FPDF
                                            import smtplib
                                            from email.mime.multipart import MIMEMultipart
                                            from email.mime.text import MIMEText
                                            from email.mime.application import MIMEApplication

                                            # 1. PDF'i Hazırla
                                            pdf = FPDF()
                                            pdf.add_page()
                                            pdf.set_font("Arial", 'B', 16)
                                            pdf.cell(200, 10, txt=f"Kraken B2B - Siparis: {siparis_id}", ln=True, align='C')
                                            # ... (Burada detay_df'i kullanarak PDF tablosunu oluşturuyoruz) ...
    
                                            pdf_yolu = f"siparis_{siparis_id}.pdf"
                                            pdf.output(pdf_yolu)
    
                                            # 2. Mail Gönder
                                            msg = MIMEMultipart()
                                            msg['Subject'] = f"Yeni Onayli Siparis: {siparis_id}"
                                            msg.attach(MIMEText(f"Siparisiniz onaylandi. Ekli dosyada detaylari bulabilirsiniz."))
    
                                            with open(pdf_yolu, "rb") as f:
                                                part = MIMEApplication(f.read(), Name=pdf_yolu)
                                            part['Content-Disposition'] = f'attachment; filename="{pdf_yolu}"'
                                            msg.attach(part)
        
                                            # (Burada SMTP server ayarlarınla maili yolluyoruz)
                                        # ---------------------------------------------

                                        st.success(f"{secili_satir['Siparis_ID']} numaralı sipariş başarıyla onaylandı!")
                                        st.session_state.editor_key += 1
                                        time.sleep(1.5)
                                        st.rerun()
                        with islem_col2:
                            if st.button("❌ Siparişi İptal Et", type="secondary", use_container_width=True):
                                raw_sip = tablo_siparisler.get_all_values()
                                headers = raw_sip[0]
                                durum_col_idx = headers.index("Durum") + 1
                                for idx, row_val in enumerate(raw_sip[1:]):
                                    if row_val[headers.index("Siparis_ID")] == secili_satir["Siparis_ID"]:
                                        tablo_siparisler.update_cell(idx + 2, durum_col_idx, "Iptal_Edilmis")
                                        st.warning(f"{secili_satir['Siparis_ID']} numaralı sipariş iptal edildi!")
                                        st.session_state.editor_key += 1
                                        time.sleep(1.5)
                                        st.rerun()
                    except Exception as e:
                        st.error(f"Sipariş detayı okunamadı: {e}")
                        
                        islem_col1, islem_col2 = st.columns(2)
                        with islem_col1:
                            if st.button("✅ Teslim Edildi (Bitir)", type="primary", use_container_width=True):
                                try:
                                    raw_sip = tablo_siparisler.get_all_values()
                                    headers = raw_sip[0]
                                    durum_col_idx = headers.index("Durum") + 1
                                    for idx, row_val in enumerate(raw_sip[1:]):
                                        if row_val[headers.index("Siparis_ID")] == admin_secilen_id:
                                            tablo_siparisler.update_cell(idx + 2, durum_col_idx, "Bitmis")
                                            st.success(f"{admin_secilen_id} numaralı sipariş başarıyla 'Teslim Edildi' olarak işaretlendi!")
                                            st.session_state.editor_key += 1
                                            time.sleep(1.5)
                                            st.rerun()
                                except Exception as e:
                                    st.error(f"Hata oluştu: {e}")
                                    
                        with islem_col2:
                            if st.button("❌ Siparişi Sil (İptal Et)", type="secondary", use_container_width=True):
                                try:
                                    raw_sip = tablo_siparisler.get_all_values()
                                    headers = raw_sip[0]
                                    for idx, row_val in enumerate(raw_sip[1:]):
                                        if row_val[headers.index("Siparis_ID")] == secili_satir["Siparis_ID"]:
                                            tablo_siparisler.delete_rows(idx + 2) # Satırı tamamen siliyoruz
                                            st.warning(f"{secili_satir['Siparis_ID']} numaralı sipariş veritabanından tamamen silindi!")
                                            st.session_state.editor_key += 1
                                            time.sleep(1.5)
                                            st.rerun()
                                except Exception as e:
                                    st.error(f"Hata oluştu: {e}")
                    except Exception as e:
                        st.error(f"Sipariş detayı okunamadı: {e}")
        
        with siparis_alt_sekme2:
            gecmis_df = siparisler_df[siparisler_df["Durum"] == "Bitmis"].copy()
            if gecmis_df.empty:
                st.info("Henüz onaylanmış sipariş bulunmuyor.")
            else:
                gecmis_df["Toplam Tutar"] = gecmis_df["Toplam_Tutar"].apply(format_tl)
                gecmis_df["Durum_Metni"] = "✅ Onaylandı"
                st.dataframe(
                    gecmis_df[["Siparis_ID", "Tarih", "Hesap_Sahibi", "Yat_Adi", "Durum_Metni", "Toplam Tutar"]].sort_values(by="Tarih", ascending=False), 
                    hide_index=True, 
                    use_container_width=True
                )

    # --- 2. SEKME: ÜRÜN & FİYATLAR ---
    with admin_sekme2:
        st.subheader("🏷️ Ürün ve Fiyat Yönetimi")
        
        urun_verileri = get_records_raw(tablo_urunler)
        if not urun_verileri:
            st.warning("Google Sheets'te ürün bulunamadı veya tablo boş.")
        else:
            urun_df = pd.DataFrame(urun_verileri)
            
            st.info("💡 **Nasıl Kullanılır?** \n* Fiyat, KDV veya isim değiştirmek için hücrelerin içine tıklayıp yazın.\n* Yeni ürün eklemek için tablonun en altındaki boş satıra tıklayın.\n* Bir ürünü silmek için satırın en solundaki gri kutucuğu seçip klavyenizden 'Delete' (veya Backspace) tuşuna basın.")
            
            # Tabloyu ve butonu FORM içine alıyoruz (Puslanmayı önler)
            with st.form("urun_duzenleme_formu"):
                duzenlenen_urun_df = st.data_editor(
                    urun_df,
                    key=f"urun_editor_{st.session_state.editor_key}",
                    use_container_width=True,
                    num_rows="dynamic",
                    hide_index=True
                )
                
                kaydet_butonu = st.form_submit_button("💾 Tüm Değişiklikleri Kaydet", type="primary", use_container_width=True)
                
            if kaydet_butonu:
                with st.spinner("Google Sheets güncelleniyor, lütfen bekleyin..."):
                    try:
                        temiz_df = duzenlenen_urun_df.fillna("")
                        yeni_veri = [temiz_df.columns.tolist()] + temiz_df.values.tolist()
                        
                        tablo_urunler.clear()
                        try:
                            tablo_urunler.update("A1", yeni_veri)
                        except:
                            try:
                                tablo_urunler.update(yeni_veri)
                            except:
                                tablo_urunler.update(values=yeni_veri, range_name="A1")
                                
                        st.success("✅ Ürünler ve fiyatlar başarıyla kaydedildi!")
                        st.session_state.editor_key += 1
                        time.sleep(2)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Güncelleme sırasında hata oluştu: {e}")

    # --- 3. SEKME: KULLANICI İŞLEMLERİ ---
    with admin_sekme3:
        st.subheader("👥 Kullanıcı İşlemleri")
        
        try:
            kullanici_tablosu_admin = client.open_by_key(TABLO_ID).worksheet("Kullanıcılar")
            kullanici_verileri = get_records_raw(kullanici_tablosu_admin)
            
            if not kullanici_verileri:
                st.warning("Google Sheets'te kullanıcı bulunamadı.")
            else:
                kullanici_df = pd.DataFrame(kullanici_verileri)
                
                st.info("💡 **Nasıl Kullanılır?** \n* Şifre, İsim veya Rol (Admin/Acente) değiştirmek için hücrelere tıklayıp yazın.\n* Yeni kullanıcı eklemek için tablonun en altındaki boş satıra tıklayın.\n* Bir kullanıcıyı silmek için en soldaki kutucuğu seçip klavyenizden 'Delete' tuşuna basın.")
                
                # Tabloyu ve butonu FORM içine alıyoruz (Puslanmayı önler)
                with st.form("kullanici_duzenleme_formu"):
                    duzenlenen_kullanici_df = st.data_editor(
                        kullanici_df,
                        key=f"kullanici_editor_{st.session_state.editor_key}",
                        use_container_width=True,
                        num_rows="dynamic",
                        hide_index=True
                    )
                    
                    kullanici_kaydet_butonu = st.form_submit_button("💾 Kullanıcıları Kaydet", type="primary", use_container_width=True)
                    
                if kullanici_kaydet_butonu:
                    with st.spinner("Kullanıcı listesi güncelleniyor..."):
                        try:
                            temiz_kullanici_df = duzenlenen_kullanici_df.fillna("")
                            yeni_kullanici_veri = [temiz_kullanici_df.columns.tolist()] + temiz_kullanici_df.values.tolist()
                            
                            kullanici_tablosu_admin.clear()
                            try:
                                kullanici_tablosu_admin.update("A1", yeni_kullanici_veri)
                            except:
                                try:
                                    kullanici_tablosu_admin.update(yeni_kullanici_veri)
                                except:
                                    kullanici_tablosu_admin.update(values=yeni_kullanici_veri, range_name="A1")
                                
                            st.success("✅ Kullanıcı bilgileri başarıyla güncellendi!")
                            st.session_state.editor_key += 1
                            time.sleep(2)
                            st.rerun()
                        except Exception as e:
                            st.error(f"Güncelleme sırasında hata oluştu: {e}")
        except Exception as e:
            st.error(f"Kullanıcı verileri çekilirken bir hata oluştu: {e}")

    st.stop() # Normal müşteri ekranlarının Admin'e görünmesini engeller!

ana_sekme1, ana_sekme2 = st.tabs(["🆕 Yeni Sipariş Oluştur", "📋 Siparişlerim"])

# ------------------------------------------
# TAB 1: YENİ SİPARİŞ OLUŞTUR
# ------------------------------------------
with ana_sekme1:
    if st.session_state.rol == "Acente":
        
        with st.expander("🛥️ Yat Yönetimi (Ekle / Sil)", expanded=True):
            y_col1, y_col2 = st.columns(2)
            
            with y_col1:
                st.write("**Yeni Yat Tanımla**")
                yeni_yat_adi = st.text_input("Sisteme eklenecek yeni yatın adı:", key="yeni_yat_adi_input")
                if st.button("Yatı Kaydet", type="primary"):
                    if yeni_yat_adi:
                        try:
                            tablo_yatlar.append_row([st.session_state.kullanici_adi, yeni_yat_adi])
                            st.session_state.gecici_bildirim = yeni_yat_adi
                            yat_degisti()
                            st.rerun()
                        except Exception as e:
                            st.error(f"Kayıt hatası: {e}")
                    else:
                        st.warning("Lütfen bir yat adı giriniz.")
            
            with y_col2:
                st.write("**Yat Listesinden Çıkar**")
                acente_yatlari_silme = yatlar_df[yatlar_df["Acente_Kullanici_adi"] == st.session_state.kullanici_adi]["Yat_Adi"].tolist()
                if acente_yatlari_silme:
                    silinecek_yat = st.selectbox("Listeden silmek istediğiniz yatı seçin:", acente_yatlari_silme)
                    if st.button("🗑️ Seçili Yatı Sil", type="secondary"):
                        try:
                            tum_yatlar_satirlar = tablo_yatlar.get_all_values()
                            for idx, satir in enumerate(tum_yatlar_satirlar):
                                if satir[0] == st.session_state.kullanici_adi and satir[1] == silinecek_yat:
                                    tablo_yatlar.delete_rows(idx + 1)
                                    st.session_state.gecici_silme_bildirim = silinecek_yat
                                    yat_degisti()
                                    st.rerun()
                        except Exception as e:
                            st.error(f"Silme işlemi başarısız: {e}")
                else:
                    st.info("Listenizde silinebilecek bir yat bulunmuyor.")
                        
        if "gecici_bildirim" in st.session_state:
            st.markdown(f"""
                <div class="odak-bildirim">✅ {st.session_state.gecici_bildirim} listenize eklendi!</div>
                <style>
                .odak-bildirim {{ background-color: #d1e7dd; color: #0f5132; border: 1px solid #badbcc; padding: 14px; border-radius: 6px; margin-top: 15px; margin-bottom: 10px; font-weight: bold; font-size: 15px; animation: gozukYokOl 4s forwards; }}
                @keyframes gozukYokOl {{ 0% {{ opacity: 1; max-height: 100px; }} 75% {{ opacity: 1; max-height: 100px; }} 100% {{ opacity: 0; max-height: 0px; padding: 0; margin: 0; border: none; overflow: hidden; }} }}
                </style>
            """, unsafe_allow_html=True)
            del st.session_state.gecici_bildirim
            
        if "gecici_silme_bildirim" in st.session_state:
            st.markdown(f"""
                <div class="odak-bildirim-silme">🗑️ {st.session_state.gecici_silme_bildirim} listenizden silindi!</div>
                <style>
                .odak-bildirim-silme {{ background-color: #f8d7da; color: #842029; border: 1px solid #f5c2c7; padding: 14px; border-radius: 6px; margin-top: 15px; margin-bottom: 10px; font-weight: bold; font-size: 15px; animation: gozukYokOl 4s forwards; }}
                </style>
            """, unsafe_allow_html=True)
            del st.session_state.gecici_silme_bildirim
                        
        st.markdown("<br>", unsafe_allow_html=True) 

        acente_yatlari = yatlar_df[yatlar_df["Acente_Kullanici_adi"] == st.session_state.kullanici_adi]["Yat_Adi"].tolist()
        
        if not acente_yatlari:
            st.error("🚨 Sisteme kayıtlı yatınız bulunmuyor. Siparişe başlamak için lütfen yukarıdaki formdan ilk yatınızı ekleyin.")
        else:
            st.write("### 🛥️ Yat Listeniz")
            st.session_state.secilen_yat = st.selectbox(
                "Yat Listeniz Seçim Kutusu",
                acente_yatlari,
                on_change=yat_degisti,
                label_visibility="collapsed"
            )
            st.markdown("---")
    else:
        st.session_state.secilen_yat = "Kendi Hesabı"

    if st.session_state.rol == "Acente" and not acente_yatlari:
        st.stop()

    st.markdown("""<style>div.stButton > button:first-child { background-color: #8B0000; color: white; }</style>""", unsafe_allow_html=True)
    st.write("### 🔍 Listeden Seçmeyi Kolaylaştırın")
    filtre_kolon1, filtre_kolon2, filtre_kolon3 = st.columns(3)
    with filtre_kolon1:
        arama_kelimesi = st.text_input("Ürün Adı veya Açıklama Ara:", "").upper()
    with filtre_kolon2:
        tum_kategoriler = ["Tümü"] + list(orijinal_df["Kategori"].dropna().unique())
        secilen_kategori = st.selectbox("Kategori Seçin:", tum_kategoriler)
    with filtre_kolon3:
        if secilen_kategori == "Tümü":
            tum_alt_kategoriler = ["Tümü"] + list(orijinal_df["Alt Kategori"].dropna().unique())
        else:
            kategoriye_ozel_alt_kat = orijinal_df[orijinal_df["Kategori"] == secilen_kategori]["Alt Kategori"].dropna().unique()
            tum_alt_kategoriler = ["Tümü"] + list(kategoriye_ozel_alt_kat)
        secilen_alt_kategori = st.selectbox("Alt Kategori Seçin:", tum_alt_kategoriler)

    filtrelenmiş_df = orijinal_df.copy()
    if "Durum" in filtrelenmiş_df.columns:
        filtrelenmiş_df = filtrelenmiş_df[filtrelenmiş_df["Durum"] == "Aktif"]
    if secilen_kategori != "Tümü":
        filtrelenmiş_df = filtrelenmiş_df[filtrelenmiş_df["Kategori"] == secilen_kategori]
    if secilen_alt_kategori != "Tümü":
        filtrelenmiş_df = filtrelenmiş_df[filtrelenmiş_df["Alt Kategori"] == secilen_alt_kategori]
    if arama_kelimesi:
        filtrelenmiş_df = filtrelenmiş_df[
            filtrelenmiş_df["Ürün Adı"].str.upper().str.contains(arama_kelimesi, na=False) | 
            filtrelenmiş_df["Açıklama"].str.upper().str.contains(arama_kelimesi, na=False)
        ]

    filtrelenmiş_df["Birim Fiyatı"] = filtrelenmiş_df["Gizli_Birim_Fiyat"].apply(format_tl)
    
    if "sepet" not in st.session_state:
        st.session_state.sepet = {}

    filtrelenmiş_df["Miktar"] = filtrelenmiş_df["Ürün Kodu"].map(st.session_state.sepet).fillna(0).astype(int)

    ekran_df = filtrelenmiş_df[[
        "Ürün Kodu", "Kategori", "Alt Kategori", "Miktar", "Ürün Adı", 
        "Açıklama", "Birim Fiyatı", "KDV Oranı"
    ]].copy()

    st.write("### 📦 Ürün Listesi")
    st.info("💡 **Önemli İpucu:** Listeye eklenecek son ürünün miktarını yazdıktan sonra, boş bir yere tıklamayı veya klavyenizden 'Enter'a basmayı unutmayın.")
    
    with st.form("siparis_giris_formu"):
        düzenlenen_df = st.data_editor(
            ekran_df,
            key=f"siparis_tablosu_{st.session_state.editor_key}",
            column_config={
                "Ürün Kodu": None, 
                "Miktar": st.column_config.NumberColumn("Miktar", min_value=0, step=1, format="%d"),
                "Açıklama": st.column_config.TextColumn("Açıklama", alignment="center"),
                "KDV Oranı": st.column_config.NumberColumn("KDV Oranı", alignment="center"),
                "Birim Fiyatı": st.column_config.TextColumn("Birim Fiyatı", alignment="right")
            },
            disabled=["Kategori", "Alt Kategori", "Ürün Adı", "Açıklama", "Birim Fiyatı", "KDV Oranı"],
            hide_index=True, use_container_width=True 
        )
        
        submit_button = st.form_submit_button("➕ Sipariş Listesini Oluştur / Güncelle", use_container_width=True)

    if submit_button:
        düzenlenen_df["Miktar"] = pd.to_numeric(düzenlenen_df["Miktar"], errors="coerce").fillna(0).astype(int)
        for _, row in düzenlenen_df.iterrows():
            urun_kodu = row["Ürün Kodu"]
            miktar = row["Miktar"]
            if miktar > 0:
                st.session_state.sepet[urun_kodu] = miktar
            elif urun_kodu in st.session_state.sepet:
                del st.session_state.sepet[urun_kodu]
                
        st.session_state.liste_onaylandi = True
        st.rerun()

    st.markdown("---")

    if st.session_state.liste_onaylandi:
        liste_df = orijinal_df[orijinal_df["Ürün Kodu"].isin(st.session_state.sepet.keys())].copy()
        liste_df["Miktar"] = liste_df["Ürün Kodu"].map(st.session_state.sepet)

        if not liste_df.empty:
            
            st.warning("⚠️ **ÖNEMLİ HATIRLATMA:** Siparişiniz henüz kaydedilmedi! Lütfen aşağıdaki listenizi kontrol ettikten sonra, sayfanın altındaki **'Siparişi Gönder'** veya **'Taslak Olarak Kaydet'** butonlarından birine basarak işleminizi tamamlayın.")
            
            st.write(f"### 📋 Sipariş Listeniz - {st.session_state.secilen_yat}")
            
            orijinal_baz = orijinal_df.set_index("Ürün Kodu")
            
            liste_df["Gizli_Birim_Fiyat"] = liste_df["Ürün Kodu"].map(orijinal_baz["Gizli_Birim_Fiyat"]).apply(to_float)
            liste_df["Saf_KDV"] = liste_df["Ürün Kodu"].map(orijinal_baz["KDV Oranı"]).apply(to_float)
            
            liste_df["Ara Toplam Ham"] = liste_df["Miktar"] * liste_df["Gizli_Birim_Fiyat"]
            liste_df["KDV Tutarı Ham"] = liste_df["Ara Toplam Ham"] * (liste_df["Saf_KDV"] / 100)
            liste_df["KDV'li Toplam Ham"] = liste_df["Ara Toplam Ham"] + liste_df["KDV Tutarı Ham"]
            
            genel_ara_toplam = liste_df["Ara Toplam Ham"].sum()
            genel_kdv_toplam = liste_df["KDV Tutarı Ham"].sum()
            genel_toplam = liste_df["KDV'li Toplam Ham"].sum() 
            
            liste_df["Ara Toplam"] = liste_df["Ara Toplam Ham"].apply(format_tl)
            liste_df["KDV'li Toplam"] = liste_df["KDV'li Toplam Ham"].apply(format_tl)
            liste_df["Birim Fiyatı"] = liste_df["Gizli_Birim_Fiyat"].apply(format_tl)
            
            gosterilecek_liste = liste_df[[
                "Kategori", "Alt Kategori", "Miktar", "Ürün Adı", 
                "Açıklama", "Birim Fiyatı", "KDV Oranı", 
                "Ara Toplam", "KDV'li Toplam"
            ]]
            
            st.dataframe(
                gosterilecek_liste,
                column_config={
                    "Açıklama": st.column_config.TextColumn(alignment="center"),
                    "KDV Oranı": st.column_config.NumberColumn(alignment="center"),
                    "Birim Fiyatı": st.column_config.TextColumn(alignment="right"),
                    "Ara Toplam": st.column_config.TextColumn(alignment="right"),
                    "KDV'li Toplam": st.column_config.TextColumn(alignment="right")
                },
                hide_index=True, use_container_width=True
            )
            
            st.write("#### 💰 Sipariş Özeti Bilgileri")
            col1, col2, col3 = st.columns(3)
            col1.metric(label="Ara Toplam", value=format_tl(genel_ara_toplam))
            col2.metric(label="Toplam KDV", value=format_tl(genel_kdv_toplam))
            col3.metric(label="Genel Toplam", value=format_tl(genel_toplam))
            
            st.write("")
            
            buton_kolon1, buton_kolon2 = st.columns(2)
            
            with buton_kolon1:
                gonder_basildi = st.button("🚀 Siparişi Gönder", type="primary", use_container_width=True)
            with buton_kolon2:
                taslak_basildi = st.button("💾 Taslak Olarak Kaydet", type="secondary", use_container_width=True)
                
            if gonder_basildi or taslak_basildi:
                durum_degeri = "Gonderis" if gonder_basildi else "Gonderilmemis"
                status_mesaj = "siparişiniz başarıyla merkeze iletildi!" if gonder_basildi else "siparişiniz taslak olarak kaydedildi!"
                
                siparis_kayit_df = liste_df[[
                    "Ürün Kodu", "Kategori", "Alt Kategori", "Miktar", "Ürün Adı", 
                    "Açıklama", "Gizli_Birim_Fiyat", "Saf_KDV"
                ]]
                detay_json_str = json.dumps(siparis_kayit_df.to_dict(orient="records"), ensure_ascii=False)
                
                if siparisler_df.empty:
                    yeni_id = "KRAKEN-1001"
                else:
                    try:
                        son_id = str(siparisler_df.iloc[-1]["Siparis_ID"])
                        son_numara = int(son_id.split("-")[1])
                        yeni_id = f"KRAKEN-{son_numara + 1}"
                    except:
                        yeni_id = f"KRAKEN-{1000 + len(siparisler_df) + 1}"
                        
                tarih_str = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")
                
                try:
                    tablo_siparisler.append_row([
                        yeni_id, 
                        tarih_str, 
                        st.session_state.kullanici_adi, 
                        st.session_state.secilen_yat, 
                        detay_json_str, 
                        float(genel_toplam), 
                        durum_degeri
                    ])

                    # --- TELEGRAM ---
                    if gonder_basildi: 
                        try:
                            import requests
                            telegram_token = "8999770908:AAEGuzHWxTjeuos_0MwpCa5GTuJGhoG5xCw"
                            telegram_chat_id = "-1004481254642"
                            
                            siparis_detayi = ""
                            for urun_kodu in st.session_state.sepet:
                                urun_adi = orijinal_df.loc[orijinal_df["Ürün Kodu"] == urun_kodu, "Ürün Adı"].values[0]
                                # Telegram HTML formatında '&', '<', '>' gibi karakterleri görünce hata verir. Temizliyoruz:
                                urun_adi = str(urun_adi).replace("&", "ve").replace("<", "").replace(">", "")
                                siparis_detayi += f"▪️ {urun_adi} ({st.session_state.sepet[urun_kodu]} adet)\n"
                                
                            # Müşteri veya Yat isminde de ampersand (&) vs. varsa patlamaması için güvenceye alalım:
                            guvenli_isim = str(st.session_state.gercek_isim).replace("&", "ve").replace("<", "").replace(">", "")
                            guvenli_yat = str(st.session_state.secilen_yat).replace("&", "ve").replace("<", "").replace(">", "")
                            
                            mesaj = (
                                f"🚨 <b>YENİ SİPARİŞ GELDİ!</b>\n\n"
                                f"👤 <b>Müşteri:</b> {guvenli_isim}\n"
                                f"🛥️ <b>Yat:</b> {guvenli_yat}\n"
                                f"🆔 <b>Sipariş No:</b> {yeni_id}\n\n"
                                f"📦 <b>Sipariş İçeriği:</b>\n{siparis_detayi}"
                            )
                            
                            response = requests.post(
                                f"https://api.telegram.org/bot{telegram_token}/sendMessage", 
                                data={"chat_id": telegram_chat_id, "text": mesaj, "parse_mode": "HTML"},
                                timeout=10  # Sunucuya "10 saniye bekle, acele etme" diyoruz!
                            )
                            
                            if response.status_code != 200:
                                st.error(f"TELEGRAM GÖNDERİLEMEDİ! Hata Kodu: {response.text}")
                                st.stop() # Sayfayı dondurur, hatayı okumamızı sağlar
                                
                        except Exception as e:
                            st.error(f"TELEGRAM KOD HATASI: {str(e)}")
                            st.stop()

                    # ----------------------------------------------------

                    st.cache_data.clear() # 🌟 SİPARİŞ VERİLİNCE HAFIZAYI TEMİZLE Kİ TABLO GÜNCELLENSİN
                    st.success(f"Tebrikler! {yeni_id} nolu {status_mesaj}")
                    st.session_state.liste_onaylandi = False
                    st.session_state.sepet = {}
                    st.session_state.editor_key += 1
                    time.sleep(1.5)
                    st.rerun()

                except Exception as e:
                    st.error(f"Sipariş kaydı sırasında hata oluştu: {e}")
        else:
            st.warning("Listenizde miktar girişi yapılmış herhangi bir ürün bulunamadı.")

# ------------------------------------------
# TAB 2: SİPARİŞLERİM
# ------------------------------------------
with ana_sekme2:
    st.write("### 📋 Sipariş Geçmişiniz")
    
    kullanici_siparisleri = siparisler_df[siparisler_df["Hesap_Sahibi"] == st.session_state.kullanici_adi].copy()
    
    if kullanici_siparisleri.empty:
        st.info("Henüz geçmiş veya taslak bir siparişiniz bulunmamaktadır.")
    else:
        kullanici_siparisleri["Toplam Tutar"] = kullanici_siparisleri["Toplam_Tutar"].apply(format_tl)
        
        durum_tab1, durum_tab2, durum_tab3, durum_tab4 = st.tabs([
            "💾 Gönderilmemiş (Taslaklar)", 
            "🚀 Gönderilmiş (Onay Bekleyen)", 
            "✅ Onaylanan Siparişler",
            "📦 Teslim Edilen Siparişler"
        ])
        
        with durum_tab1:
            taslaklar = kullanici_siparisleri[kullanici_siparisleri["Durum"] == "Gonderilmemis"]
            if taslaklar.empty:
                st.write("Bekleyen taslak siparişiniz bulunmuyor.")
            else:
                # Tabloyu seçilebilir yaptık
                event = st.dataframe(
                    taslaklar[["Siparis_ID", "Tarih", "Yat_Adi", "Toplam Tutar"]], 
                    use_container_width=True, hide_index=True,
                    selection_mode="single-row", on_select="rerun"
                )
                
                # Satıra tıklandığında detayları aşağıya dök
                if event.selection.rows:
                    secili_idx = event.selection.rows[0]
                    secili_satir = taslaklar.iloc[secili_idx]
                    
                    st.divider()
                    st.markdown(f"#### 📄 Sipariş No: `{secili_satir['Siparis_ID']}` | Detaylar")
                    
                    try:
                        detay_dict = json.loads(secili_satir["Siparis_Detayi"])
                        detay_df = pd.DataFrame(detay_dict)
                        detay_df = detay_df.rename(columns={"Saf_KDV": "Kdv"})
                        
                        # Zırhlı dökümü bas
                        st_zırhlı_detay_goster(detay_df)
                        
                        # Butonlar
                        c1, c2, c3 = st.columns(3)
                        with c1:
                            if st.button("🚀 Gönder", type="primary", use_container_width=True):
                                raw_sip = tablo_siparisler.get_all_values()
                                headers = raw_sip[0]
                                durum_col_idx = headers.index("Durum") + 1 
                                for idx, row in enumerate(raw_sip[1:]):
                                    if row[headers.index("Siparis_ID")] == secili_satir["Siparis_ID"]:
                                        tablo_siparisler.update_cell(idx + 2, durum_col_idx, "Gonderis")
                                        st.rerun()
                        with c2:
                            if st.button("✏️ Düzenle", use_container_width=True):
                                st.session_state.sepet = {urun["Ürün Kodu"]: int(urun["Miktar"]) for urun in detay_dict}
                                st.session_state.liste_onaylandi = True
                                # Eski taslağı sil
                                raw_sip = tablo_siparisler.get_all_values()
                                for idx, row_val in enumerate(raw_sip[1:]):
                                    if row_val[0] == secili_satir["Siparis_ID"]:
                                        tablo_siparisler.delete_rows(idx + 2)
                                        break
                                st.rerun()
                        with c3:
                            if st.button("🗑️ Sil", type="secondary", use_container_width=True):
                                raw_sip = tablo_siparisler.get_all_values()
                                for idx, row_val in enumerate(raw_sip[1:]):
                                    if row_val[0] == secili_satir["Siparis_ID"]:
                                        tablo_siparisler.delete_rows(idx + 2)
                                        st.rerun()
                    except Exception as e:
                        st.error(f"Detaylar yüklenemedi: {e}")
                            
        with durum_tab2:
            gonderilenler = kullanici_siparisleri[kullanici_siparisleri["Durum"] == "Gonderis"]
            if gonderilenler.empty:
                st.write("Gönderilmiş ve onay bekleyen siparişiniz bulunmuyor.")
            else:
                st.dataframe(gonderilenler[["Siparis_ID", "Tarih", "Yat_Adi", "Toplam Tutar"]], hide_index=True, use_container_width=True)
                
        with durum_tab3:
            bitenler = kullanici_siparisleri[kullanici_siparisleri["Durum"] == "Bitmis"]
            if bitenler.empty:
                st.write("Teslim edilmiş geçmiş siparişiniz bulunmuyor.")
            else:
                st.dataframe(bitenler[["Siparis_ID", "Tarih", "Yat_Adi", "Toplam Tutar"]], hide_index=True, use_container_width=True)

        with durum_tab4:
            teslim_edilenler = kullanici_siparisleri[kullanici_siparisleri["Durum"] == "Bitmis"]
            if teslim_edilenler.empty:
                st.write("Henüz teslim edilmiş bir siparişiniz bulunmuyor.")
            else:
                st.dataframe(teslim_edilenler[["Siparis_ID", "Tarih", "Yat_Adi", "Toplam Tutar"]], hide_index=True, use_container_width=True)
                
        st.markdown("---")
        
