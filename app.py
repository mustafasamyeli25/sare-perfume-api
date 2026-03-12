import os
import csv
import json
import base64
import re
import logging
from flask import Flask, request, jsonify
from flask_cors import CORS
from google import genai
from google.genai import types

# 1. LOGLAMA YAPILANDIRMASI (Hata bulmayı kolaylaştırır)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

app = Flask(__name__)
CORS(app)

# 2. YAPILANDIRMA VE SABİTLER
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
CSV_FILE = 'products_export_1 (2).csv'
STORE_URL = "https://sareperfume.com/products/"

# 3. GEMINI İSTEMCİSİ (Hata kontrolü ile)
client = None
if GEMINI_API_KEY:
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        logging.info("Gemini API Bağlantısı Başarılı.")
    except Exception as e:
        logging.error(f"API İstemcisi kurulamadı: {e}")

# 4. KATALOG HAFIZALAMA (Uygulama açılırken bir kez yüklenir)
PRODUCT_DB = {}
CATALOG_TEXT = ""

def clean_html(html):
    if not html: return ""
    return re.sub(r'<.*?>', ' ', html).replace('\n', ' ').strip()

def load_catalog():
    global PRODUCT_DB, CATALOG_TEXT
    path = os.path.join(os.path.dirname(__file__), CSV_FILE)
    if not os.path.exists(path):
        logging.error("KRİTİK HATA: CSV dosyası bulunamadı!")
        return

    lines = []
    try:
        with open(path, mode='r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                handle = row.get('Handle', '').strip()
                title = row.get('Title', '').strip()
                if not handle or not title: continue
                
                PRODUCT_DB[handle] = {
                    "title": title,
                    "image": row.get('Image Src', '') or "https://via.placeholder.com/200",
                    "url": f"{STORE_URL}{handle}"
                }
                # AI'nın okuyacağı özet bilgi
                tags = row.get('Tags', '')
                desc = clean_html(row.get('Body (HTML)', ''))[:200]
                lines.append(f"KOD: {handle} | ÜRÜN: {title} | ETİKETLER: {tags} | ÖZET: {desc}")
        CATALOG_TEXT = "\n".join(lines)
        logging.info(f"Katalog Hazır: {len(PRODUCT_DB)} ürün yüklendi.")
    except Exception as e:
        logging.error(f"CSV Okuma Hatası: {e}")

load_catalog()

# 5. ANA MOTOR (RECOMMEND ENDPOINT)
@app.route("/recommend", methods=["POST"])
def recommend():
    if not client:
        return jsonify({"error": "Sistem Hatası: API Anahtarı bulunamadı."}), 200

    try:
        data = request.get_json()
        user_query = data.get("query", "").strip()
        image_base64 = data.get("image", None)

        if not user_query and not image_base64:
            return jsonify({"error": "Lütfen bir mesaj yazın veya fotoğraf yükleyin."}), 400

        # SHERLOCK HOLMES PROMPT (Kaçış karakterleri düzeltildi)
        prompt = f"""
        Sen elit bir koku uzmanısın. Katalog aşağıdadır:
        {CATALOG_TEXT}
        
        GÖREV: Müşterinin tarzını, mesleğini ve (fotoğraf varsa) ten rengi/kıyafet detaylarını analiz et.
        Katalogdan en uygun 3 parfümü seç.
        
        YANIT FORMATI: Sadece JSON formatında, başka yazı eklemeden şu yapıda yanıt ver:
        {{
            "recommendations": [
                {{
                    "kimlik": "Parfümün Handle değeri",
                    "analiz": "Kişiye özel neden seçtiğini anlatan 2 cümlelik derin analiz."
                }}
            ]
        }}
        """

        contents = [prompt]
        if user_query: contents.append(f"Müşteri Talebi: {user_query}")
        if image_base64:
            # Base64 temizleme
            img_data = image_base64.split(",")[1] if "," in image_base64 else image_base64
            contents.append(types.Part.from_bytes(data=base64.b64decode(img_data), mime_type='image/jpeg'))

        # API ÇAĞRISI (En stabil model ve config)
        response = client.models.generate_content(
            model='gemini-1.5-flash',
            contents=contents,
            config=types.GenerateContentConfig(
                response_mime_type='application/json'
            )
        )
        
        # Yanıtı temizle ve işle
        res_text = response.text.replace("```json", "").replace("```", "").strip()
        res_json = json.loads(res_text)
        
        final_output = []
        for rec in res_json.get("recommendations", []):
            handle = rec.get("kimlik", "").strip()
            if handle in PRODUCT_DB:
                product = PRODUCT_DB[handle]
                final_output.append({
                    "title": product["title"],
                    "url": product["url"],
                    "image": product["image"],
                    "description": rec.get("analiz", "")
                })

        return jsonify({"recommendations": final_output})

    except Exception as e:
        logging.error(f"Sistem Hatası: {str(e)}")
        return jsonify({"error": f"Hata: {str(e)}"}), 200

@app.route("/")
def health(): return "Sare Perfume API - Professional v3.0"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
