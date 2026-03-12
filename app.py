
import os
import csv
import json
import base64
import re
import logging
from flask import Flask, request, jsonify
from flask_cors import CORS
import google.generativeai as genai

# Logging yapılandırması - Düzeltildi
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)
CORS(app)

# --- Yapılandırma Değişkenleri ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
CSV_FILE_NAME = 'products_export_1 (2).csv'
PLACEHOLDER_IMAGE_URL = "https://via.placeholder.com/150?text=Sare+Perfume"
PRODUCT_BASE_URL = "https://sareperfume.com/products/"

# Gemini API istemcisini başlat
model = None
if not GEMINI_API_KEY:
    logging.error("GEMINI_API_KEY ortam değişkeni ayarlanmamış. API servisi kullanılamayacak.")
else:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-1.5-flash') # Modeli burada başlatıyoruz
        logging.info("Gemini API istemcisi başarıyla başlatıldı.")
    except Exception as e:
        logging.error(f"Gemini API istemcisi başlatılırken hata oluştu: {e}")

# --- Katalog ve Resimleri Hafızaya Al --- (Uygulama başlangıcında bir kez yüklenir)
PERFUME_CATALOG_TEXT = ""
PRODUCT_DB = {}

def clean_html(raw_html: str) -> str:
    if not raw_html:
        return ""
    cleanr = re.compile('<.*?>')
    cleantext = re.sub(cleanr, ' ', raw_html)
    return re.sub(r'\s+', ' ', cleantext).strip()

def load_product_data():
    global PERFUME_CATALOG_TEXT, PRODUCT_DB
    # Vercel'in geçici dosya sisteminde çalışabilmesi için dosya yolunu göreceli yapıyoruz
    csv_path = os.path.join(os.path.dirname(__file__), CSV_FILE_NAME)
    
    catalog_lines = []
    temp_product_db = {}

    if not os.path.exists(csv_path):
        logging.error(f"CSV dosyası bulunamadı: {csv_path}")
        PERFUME_CATALOG_TEXT = f"HATA: Katalog dosyası bulunamadı: {CSV_FILE_NAME}"
        return

    try:
        with open(csv_path, mode='r', encoding='utf-8-sig') as file:
            reader = csv.DictReader(file)
            for row in reader:
                title = row.get('Title', '').strip()
                if not title:
                    continue
                
                handle = row.get('Handle', '').strip()
                body = clean_html(row.get('Body (HTML)', ''))
                tags = row.get('Tags', '').strip()
                image = row.get('Image Src', '').strip()
                
                if handle not in temp_product_db:
                    temp_product_db[handle] = {
                        "title": title,
                        "image": image if image else PLACEHOLDER_IMAGE_URL,
                        "url": f"{PRODUCT_BASE_URL}{handle}"
                    }
                    
                    line = f"KİMLİK: {handle} | İSİM: {title} | ETİKETLER: {tags} | DETAY: {body[:300]}"
                    catalog_lines.append(line)
        
        PERFUME_CATALOG_TEXT = "\n".join(catalog_lines)
        PRODUCT_DB = temp_product_db
        logging.info(f"Ürün kataloğu başarıyla yüklendi. {len(PRODUCT_DB)} ürün bulundu.")

    except Exception as e:
        logging.error(f"Katalog yüklenirken beklenmeyen bir hata oluştu: {e}")
        PERFUME_CATALOG_TEXT = f"HATA: Katalog yüklenemedi. {str(e)}"

# Uygulama başlangıcında verileri yükle
load_product_data()

@app.route("/", defaults={'path': ''})
@app.route("/<path:path>")
def catch_all(path):
    if not model:
        logging.error("Gemini API istemcisi kullanılamıyor. API anahtarı eksik veya başlatma hatası.")
        return jsonify({"error": "Sistem Hatası: API Anahtarı eksik veya servis kullanılamıyor."}), 500

    if request.method == 'POST':
        try:
            data = request.get_json()
            if not data:
                return jsonify({"error": "Geçersiz JSON formatı veya boş istek gövdesi."}), 400

            user_query = data.get("query", "").strip()
            image_base64 = data.get("image", None)

            if not user_query and not image_base64:
                return jsonify({"error": "Lütfen bir metin yazın veya fotoğraf yükleyin."}), 400

            prompt_template = f"""
            Sen dünyaca ünlü, insan psikolojisinden ve görünümünden çok iyi anlayan elit bir koku uzmanısın (Master Perfumer).
            Aşağıda Sare Perfume mağazasındaki ürünlerin kataloğu var:
            
            {PERFUME_CATALOG_TEXT}
            
            Görev: 
            1. Müşterinin yazdığı metni veya yüklediği fotoğrafı ÇOK DERİNLEMESİNE analiz et. 
            2. Eğer bir fotoğraf varsa; kişinin mesleğini, giyim tarzını, fiziksel özelliklerini ve ortamın enerjisini anla.
            3. Bu detaylı analize göre katalogdan onun karakterine en kusursuz uyacak 3 parfümü seç.
            
            Yanıtını SADECE AŞAĞIDAKİ JSON formatında ver. Başka hiçbir şey yazma:
            {{"recommendations": [
                {{"kimlik": "Seçtiğin parfümün KİMLİK (Handle) değeri", "aciklama": "Bu parfümü NEDEN seçtiğini kişiye özel, 2-3 cümlelik çok etkileyici bir analizle yaz."}}
            ]}}
            """
            
            content_parts = [prompt_template]
            
            if user_query:
                content_parts.append(f"Müşteri Sorgusu: {user_query}")

            if image_base64:
                try:
                    if "," in image_base64:
                        header, image_data_str = image_base64.split(",", 1)
                    else:
                        image_data_str = image_base64
                    image_bytes = base64.b64decode(image_data_str)
                    content_parts.append({'mime_type': 'image/jpeg', 'data': image_bytes})
                except Exception as e:
                    logging.error(f"Base64 resim çözümlenirken hata oluştu: {e}")
                    return jsonify({"error": "Geçersiz resim formatı."}), 400

            response = model.generate_content(content_parts)
            
            clean_response = response.text.replace("```json", "").replace("```", "").strip()
            gemini_data = json.loads(clean_response)
            
            final_results = []
            recommendations = gemini_data.get("recommendations", [])
            if isinstance(recommendations, list):
                for rec in recommendations:
                    handle = rec.get("kimlik", "").strip()
                    if handle and handle in PRODUCT_DB:
                        product_info = PRODUCT_DB[handle]
                        final_results.append({
                            "title": product_info["title"],
                            "url": product_info["url"],
                            "image": product_info["image"],
                            "description": rec.get("aciklama", "").strip()
                        })
                    else:
                        logging.warning(f"Gemini tarafından önerilen 'kimlik' ({handle}) katalogda bulunamadı.")
            
            return jsonify({"recommendations": final_results})
            
        except Exception as e:
            logging.error(f"Beklenmeyen bir hata oluştu: {e}", exc_info=True)
            return jsonify({"error": f"Sistem Hatası: Beklenmeyen bir sorun oluştu. Detay: {str(e)}"}), 500
    else:
        return "Parfüm öneri API'sine hoş geldiniz! Lütfen POST isteği gönderin."

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)
