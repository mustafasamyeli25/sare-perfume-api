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

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

app = Flask(__name__)
CORS(app)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
CSV_NAME = 'products_export_1 (2).csv'
STORE_URL = "https://sareperfume.com/products/"

client = None
if GEMINI_API_KEY:
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
    except Exception as e:
        logging.error(f"API Hatası: {e}")

PRODUCT_DB = {}
CATALOG_TEXT = ""

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
                    desc = re.sub(r'<.*?>', ' ', row.get('Body (HTML)', '')).replace('\n', ' ').strip()
                    lines.append(f"KİMLİK: {h} | AD: {t} | ETİKET: {row.get('Tags', '')} | ÖZET: {desc[:150]}")
        CATALOG_TEXT = "\n".join(lines)
    except Exception as e:
        logging.error(f"Katalog Hatası: {e}")

load_data()

@app.route("/recommend", methods=["POST"])
def recommend():
    if not client:
        return jsonify({"error": "API Key bulunamadı."}), 200

    try:
        data = request.get_json()
        query = data.get("query", "").strip()
        img = data.get("image", None)

        if not query and not img:
            return jsonify({"error": "Lütfen yazı yazın veya fotoğraf ekleyin."}), 400

        prompt = (
            "Sen son derece samimi, karizmatik ve insan sarrafı bir niş parfüm danışmanısın. "
            "Sanki müşteri mağazana gelmiş ve karşılıklı kahve içiyormuşsunuz gibi sıcak, senli-benli bir dille konuş.\n"
            f"Katalog:\n{CATALOG_TEXT}\n\n"
            "GÖREV:\n"
            "1. Fotoğraf geldiyse: Bu bir ev selfie'si, boydan fotoğraf veya sadece bir yüz olabilir. Hiç fark etmez. "
            "Kişinin saç/göz rengine, gülüşüne, giyimine veya o anki rahat ortamına bakarak enerjisini hisset.\n"
            "2. Katalogdan en uygun 3 parfümü seç.\n\n"
            "ÜSLUP KURALI:\n"
            "ASLA sıkıcı katalog veya reklam metni yazma ('mükemmel uyum sağlar', 'taçlandırır' gibi klişeler YASAK!). "
            "Doğrudan fotoğraftaki/yazıdaki bir detaya vur. Örnek: 'Evdeki o cool havanı hissettim. Senin gibi esmer tenli ve sıcak gülüşlü birine odunsu bir şeyler lazım...'\n\n"
            "YANIT SADECE JSON OLMALIDIR:\n"
            '{"recommendations": [{"kimlik": "Handle degeri", "aciklama": "Sıcak ve doğal 2-3 cümlelik analiz."}]}'
        )

        contents = [prompt]
        if query: contents.append(f"Müşteri Talebi: {query}")
        if img:
            img_data = img.split(",")[1] if "," in img else img
            contents.append(
                types.Part.from_bytes(data=base64.b64decode(img_data), mime_type='image/jpeg')
            )

        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=contents,
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        
        raw_text = response.text.strip()
        start_idx = raw_text.find('{')
        end_idx = raw_text.rfind('}')
        if start_idx != -1 and end_idx != -1:
            raw_text = raw_text[start_idx:end_idx+1]
            
        res_json = json.loads(raw_text)
        
        final_list = []
        for r in res_json.get("recommendations", []):
            h = r.get("kimlik", "").strip()
            if h in PRODUCT_DB:
                product = PRODUCT_DB[h]
                final_list.append({
                    "title": product["title"],
                    "url": product["url"],
                    "image": product["image"],
                    "description": r.get("aciklama", "Bu koku tam sana göre.")
                })
        
        return jsonify({"recommendations": final_list})

    except Exception as e:
        logging.error(f"Hata: {e}")
        return jsonify({"error": f"Sistem Hatası: {str(e)}"}), 200

@app.route("/")
def home(): return "Sare API Aktif!"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
