import os
import csv
import json
import base64
import re
import logging
from flask import Flask, request, jsonify
from flask_cors import CORS

import google.generativeai as genai

logging.basicConfig(level=logging.INFO)
app = Flask(__name__)
CORS(app)

# --- AYARLAR ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
CSV_NAME = 'products_export_1 (2).csv'
STORE_URL = "https://sareperfume.com/products/"

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
                    lines.append(f"KİMLİK: {h} | AD: {t} | ETİKET: {row.get('Tags', '')} | ÖZET: {desc[:100]}")
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

        if not query and not img:
            return jsonify({"error": "Lütfen yazı yazın veya fotoğraf ekleyin."}), 400

        # --- LÜKS BUTİK DANIŞMANI PROMPTU ---
        prompt = (
            "Sen Beymen gibi lüks bir butikte çalışan, işini çok iyi bilen, müşteriyle çok samimi ama saygılı konuşan bir niş parfüm uzmanısın.\n"
            f"Katalog:\n{CATALOG_TEXT}\n\n"
            "GÖREV:\n"
            "1. Fotoğraf geldiyse: İllaki meslek, üniforma veya takım elbise arama! Müşteri evden rahat bir pijama fotoğrafı da atmış olabilir. Sen onun bakışlarına, saçlarına, enerjisine veya ortamın doğallığına odaklan.\n"
            "2. Ona katalogdan en uygun 3 parfümü seç.\n\n"
            "ÜSLUP KURALLARI:\n"
            "- ASLA 'zarafetinizi taçlandırır, mükemmel uyum sağlar' gibi yapmacık reklam kelimeleri KULLANMA!\n"
            "- Hitap ederken çok samimi ama saygılı ol. Sanki mağazanda karşılıklı kahve içiyormuşsunuz gibi doğal konuş.\n"
            "- Örnek tarz: 'Ev ortamındaki o huzurlu ve doğal enerjinizi hissettim. Bu dinginliğe şu odunsu kokunun sıcaklığı çok yakışacaktır...' veya 'Gözlerinizdeki o derin bakışı bu iddialı kokuyla tamamlamak istedim...'\n\n"
            "YANIT SADECE JSON OLMALIDIR:\n"
            '{"recommendations": [{"kimlik": "Handle degeri", "aciklama": "Sıcak, içten ve reklamsız 2 cümlelik özel analiz."}]}'
        )

        # Günde 1500 adet ücretsiz hakkı olan STABİL model
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
        
        # JSON Kalkanı
        txt = response.text.strip()
        start_idx = txt.find('{')
        end_idx = txt.rfind('}')
        if start_idx != -1 and end_idx != -1:
            txt = txt[start_idx:end_idx+1]
            
        res_data = json.loads(txt)
        
        final_list = []
        for r in res_data.get("recommendations", []):
            h = r.get("kimlik", "").strip()
            if h in PRODUCT_DB:
                product = PRODUCT_DB[h]
                final_list.append({
                    "title": product["title"],
                    "url": product["url"],
                    "image": product["image"],
                    "description": r.get("aciklama", "Bu koku enerjinize çok yakışacaktır.")
                })
        
        return jsonify({"recommendations": final_list})

    except Exception as e:
        logging.error(f"Hata: {e}")
        return jsonify({"error": f"Sistem yogunlugu veya hata: {str(e)}"}), 200

@app.route("/")
def home(): return "Sare API Aktif!"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
