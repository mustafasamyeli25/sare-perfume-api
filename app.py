import os
import csv
import json
import base64
import re
from flask import Flask, request, jsonify
from flask_cors import CORS
from google import genai
from google.genai import types

app = Flask(__name__)
CORS(app)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

# --- KATALOĞU VE RESİMLERİ HAFIZAYA AL ---
PERFUME_CATALOG_TEXT = ""
PRODUCT_DB = {}

# HTML etiketlerini temizleme fonksiyonu
def clean_html(raw_html):
    if not raw_html: return ""
    cleanr = re.compile('<.*?>')
    cleantext = re.sub(cleanr, ' ', raw_html)
    return re.sub(r'\s+', ' ', cleantext).strip()

try:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # GitHub'a yüklediğin dosyanın tam adı (Birebir aynı olmalı)
    csv_path = os.path.join(current_dir, 'products_export_1 (2).csv')
    
    catalog_lines = []
    with open(csv_path, mode='r', encoding='utf-8-sig') as file:
        reader = csv.DictReader(file)
        for row in reader:
            title = row.get('Title', '')
            if not title: continue # Boş (varyant) satırlarını atla
            
            handle = row.get('Handle', '')
            body = clean_html(row.get('Body (HTML)', ''))
            tags = row.get('Tags', '')
            image = row.get('Image Src', '')
            
            # Veritabanına kaydet (Görsel ve link için gizli hafıza)
            if handle not in PRODUCT_DB:
                PRODUCT_DB[handle] = {
                    "title": title,
                    "image": image if image else "https://via.placeholder.com/150?text=Sare+Perfume",
                    "url": f"https://sareparfum.com/products/{handle}"
                }
                
                # Yapay zekaya sadece özet bilgi veriyoruz (Tüy gibi hafifletiyoruz)
                line = f"KİMLİK: {handle} | İSİM: {title} | ETİKETLER: {tags} | DETAY: {body[:300]}"
                catalog_lines.append(line)
                
    PERFUME_CATALOG_TEXT = "\n".join(catalog_lines)
except Exception as e:
    PERFUME_CATALOG_TEXT = f"HATA: Katalog yüklenemedi. {str(e)}"

@app.route("/recommend", methods=["POST"])
def recommend():
    if not client:
        return jsonify({"error": "Sistem Hatası: API Anahtarı eksik."}), 200

    try:
        data = request.get_json()
        user_query = data.get("query", "")
        image_base64 = data.get("image", None)

        if not user_query and not image_base64:
            return jsonify({"error": "Lütfen bir metin yazın veya fotoğraf yükleyin."}), 400

        prompt = f"""
        Sen uzman bir parfüm danışmanısın. Aşağıda Sare Perfume mağazasındaki ürünlerin kataloğu var:
        
        {PERFUME_CATALOG_TEXT}
        
        Görev: Müşterinin isteğini veya yüklediği fotoğrafı analiz et. Yukarıdaki katalogdan en uygun 3 parfümü seç.
        
        Yanıtını SADECE AŞAĞIDAKİ JSON formatında ver. Başka hiçbir şey yazma:
        {{
            "recommendations": [
                {{
                    "kimlik": "Seçtiğin parfümün KİMLİK (Handle) değeri",
                    "aciklama": "Müşteriye bu parfümü neden önerdiğini anlatan 1-2 cümlelik şık, pazarlama odaklı sunum."
                }}
            ]
        }}
        """

        content_parts = [prompt]
        
        if image_base64:
            if "," in image_base64:
                header, image_data_str = image_base64.split(",", 1)
            else:
                image_data_str = image_base64
            image_bytes = base64.b64decode(image_data_str)
            content_parts.append(types.Part.from_bytes(data=image_bytes, mime_type='image/jpeg'))

        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=content_parts,
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        
        clean_response = response.text.replace("```json", "").replace("```", "").strip()
        gemini_data = json.loads(clean_response)
        
        # Yapay zekanın seçtiği parfümlerin resimlerini ve linklerini hafızadan çekip birleştir
        final_results = []
        for rec in gemini_data.get("recommendations", []):
            handle = rec.get("kimlik", "")
            if handle in PRODUCT_DB:
                product_info = PRODUCT_DB[handle]
                final_results.append({
                    "title": product_info["title"],
                    "url": product_info["url"],
                    "image": product_info["image"],
                    "description": rec.get("aciklama", "")
                })
                
        return jsonify({"recommendations": final_results})
        
    except Exception as e:
        return jsonify({"error": f"Sistem Hatası: {str(e)}"}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
