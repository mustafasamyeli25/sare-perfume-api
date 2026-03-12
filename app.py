import os
import csv
import json
import base64
import re
import logging
from flask import Flask, request, jsonify
from flask_cors import CORS
from google import genai

# Log sistemini kuralım
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)
CORS(app)

# --- YAPILANDIRMA ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
CSV_FILE_NAME = 'products_export_1 (2).csv'
PRODUCT_BASE_URL = "https://sareperfume.com/products/"

# --- API İSTEMCİSİ (En Güvenli Başlatma) ---
client = None
if GEMINI_API_KEY:
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        logging.info("Gemini API istemcisi hazır.")
    except Exception as e:
        logging.error(f"İstemci başlatılamadı: {e}")
else:
    logging.error("Vercel üzerinde GEMINI_API_KEY bulunamadı!")

# --- VERİTABANI YÜKLEME ---
PRODUCT_DB = {}
CATALOG_TEXT = ""

def clean_html(raw_html):
    if not raw_html: return ""
    return re.sub(r'<.*?>', ' ', raw_html).replace('\n', ' ').strip()

def load_catalog():
    global PRODUCT_DB, CATALOG_TEXT
    csv_path = os.path.join(os.path.dirname(__file__), CSV_FILE_NAME)
    if not os.path.exists(csv_path): return
    
    lines = []
    with open(csv_path, mode='r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            handle = row.get('Handle', '').strip()
            title = row.get('Title', '').strip()
            if not handle or not title: continue
            
            PRODUCT_DB[handle] = {
                "title": title,
                "image": row.get('Image Src', '') or "https://via.placeholder.com/150",
                "url": f"{PRODUCT_BASE_URL}{handle}"
            }
            lines.append(f"KOD: {handle} | AD: {title} | ETİKET: {row.get('Tags','')} | ÖZET: {clean_html(row.get('Body (HTML)',''))[:200]}")
    CATALOG_TEXT = "\n".join(lines)

load_catalog()

@app.route("/recommend", methods=["POST"])
def recommend():
    if not client:
        return jsonify({"error": "API anahtarı Vercel'de tanımlı değil!"}), 200

    try:
        data = request.get_json()
        query = data.get("query", "")
        img = data.get("image", None)

        # Sherlock Holmes Prompt (Manus'un hataya sebep olan .format yapısı düzeltildi)
        prompt = f"Sen koku uzmanısın. Kataloğumuz:\n{CATALOG_TEXT}\n\nMüşteriyi (yazı/foto) analiz et ve en uygun 3 parfümü seç. Yanıtı SADECE bu JSON formatında ver: " + '{"recommendations": [{"kimlik": "Handle", "aciklama": "Neden seçtiğini anlatan 2 cümle"}]}'

        contents = [prompt]
        if query: contents.append(f"Müşteri diyor ki: {query}")
        if img:
            img_clean = img.split(",")[1] if "," in img else img
            contents.append(genai.types.Part.from_bytes(data=base64.b64decode(img_clean), mime_type='image/jpeg'))

        # Kotayı korumak için 1.5-flash
        response = client.models.generate_content(
            model='gemini-1.5-flash',
            contents=contents,
            config={'response_mime_type': 'application/json'}
        )
        
        raw_text = response.text.replace("```json", "").replace("```", "").strip()
        results = json.loads(raw_text)
        
        final_list = []
        for r in results.get("recommendations", []):
            h = r.get("kimlik")
            if h in PRODUCT_DB:
                final_list.append({
                    "title": PRODUCT_DB[h]["title"],
                    "url": PRODUCT_DB[h]["url"],
                    "image": PRODUCT_DB[h]["image"],
                    "description": r.get("aciklama", "")
                })
        return jsonify({"recommendations": final_list})

    except Exception as e:
        logging.error(f"Hata: {e}")
        return jsonify({"error": f"Bir şeyler ters gitti: {str(e)}"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
