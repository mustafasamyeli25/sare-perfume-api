#!/usr/bin/env python3
"""
Sare Perfume - Akıllı Koku Danışmanı API Sunucusu

Bu Flask sunucusu, Shopify mağazası için bir API endpoint sağlar.
Kullanıcı sorgularını alır, embedding sistemiyle en iyi parfümleri bulur
ve sonuçları JSON formatında döndürür.

Endpoint: /recommend
Method: POST
JSON Body: {
    "query": "Kullanıcının yazdığı metin",
    "gender": "Erkek" | "Kadın" | "Hepsi"
}
"""

import os
import warnings
from flask import Flask, request, jsonify
from flask_cors import CORS

# Uyarıları bastır
warnings.filterwarnings("ignore")

# Embedding sistemini import et
# Bu dosyanın aynı dizinde olduğundan emin olun
import parfum_embedding_v2 as perfume_system

app = Flask(__name__)

# Geliştirme ortamında tüm kaynaklardan gelen isteklere izin ver
CORS(app)

# --- VERİ TABANINI YÜKLE ---
# Sunucu başladığında embedding veritabanını bir kere yükle
print("Akıllı Koku Danışmanı API başlatılıyor...")
DB_DATA = None
try:
    DB_DATA = perfume_system.load_embedding_database()
    print("✓ API kullanıma hazır!")
except Exception as e:
    print(f"HATA: Embedding veritabanı yüklenemedi: {e}")
    print("Lütfen 'parfum_zenginlestirilmis.csv' ve 'parfum_embeddings_v2.pkl' dosyalarının mevcut olduğundan emin olun.")


@app.route("/recommend", methods=["POST"])
def recommend():
    """Parfüm önerisi yapan ana API endpointi."""
    if not DB_DATA:
        return jsonify({"error": "Sistem hazır değil, lütfen sunucu loglarını kontrol edin."}), 500

    data = request.get_json()
    if not data or "query" not in data:
        return jsonify({"error": "'query' alanı zorunludur."}), 400

    user_query = data["query"]
    gender_filter = data.get("gender", "Hepsi") # Varsayılan 'Hepsi'

    if not user_query:
        return jsonify({"error": "Sorgu boş olamaz."}), 400

    print(f"Gelen sorgu: '{user_query}', Cinsiyet: {gender_filter}")

    try:
        # Akıllı danışmanı çalıştır (GPT zenginleştirmesi ile)
        matches, enriched_query = perfume_system.smart_perfume_advisor(
            user_input=user_query,
            db_data=DB_DATA,
            gender_filter=gender_filter,
            use_gpt_enrichment=True
        )

        response = {
            "enriched_query": enriched_query,
            "recommendations": matches
        }

        return jsonify(response)

    except Exception as e:
        print(f"İşlem sırasında hata: {e}")
        return jsonify({"error": "Öneri yapılırken bir sunucu hatası oluştu."}), 500


@app.route("/")
def health_check():
    """Sunucunun ayakta olup olmadığını kontrol etmek için basit bir endpoint."""
    status = "Hazır" if DB_DATA else "Başlatılıyor"
    return f"Sare Perfume Akıllı Koku Danışmanı API - Durum: {status}"


if __name__ == "__main__":
    # Geliştirme sunucusu. Üretim ortamı için Gunicorn gibi bir WSGI sunucusu kullanın.
    # Örnek: gunicorn --workers=1 --threads=4 --bind 0.0.0.0:8080 app:app
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=True)
