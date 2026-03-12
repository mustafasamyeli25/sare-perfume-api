import os
import csv
import json
import base64
from flask import Flask, request, jsonify
from flask_cors import CORS
import google.generativeai as genai

app = Flask(__name__)
CORS(app)

# --- GEMINI API AYARI ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
else:
    print("UYARI: GEMINI_API_KEY bulunamadı!")

# --- PARFÜM KATALOĞUNU HAFIZAYA AL (Vercel Uyumlu Dosya Yolu) ---
PERFUME_CATALOG = ""
try:
    # Dosyanın Vercel'de tam nerede olduğunu bul
    current_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(current_dir, 'parfum_zenginlestirilmis.csv')
    
    with open(csv_path, mode='r', encoding='utf-8-sig') as file:
        reader = csv.DictReader(file)
        catalog_lines = []
        for row in reader:
            kod = row.get('Benim Kodum', row.get('Ürün Kodu', ''))
            isim = row.get('Orijinal Ad', row.get('Parfüm Adı', ''))
            cinsiyet = row.get('Cinsiyet', '')
            ailesi = row.get('Koku Ailesi', '')
            notalar = f"Üst: {row.get('Üst Notalar','')}, Orta: {row.get('Orta Notalar','')}, Alt: {row.get('Alt Notalar','')}"
            mevsim = row.get('Mevsim', '')
            ortam = row.get('Ortam', '')
            line = f"KOD: {kod} | İSİM: {isim} | CİNSİYET: {cinsiyet} | AİLE: {ailesi} | NOTALAR: {notalar} | MEVSİM: {mevsim} | ORTAM: {ortam}"
            catalog_lines.append(line)
        PERFUME_CATALOG = "\n".join(catalog_lines)
except Exception as e:
    PERFUME_CATALOG = f"HATA: Katalog okunamadı. Detay: {str(e)}"

# --- ANA MOTOR (MULTIMODAL) ---
@app.route("/recommend", methods=["POST"])
def recommend():
    try:
        data = request.get_json()
        user_query = data.get("query", "")
        image_base64 = data.get("image", None)

        if not user_query and not image_base64:
            return jsonify({"error": "Lütfen bir metin yazın veya fotoğraf yükleyin."}), 400

        prompt = f"""
        Sen uzman bir parfüm danışmanısın. Aşağıda Sare Perfume mağazasındaki parfümlerin kataloğu var:
        
        {PERFUME_CATALOG}
        
        Görev: Müşterinin verdiği bilgileri (ister yazı ister fotoğraf olsun) analiz et.
        Mağazadaki kataloğumuzdan bu isteğe en uygun 3 parfümü seç.
        
        Yanıtını SADECE AŞAĞIDAKİ JSON FORMATINDA ver. Başına veya sonuna ```json gibi işaretler KOYMA:
        {{
            "recommendations": [
                {{
                    "Ürün Kodu": "Parfüm kodu",
                    "Parfüm Adı": "Parfüm adı",
                    "Cinsiyet": "Cinsiyeti",
                    "Koku Ailesi": "Ailesi",
                    "Mevsim": "Uygun Mevsim",
                    "Ortam": "Uygun Ortam",
                    "Açıklama": "Müşteriye bu parfümü neden önerdiğini anlatan 1-2 cümlelik şık bir sunum."
                }}
            ]
        }}
        """

        content = [prompt]
        
        if image_base64:
            if "," in image_base64:
                header, image_data = image_base64.split(",", 1)
            else:
                image_data = image_base64
                
            content.append({
                "mime_type": "image/jpeg",
                "data": image_data
            })

        model = genai.GenerativeModel('gemini-1.5-flash', generation_config={"response_mime_type": "application/json"})
        response = model.generate_content(content)
        
        # Gemini'nin olası markdown (```json) işaretlerini zorla temizle
        clean_response = response.text.replace("```json", "").replace("```", "").strip()
        
        result_json = json.loads(clean_response)
        return jsonify(result_json)
        
    except Exception as e:
        # Hata olursa artık 500 dönüp gizlemeyeceğiz, hatanın adını ekrana yansıtacağız!
        return jsonify({"error": f"Sistem Hatası: {str(e)}"}), 200

@app.route("/")
def health_check():
    return "Sare Perfume API - Aktif!"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
