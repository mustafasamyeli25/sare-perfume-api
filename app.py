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
        logging.error(f"API Hatasi: {e}")

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
                    lines.append(f"KIMLIK: {h} | AD: {t} | ETIKET: {row.get('Tags', '')} | OZET: {desc[:150]}")
        CATALOG_TEXT = "\n".join(lines)
    except Exception as e:
        logging.error(f"Katalog Hatasi: {e}")

load_data()

@app.route("/recommend", methods=["POST"])
def recommend():
    if not client:
        return jsonify({"error": "API Key bulunamadi."}), 200

    try:
        data = request.get_json()
        query = data.get("query", "").strip()
        img = data.get("image", None)

        if not query and not img:
            return jsonify({"error": "Lutfen yazi yazin veya fotograf ekleyin."}), 400

        # --- SAMİMİ AMA PROFESYONEL BUTİK UZMANI PROMPTU ---
        prompt = (
            "Sen seçkin, son derece sicakkanli ve insan sarrafi bir luks parfum danismanisin. "
            "Musterinle aranda profesyonel ama cok icten, guven veren bir bag var.\n"
            f"Katalog:\n{CATALOG_TEXT}\n\n"
            "GOREV:\n"
            "1. Fotografa bak (ev hali, ofis, sokak veya sadece bir yuz olabilir). Illaki meslek arama! "
            "Kisinin enerjisine, bakisina, gulusune veya o anki ortaminin havasina odaklan.\n"
            "2. Ona katalogdan en uygun 3 parfumu sec.\n\n"
            "USLUP KURALLARI:\n"
            "- ASLA 'zarafetinizi taclandirir, mukemmel uyum saglar, notalari soyledir' gibi yapmacik ve sikici reklamci kelimeleri KULLANMA!\n"
            "- 'Kanka' agziyla konusma; saygili ama sicak ve dogal bir dil kullan.\n"
            "- Ornek tarz: 'Ev ortamindaki o huzurlu ve dogal enerjinizi hissettim. Bu dinginlige bu kokunun sicakligi cok yakisacaktir...' veya 'Gozlerinizdeki o derin bakisi bu iddiali kokuyla tamamlamak istedim...'\n\n"
            "YANIT SADECE ASAGIDAKI JSON OLMALIDIR:\n"
            '{"recommendations": [{"kimlik": "Handle degeri", "aciklama": "Sicak, icten ve reklamsiz 2 cumlelik ozel analiz."}]}'
        )

        contents = [prompt]
        if query: contents.append(f"Musteri Talebi: {query}")
        if img:
            img_data = img.split(",")[1] if "," in img else img
            contents.append(
                types.Part.from_bytes(data=base64.b64decode(img_data), mime_type='image/jpeg')
            )

        # --- OTOMATİK MODEL GEÇİŞİ (KOTA DOLARSA ÇÖKMESİN DİYE) ---
        # En yüksek kotası olan modelden başlayarak dener.
        fallback_models = [
            'gemini-1.5-flash',
            'gemini-2.0-flash',
            'gemini-1.5-pro'
        ]
        
        response = None
        for m in fallback_models:
            try:
                response = client.models.generate_content(
                    model=m,
                    contents=contents,
                    config=types.GenerateContentConfig(response_mime_type="application/json")
                )
                break
            except Exception as e:
                logging.warning(f"{m} modeli basarisiz oldu, digerine geciliyor. Hata: {e}")
                continue
                
        if not response:
            return jsonify({"error": "Sistem yogunlugu nedeniyle su an yanit veremiyoruz, lutfen birazdan tekrar deneyin."}), 200
        
        # --- JSON TEMİZLEYİCİ ---
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
                    "description": r.get("aciklama", "Bu koku enerjinize cok yakisacak.")
                })
        
        return jsonify({"recommendations": final_list})

    except Exception as e:
        logging.error(f"Genel Hata: {e}")
        return jsonify({"error": f"Sistem Hatasi: {str(e)}"}), 200

@app.route("/")
def home(): return "Sare API Aktif!"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
