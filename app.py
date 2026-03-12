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
    print("UYARI: GEMINI_API_KEY bulunamadı! Vercel ayarlarına ekleyin.")

# --- PARFÜM KATALOĞUNU HAFIZAYA AL (Tüy gibi hafif) ---
PERFUME_CATALOG = ""
try:
    with open('parfum_zenginlestirilmis.csv', mode='r', encoding='utf-8-sig') as file:
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
        print(f"✓ {len(catalog_lines)} parfüm tüy gibi hafif şekilde belleğe yüklendi.")
except Exception as e:
    print(f"Katalog yüklenirken hata oluştu: {e}")

# --- ANA MOTOR (MULTIMODAL) ---
@app.route("/recommend", methods=["POST"])
def recommend():
    data = request.get_json()
    user_query = data.get("query", "") # Yazı
    image_base64 = data.get("image", None) # Fotoğraf (base64)

    if not user_query and not image_base64:
        return jsonify({"error": "Sorgu boş olamaz (Yazı veya fotoğraf gereklidir)."}), 400

    print(f"Müşteri arıyor: Yazı: '{user_query[:50]}...', Fotoğraf: {'Var' if image_base64 else 'Yok'}")

    # Gemini'ye gönderilecek talimat
    prompt = f"""
    Sen uzman bir parfüm danışmanısın. Aşağıda Sare Perfume mağazasındaki parfümlerin kataloğu var:
    
    {PERFUME_CATALOG}
    
    Görev: Müşterinin verdiği bilgileri (ister yazı ister fotoğraf olsun) analiz et. 
    Fotoğraf varsa, şişenin şeklini, rengini veya fotoğraftaki objelerin (kumsal, elbise, vs.) hissiyatını anla.
    Mağazadaki kataloğumuzdan bu hissiyata ve isteğe en uygun 3 parfümü seç.
    
    Yanıtını aşağıdaki JSON formatında ver:
    {{
        "analysis_summary": "Kullanıcının isteği/fotoğrafının kısa analizi",
        "recommendations": [
            {{
                "Ürün Kodu": "Parfüm kodu",
                "Parfüm Adı": "Parfüm adı",
                "Cinsiyet": "Cinsiyeti",
                "Koku Ailesi": "Ailesi",
                "Mevsim": "Uygun Mevsim",
                "Ortam": "Uygun Ortam",
                "Açıklama": "Müşteriye bu parfümü neden önerdiğini anlatan 1-2 cümlelik şık, profesyonel bir sunum."
            }}
        ]
    }}
    """

    # Model içeriği hazırla
    content = [prompt]
    
    # Fotoğraf varsa, base64'ü Gemini formatına çevir
    if image_base64:
        # base64'ün başındaki 'data:image/png;base64,' kısmını temizle
        if "," in image_base64:
            header, image_data = image_base64.split(",", 1)
        else:
            image_data = image_base64
            
        content.append({
            "mime_type": "image/jpeg", # veya png, flash otomatik anlar
            "data": image_data
        })

    try:
        model = genai.GenerativeModel('gemini-1.5-flash', generation_config={"response_mime_type": "application/json"})
        response = model.generate_content(content)
        result_json = json.loads(response.text)
        return jsonify(result_json)
    except Exception as e:
        print(f"Gemini API Hatası: {e}")
        return jsonify({"error": "Sistemde anlık bir yoğunluk var, lütfen tekrar deneyin."}), 500

@app.route("/")
def health_check():
    return "Sare Perfume Akıllı Koku Danışmanı (Gemini API Altyapısı) - Canlı ve Tüy Gibi Hafif!"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
