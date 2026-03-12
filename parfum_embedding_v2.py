import pandas as pd
import numpy as np
import json
import os
import pickle
import warnings
from sentence_transformers import SentenceTransformer
from openai import OpenAI

# OpenAI Ayarı (Render ayarlarından çekecek)
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# Dosya yolları
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EMBEDDINGS_FILE = os.path.join(BASE_DIR, 'parfum_embeddings_v2.pkl')
DATA_FILE = os.path.join(BASE_DIR, 'parfum_zenginlestirilmis.csv')

# Çok dilli embedding modeli (Türkçe için optimize)
print("Embedding modeli yükleniyor...")
EMBEDDING_MODEL = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
print("✓ Model hazır")

def create_perfume_description(row):
    """Her parfüm için zengin bir metin açıklaması oluştur."""
    parts = [f"Parfüm: {row.get('Parfüm Adı', '')}"]
    
    if pd.notna(row.get('Koku Ailesi')):
        parts.append(f"Koku Ailesi: {row['Koku Ailesi']}")
    
    if pd.notna(row.get('Üst Notalar')):
        parts.append(f"Üst Notalar: {row['Üst Notalar']}")
    if pd.notna(row.get('Orta Notalar')):
        parts.append(f"Orta Notalar: {row['Orta Notalar']}")
    if pd.notna(row.get('Alt Notalar')):
        parts.append(f"Alt Notalar: {row['Alt Notalar']}")
        
    if pd.notna(row.get('Mevsim')):
        parts.append(f"Uygun Mevsim: {row['Mevsim']}")
    if pd.notna(row.get('Ortam')):
        parts.append(f"Kullanım Ortamı: {row['Ortam']}")
        
    if pd.notna(row.get('Açıklama')):
        parts.append(f"Açıklama: {row['Açıklama']}")

    return ". ".join(parts)

def build_embedding_database():
    """Tüm parfümler için embedding vektörleri oluştur."""
    print("Parfüm veri tabanı yükleniyor...")
    df = pd.read_csv(DATA_FILE)
    
    records = []
    texts_to_embed = []
    
    for _, row in df.iterrows():
        record = row.to_dict()
        desc = create_perfume_description(row)
        
        records.append(record)
        texts_to_embed.append(desc)
        
    print(f"{len(texts_to_embed)} parfüm için embedding hesaplanıyor...")
    embeddings = EMBEDDING_MODEL.encode(texts_to_embed, show_progress_bar=True)
    
    data = {
        'records': records,
        'embeddings': embeddings
    }
    
    with open(EMBEDDINGS_FILE, 'wb') as f:
        pickle.dump(data, f)
        
    print(f"✓ {len(records)} parfüm embedding'i kaydedildi")
    return data

def load_embedding_database():
    """Kaydedilmiş embedding veri tabanını yükle."""
    if not os.path.exists(EMBEDDINGS_FILE):
        print("HATA: Embedding dosyası bulunamadı, baştan oluşturuluyor...")
        return build_embedding_database()
        
    with open(EMBEDDINGS_FILE, 'rb') as f:
        data = pickle.load(f)
    print(f"✓ {len(data['records'])} parfüm embedding'i yüklendi")
    return data

def cosine_similarity_matrix(query_vec, matrix):
    """Sorgu vektörü ile tüm parfüm vektörleri arasındaki benzerliği hesapla."""
    query_norm = query_vec / (np.linalg.norm(query_vec) + 1e-10)
    matrix_norm = matrix / (np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-10)
    return np.dot(matrix_norm, query_norm)

def enrich_query_with_gpt(user_input):
    """GPT ile kullanıcı sorgusunu parfüm arama için zenginleştir."""
    prompt = f"""Kullanıcı şunu söylüyor: "{user_input}"

Bu ifadeyi parfüm arama için zenginleştir. Şunları belirt:
- Ortam/durum (kumsal, ofis, gece kulübü, vb.)
- Koku ailesi (odunsu, çiçeksi, ferah, baharatlı, vb.)
- Hissiyat (enerjik, romantik, gizemli, vb.)

Sadece 1-2 cümlelik zenginleştirilmiş arama metni döndür, ekstra açıklama yapma."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Sen uzman bir parfüm danışmanısın. Kullanıcı sorgusunu teknik parfüm notalarına ve hissiyatına çeviriyorsun."},
                {"role": "user", "content": prompt}
            ]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"GPT zenginleştirme hatası: {e}")
        return user_input

def find_best_matches(query, db_data, top_k=5, gender_filter=None):
    """En uygun parfümleri bul."""
    query_embedding = EMBEDDING_MODEL.encode([query])[0]
    
    embeddings = db_data['embeddings']
    records = db_data['records']
    
    similarities = cosine_similarity_matrix(query_embedding, embeddings)

    if gender_filter and gender_filter != 'Hepsi':
        for i, record in enumerate(records):
            cinsiyet = str(record.get('Cinsiyet', '')).strip()
            if gender_filter == 'Erkek' and cinsiyet not in ['Erkek', 'Unisex']:
                similarities[i] = -1
            elif gender_filter == 'Kadın' and cinsiyet not in ['Kadın', 'Unisex']:
                similarities[i] = -1

    top_indices = np.argsort(similarities)[::-1][:top_k]

    results = []
    for idx in top_indices:
        if similarities[idx] > 0:
            record = records[idx]
            results.append({
                'Ürün Kodu': record.get('Ürün Kodu', record.get('Benim Kodum', '')),
                'Parfüm Adı': record.get('Parfüm Adı', record.get('Orijinal Ad', '')),
                'Benzerlik Skoru': round(float(similarities[idx]) * 100, 1),
                'Cinsiyet': record.get('Cinsiyet', ''),
                'Koku Ailesi': record.get('Koku Ailesi', ''),
                'Mevsim': record.get('Mevsim', ''),
                'Ortam': record.get('Ortam', ''),
                'Açıklama': record.get('Açıklama', '')
            })

    return results

def smart_perfume_advisor(user_input, db_data, gender_filter=None, use_gpt_enrichment=True):
    """Akıllı parfüm danışmanı ana fonksiyonu."""
    if use_gpt_enrichment:
        enriched_query = enrich_query_with_gpt(user_input)
    else:
        enriched_query = user_input

    matches = find_best_matches(enriched_query, db_data, top_k=5, gender_filter=gender_filter)
    return matches, enriched_query

if __name__ == "__main__":
    print("Sare Perfume - Akıllı Koku Danışmanı Modülü")
