import os
import csv
import json
import base64
import re
import logging
from flask import Flask, request, jsonify
from flask_cors import CORS
import google.generativeai as genai

# Logları aktif edelim
logging.basicConfig(level=logging.INFO)

app = Flask(__name__)
CORS(app)

# --- AYARLAR ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
CSV_NAME = 'products_export_1 (2).csv'
STORE_URL = "https://sareperfume.com/products/"

# Gemini Yapılandırması
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# --- KATALOG VERİLERİ ---
PRODUCT_DB = {}
CATALOG_TEXT = ""

def clean_html(raw):
    if not raw: return ""
    return re.sub(r'<.*?>', ' ', raw).replace('\n', ' ').strip()

def load_data():
    global PRODUCT_DB, CATALOG_TEXT
    path = os.path.join(os.path.dirname(__file__), CSV_NAME)
    if not os.path.exists(path):
        logging.error(f"HATA: {CSV_NAME} bulunamadı!")
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
                    lines.append(f"KOD: {h} | AD: {t}")
        CATALOG_TEXT = "\n".join(lines)
        logging.info("Katalog yüklendi.")
    except Exception as e:
        logging.error(f"Veri yükleme hatası: {e}")

load_data()

@app.route("/recommend", methods=["POST"])
def recommend():
    if not GEMINI_API_KEY:
        return jsonify({"error": "API Key eksik."}), 200

    try:
        data = request.get_json()
        query = data.get("query", "").strip()
        img = data.get("image", None)

        # Sherlock Holmes Prompt
        prompt = (
            "Sen elit bir koku danışmanısın. Katalog:\n"
            f"{CATALOG_TEXT}\n\n"
            "Müşteriyi analiz et ve en uygun 3 parfümü seç. "
            "Yanıtı SADECE bu JSON yapısında ver:\n"
            '{"recommendations": [{"kimlik": "Handle", "analiz": "Yorum"}]}'
        )

        # 404 HATASINI ÇÖZEN KRİTİK MODEL TANIMI
        # 'gemini-1.5-flash' yerine bazen 'models/gemini-1.5-flash' gerekir
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        content = [prompt]
        if query: content.append(f"Talep: {query}")
        if img:
            img_data = img.split(",")[1] if "," in img else img
            content.append({
                "mime_type": "image/jpeg",
                "data": base64.b64decode(img_data)
            })

        # Yanıtı al
        response = model.generate_content(content)
        
        # JSON temizleme
        txt = response.text.strip()
        if "```json" in txt:
            txt = txt.split("```json")[1].split("```")[0].strip()
        elif "```" in txt:
            txt = txt.split("```")[1].split("```")[0].strip()
            
        res_data = json.loads(txt)
        
        final_list = []
        for r in res_data.get("recommendations", []):
            h = r.get("kimlik", "").strip()
            if h in PRODUCT_DB:
                final_list.append({
                    "title": PRODUCT_DB[h]["title"],
                    "url": PRODUCT_DB[h]["url"],
                    "image": PRODUCT_DB[h]["image"],
                    "description": r.get("analiz", "")
                })
        
        return jsonify({"recommendations": final_list})

    except Exception as e:
        logging.error(f"Hata: {e}")
        return jsonify({"error": f"Sistem hatası: {str(e)}"}), 200

@app.route("/")
def home(): return "Sare API Aktif!"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
