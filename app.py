import os
import csv
import json
import base64
import re
import logging
from flask import Flask, request, jsonify
from flask_cors import CORS

# 2026 standartlarındaki yeni kütüphane
from google import genai
from google.genai import types

# Detaylı hata takibi için logları açalım
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

app = Flask(__name__)
CORS(app)

# --- AYARLAR ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
CSV_NAME = 'products_export_1 (2).csv'
STORE_URL = "https://sareperfume.com/products/"

# İstemciyi başlatalım (API anahtarı kontrolüyle)
client = None
if GEMINI_API_KEY:
    try:
        # Yeni nesil istemci yapılandırması
        client = genai.Client(api_key=GEMINI_API_KEY)
        logging.info("Gemini API Bağlantısı Başarıyla Kuruldu.")
    except Exception as e:
        logging.error(f"API Bağlantı Hatası: {e}")

# --- KATALOG VERİLERİNİ HAFIZAYA AL ---
PRODUCT_DB = {}
CATALOG_TEXT = ""

def clean_html(raw):
    if not raw: return ""
    return re.sub(r'<.*?>', ' ', raw).replace('\n', ' ').strip()

def load_data():
    global PRODUCT_DB, CATALOG_TEXT
    path = os.path.join(os.path.dirname(__file__), CSV_NAME)
    if not os.path.exists(path):
        logging.error(f"KRİTİK HATA: {CSV_NAME} bulunamadı!")
        return

    lines = []
    try:
        with open(path, mode='r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                h = row.get('Handle', '').strip()
                t = row.get('Title', '').strip()
                if h and t:
                    PRODUCT_DB[h] = {
                        "title": t,
                        "image": row.get('Image Src', '') or "https://via.placeholder.com/200",
                        "url": f"{STORE_URL}{h}"
                    }
                    lines.append(f"KİMLİK: {h} | AD: {t}")
        CATALOG_TEXT = "\n".join(lines)
        logging.info(f"Katalog başarıyla yüklendi: {len(PRODUCT_DB)} ürün.")
    except Exception as e:
        logging.error(f"Veri yükleme hatası: {e}")

# Uygulama başlarken verileri bir kez yükle
load_data()

@app.route("/recommend", methods=["POST"])
def recommend():
    if not client:
        return jsonify({"error": "Sistem Hatası: API Anahtarı eksik veya geçersiz."}), 200

    try:
        data = request.get_json()
        query = data.get("query", "").strip()
        img_base64 = data.get("image", None)

        if not query and not img_base64:
            return jsonify({"error": "Lütfen bir mesaj yazın veya fotoğraf yükleyin."}), 400

        # Sherlock Holmes Prompt (Süslü parantez karmaşası olmadan)
        prompt = (
            "Sen elit bir koku uzmanısın. Katalog aşağıdadır:\n" +
            f"{CATALOG_TEXT}\n\n" +
            "GÖREV: Müşteriyi analiz et ve kataloğumuzdan en uygun 3 parfümü seç.\n" +
            "YANIT: Sadece JSON formatında, şu yapıda cevap ver:\n" +
            '{"recommendations": [{"kimlik": "Handle degeri", "analiz": "Analiz mesajı"}]}'
        )

        contents = [prompt]
        if query: contents.append(f"Müşteri İsteği: {query}")
        
        if img_base64:
            # Base64 temizleme işlemi
            img_data = img_base64.split(",")[1] if "," in img_base64 else img_base64
            contents.append(
                types.Part.from_bytes(
                    data=base64.b64decode(img_data),
                    mime_type='image/jpeg'
                )
            )

        # 404 HATASINI ÇÖZEN EN STABİL MODEL ÇAĞRISI
        # 'gemini-1.5-flash' ismi bazen v1beta kapısına yönlenir, 
        # bu kütüphane ile bu kullanımı sabitledik.
        response = client.models.generate_content(
            model='gemini-1.5-flash',
            contents=contents,
            config=types.GenerateContentConfig(
                response_mime_type='application/json'
            )
        )
        
        # Yanıtı temizle ve işle
        raw_text = response.text.replace("```json", "").replace("```", "").strip()
        res_json = json.loads(raw_text)
        
        final_list = []
        for r in res_json.get("recommendations", []):
            h = r.get("kimlik", "").strip()
            if h in PRODUCT_DB:
                final_list.append({
                    "title": PRODUCT_DB[h]["title"],
                    "url": PRODUCT_DB[h]["url"],
                    "image": PRODUCT_DB[h]["image"],
                    "description": r.get("analiz", "Size özel seçtiğimiz bu koku ile tarzınızı yansıtın.")
                })
        
        return jsonify({"recommendations": final_list})

    except Exception as e:
        logging.error(f"Sistem Hatası: {e}")
        return jsonify({"error": f"Bir şeyler ters gitti: {str(e)}"}), 200

@app.route("/")
def home(): 
    return "Sare Perfume API v6.0 - 2026 Engine Aktif!"

if __name__ == "__main__":
    # Geliştirme ortamı için port ayarı
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
