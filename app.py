import os
import csv
import json
import base64
import re
import logging
from flask import Flask, request, jsonify
from flask_cors import CORS

# En güncel Google AI kütüphanesi
from google import genai
from google.genai import types

# Log sistemini tertemiz kuralım (Tırnak hatası düzeltildi)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)
CORS(app)

# --- Yapılandırma ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
CSV_FILE_NAME = 'products_export_1 (2).csv'
PLACEHOLDER_IMAGE_URL = "https://via.placeholder.com/150?text=Sare+Perfume"
PRODUCT_BASE_URL = "https://sareperfume.com/products/"

# Gemini İstemcisi
client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

# --- Veritabanı Hafızası ---
PERFUME_CATALOG_TEXT = ""
PRODUCT_DB = {}

def clean_html(raw_html):
    if not raw_html: return ""
    cleanr = re.compile('<.*?>')
    cleantext = re.sub(cleanr, ' ', raw_html)
    return re.sub(r'\s+', ' ', cleantext).strip()

def load_data():
    global PERFUME_CATALOG_TEXT, PRODUCT_DB
    current_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(current_dir, CSV_FILE_NAME)
    
    if not os.path.exists(csv_path):
        logging.error("CSV Bulunamadı!")
        return

    catalog_lines = []
    with open(csv_path, mode='r', encoding='utf-8-sig') as file:
        reader = csv.DictReader(file)
        for row in reader:
            title = row.get('Title', '').strip()
            handle = row.get('Handle', '').strip()
            if not title or not handle: continue
            
            image = row.get('Image Src', '').strip()
            body = clean_html(row.get('Body (HTML)', ''))
            tags = row.get('Tags', '').strip()
            
            if handle not in PRODUCT_DB:
                PRODUCT_DB[handle] = {
                    "title": title,
                    "image": image if image else PLACEHOLDER_IMAGE_URL,
                    "url": f"{PRODUCT_BASE_URL}{handle}"
                }
                catalog_lines.append(f"KİMLİK: {handle} | İSİM: {title} | ETİKETLER: {tags} | ÖZET: {body[:250]}")
    
    PERFUME_CATALOG_TEXT = "\n".join(catalog_lines)
    logging.info(f"Katalog Yüklendi: {len(PRODUCT_DB)} ürün.")

# Verileri yükle
load_data()

@app.route("/recommend", methods=["POST"])
def recommend():
    if not client:
        return jsonify({"error": "API Key Eksik"}), 200

    try:
        data = request.get_json()
        user_query = data.get("query", "").strip()
        image_base64 = data.get("image", None)

        if not user_query and not image_base64:
            return jsonify({"error": "Yazı veya fotoğraf girilmedi."}), 400

        # SHERLOCK HOLMES PROMPT
        prompt = f"""
        Sen elit bir koku uzmanısın. Katalog aşağıdadır:
        {PERFUME_CATALOG_TEXT}
        
        Görev:
        1. Fotoğrafı/metni derinlemesine analiz et. Kişinin mesleğini, tarzını, ten rengini (fotoğraf varsa) anla.
        2. Katalogdan en uygun 3 parfümü seç.
        3. Yanıtı SADECE bu JSON formatında ver:
        {{
            "recommendations": [
                {{
                    "kimlik": "Handle degeri",
                    "aciklama": "Kişinin fotoğrafındaki detaylara (üniforma, ten rengi, ortam vb.) özel 2 cümlelik analiz."
                }}
            ]
        }}
        """

        content_parts = [prompt]
        if image_base64:
            img_data = image_base64.split(",")[1] if "," in image_base64 else image_base64
            content_parts.append(types.Part.from_bytes(data=base64.b64decode(img_data), mime_type='image/jpeg'))

        response = client.models.generate_content(
            model='gemini-2.0-flash', # En stabil sürüm
            contents=content_parts,
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        
        result_json = json.loads(response.text.replace("```json", "").replace("```", "").strip())
        
        final_list = []
        for rec in result_json.get("recommendations", []):
            h = rec.get("kimlik")
            if h in PRODUCT_DB:
                p = PRODUCT_DB[h]
                final_list.append({
                    "title": p["title"],
                    "url": p["url"],
                    "image": p["image"],
                    "description": rec.get("aciklama")
                })
                
        return jsonify({"recommendations": final_list})

    except Exception as e:
        logging.error(f"Hata: {e}")
        return jsonify({"error": f"Sistem Hatası: {str(e)}"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
