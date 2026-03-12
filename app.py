import os
import csv
import json
import re
import logging
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS

logging.basicConfig(level=logging.INFO)
app = Flask(__name__)
CORS(app)

# --- AYARLAR ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
CSV_NAME = 'products_export_1 (2).csv'
STORE_URL = "https://sareperfume.com/products/"

PRODUCT_DB = {}
CATALOG_TEXT = ""

def clean_html(raw):
    if not raw: return ""
    return re.sub(r'<.*?>', ' ', raw).replace('\n', ' ').strip()

def load_data():
    global PRODUCT_DB, CATALOG_TEXT
    path = os.path.join(os.path.dirname(__file__), CSV_NAME)
    
    if not os.path.exists(path):
        logging.error(f"Hata: {CSV_NAME} dosyası bulunamadı!")
        return

    lines = []
    try:
        # utf-8-sig kullanarak BOM karakterlerini temizliyoruz
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
                    desc = clean_html(row.get('Body (HTML)', ''))
                    # Gemini'nin daha iyi anlaması için yapılandırılmış metin
                    lines.append(self_text := f"KİMLİK: {h} | AD: {t} | ÖZET: {desc[:100]}")
        
        CATALOG_TEXT = "\n".join(lines)
        logging.info(f"{len(PRODUCT_DB)} ürün başarıyla yüklendi.")
    except Exception as e:
        logging.error(f"Katalog yükleme hatası: {e}")

load_data()

@app.route("/recommend", methods=["POST"])
def recommend():
    if not GEMINI_API_KEY:
        return jsonify({"error": "Sistem hatası: API Key eksik."}), 500
    
    try:
        data = request.get_json()
        query = data.get("query", "").strip()
        img_data = data.get("image", None)

        # --- PROMPT GÜNCELLEMESİ ---
        # AI'ya katalogdaki 'KİMLİK' bilgisini tam kullanması gerektiğini vurguluyoruz
        prompt = (
            "Sen samimi bir niş parfüm uzmanısın. Katalogdaki ürünleri kullanarak tavsiye ver.\n"
            f"Katalog:\n{CATALOG_TEXT}\n\n"
            "GÖREV: Kullanıcının havasına/görüntüsüne göre katalogdan 3 parfüm seç.\n"
            "KURALLAR:\n"
            "1. Sadece katalogdaki 'KİMLİK' (Handle) bilgilerini kullan.\n"
            "2. Yanıtın mutlaka geçerli bir JSON olmalı.\n"
            "3. Üslubun dükkanda kahve içiyormuşuz gibi çok doğal ve reklamsız olsun.\n"
            "YANIT FORMATI:\n"
            '{"recommendations": [{"kimlik": "handle-adi", "aciklama": "kısa ve samimi yorum"}]}'
        )

        # Gemini API Parçaları
        contents_parts = [{"text": prompt}]
        if query:
            contents_parts.append({"text": f"Müşteri mesajı: {query}"})
        
        if img_data:
            # Base64 temizleme ve MIME type tespiti
            mime_type = "image/jpeg"
            if "," in img_data:
                header, img_data = img_data.split(",")
                if "png" in header: mime_type = "image/png"
            
            contents_parts.append({
                "inlineData": {
                    "mimeType": mime_type,
                    "data": img_data
                }
            })

        # API İsteği
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
        payload = {
            "contents": [{"parts": contents_parts}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.7 # Biraz yaratıcılık ekler
            }
        }

        resp = requests.post(url, json=payload, timeout=30)
        resp_json = resp.json()

        # Hata kontrolü
        if "candidates" not in resp_json:
            logging.error(f"Gemini Hatası: {resp_json}")
            return jsonify({"error": "AI yanıt veremedi, lütfen tekrar dene."}), 200

        # JSON Yanıtını Ayrıştırma
        raw_text = resp_json['candidates'][0]['content']['parts'][0]['text']
        res_data = json.loads(raw_text)
        
        final_recommendations = []
        for r in res_data.get("recommendations", []):
            handle = r.get("kimlik", "").strip()
            if handle in PRODUCT_DB:
                product = PRODUCT_DB[handle]
                final_recommendations.append({
                    "title": product["title"],
                    "url": product["url"],
                    "image": product["image"],
                    "description": r.get("aciklama", "Sana çok yakışacağını düşündüğüm bir koku.")
                })

        return jsonify({"recommendations": final_recommendations})

    except Exception as e:
        logging.error(f"İşlem hatası: {e}")
        return jsonify({"error": "Bir şeyler ters gitti, butik kapalı olabilir :)"}), 200

@app.route("/")
def home(): 
    return jsonify({"status": "Sare API Aktif", "product_count": len(PRODUCT_DB)})

if __name__ == "__main__":
    # Render/Heroku gibi platformlar için PORT ayarı
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
