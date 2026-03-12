import os
import csv
import json
import base64
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
    if not os.path.exists(path): return
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
                    desc = clean_html(row.get('Body (HTML)', ''))
                    lines.append(f"KİMLİK: {h} | AD: {t} | ÖZET: {desc[:100]}")
        CATALOG_TEXT = "\n".join(lines)
    except Exception as e:
        logging.error(f"Katalog hatası: {e}")

load_data()

@app.route("/recommend", methods=["POST"])
def recommend():
    if not GEMINI_API_KEY:
        return jsonify({"error": "API Key eksik."}), 200
    try:
        data = request.get_json()
        query = data.get("query", "").strip()
        img = data.get("image", None)

        # --- SAMİMİ UZMAN PROMPTU ---
        prompt = (
            "Sen seçkin bir niş parfüm butiğinde çalışan, işini çok iyi bilen ama müşterisiyle çok samimi ve içten konuşan bir uzmansın.\n"
            f"Katalog:\n{CATALOG_TEXT}\n\n"
            "GÖREV: Fotoğraf ev ortamında bir selfie bile olsa, kişinin enerjisine ve o anki havasına bakarak 3 parfüm seç.\n"
            "ÜSLUP: ASLA 'notalar, paçuli, zarafetinizi taçlandırır' gibi sıkıcı reklam kelimeleri kullanma. "
            "Sanki dükkanda karşılıklı kahve içiyormuşsunuz gibi doğal ve reklamsız konuş.\n"
            "YANIT: Sadece JSON formatında cevap ver: "
            '{"recommendations": [{"kimlik": "Handle", "aciklama": "Samimi 2 cümlelik analiz"}]}'
        )

        # REST API (DOĞRUDAN BAĞLANTI)
        parts = [{"text": prompt}]
        if query: parts.append({"text": query})
        if img:
            parts.append({"inlineData": {"mimeType": "image/jpeg", "data": img.split(",")[1] if "," in img else img}})

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
        resp = requests.post(url, json={"contents": [{"parts": parts}], "generationConfig": {"responseMimeType": "application/json"}}, timeout=30)
        
        raw_text = resp.json()['candidates'][0]['content']['parts'][0]['text']
        res_data = json.loads(raw_text[raw_text.find('{'):raw_text.rfind('}')+1])
        
        final = []
        for r in res_data.get("recommendations", []):
            h = r.get("kimlik", "").strip()
            if h in PRODUCT_DB:
                final.append({
                    "title": PRODUCT_DB[h]["title"],
                    "url": PRODUCT_DB[h]["url"],
                    "image": PRODUCT_DB[h]["image"],
                    "description": r.get("aciklama", "Harika bir seçim.")
                })
        return jsonify({"recommendations": final})
    except Exception as e:
        return jsonify({"error": str(e)}), 200

@app.route("/")
def home(): return "Sare API Aktif!"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
