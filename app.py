import os
import csv
import json
import base64
import re
import logging
from flask import Flask, request, jsonify
from flask_cors import CORS

# AZ ÖNCE ÇALIŞAN O SAĞLAM KÜTÜPHANE
import google.generativeai as genai

logging.basicConfig(level=logging.INFO)
app = Flask(__name__)
CORS(app)

# --- AYARLAR ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
CSV_NAME = 'products_export_1 (2).csv'
STORE_URL = "https://sareperfume.com/products/"

# Gemini Yapılandırması (Geleneksel ve En Sağlam Yöntem)
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# --- VERİ YÜKLEME ---
PRODUCT_DB = {}
CATALOG_TEXT = ""

def clean_html(raw):
    if not raw: return ""
    return re.sub(r'<.*?>', ' ', raw).replace('\n', ' ').strip()

def load_data():
    global PRODUCT_DB, CATALOG_TEXT
    path = os.path.join(os.path.dirname(__file__), CSV_NAME)
    if not os.path.exists(path):
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
                    tags = row.get('Tags', '')
                    lines.append(f"KOD: {h} | AD: {t} | TAGS: {tags}")
        CATALOG_TEXT = "\n".join(lines)
        logging.info("Katalog Hazır!")
    except Exception as e:
        logging.error(f"Katalog Hatası: {e}")

load_data()

@app.route("/recommend", methods=["POST"])
def recommend():
    if not GEMINI_API_KEY:
        return jsonify({"error": "API Key Vercel'e eklenmemiş!"}), 200

    try:
        data = request.get_json()
        query = data.get("query", "").strip()
        img = data.get("image", None)

        # SHERLOCK HOLMES PROMPT (Yapay Zekanın Beyni)
        prompt = (
            "Sen elit bir koku uzmanısın. Katalog aşağıdadır:\n" +
            f"{CATALOG_TEXT}\n\n" +
            "GÖREV: Müşterinin tarzını, mesleğini ve (fotoğraf varsa) ten rengini analiz et. " +
            "En uygun 3 parfümü seç. Yanıtı SADECE aşağıdaki JSON formatında ver, başka yazı ekleme:\n" +
            '{"recommendations": [{"kimlik": "Handle degeri", "analiz": "2 cümlelik kişiye özel analiz"}]}'
        )

        # 404 HATASINI BİTİREN STABİL MODEL ÇAĞRISI
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        content = [prompt]
        if query: content.append(f"Müşteri Talebi: {query}")
        if img:
            img_data = img.split(",")[1] if "," in img else img
            content.append({
                "mime_type": "image/jpeg",
                "data": base64.b64decode(img_data)
            })

        response = model.generate_content(content)
        
        # Yanıtı JSON olarak temizle
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
                    "description": r.get("analiz", "Harika bir koku seçimi.")
                })
        
        return jsonify({"recommendations": final_list})

    except Exception as e:
        logging.error(f"Sistem Hatası: {e}")
        return jsonify({"error": f"Bir şeyler ters gitti: {str(e)}"}), 200

@app.route("/")
def home(): return "Sare Perfume API v7.0 - Geri Döndük ve Aktifiz!"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
