'''
Parfüm Akıllı Eşleştirme Sistemi v2
Sentence-Transformers (çok dilli) + GPT-4.1-mini kullanarak
müşteri sorgularını en uygun parfümle eşleştirir.

Mimari:
- Embedding: paraphrase-multilingual-MiniLM-L12-v2 (Türkçe destekli, ücretsiz)
- Sorgu zenginleştirme: GPT-4.1-mini
- Benzerlik: Kosinüs benzerliği
- Üretim için: Gemini text-embedding-004 ile değiştirilebilir
'''

import pandas as pd
import numpy as np
import os
import pickle
import warnings
warnings.filterwarnings('ignore')

from sentence_transformers import SentenceTransformer
from openai import OpenAI

client = OpenAI()

# Dosya yolları, bu script'in bulunduğu dizine göre ayarlandı
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EMBEDDINGS_FILE = os.path.join(BASE_DIR, 'parfum_embeddings_v2.pkl')
DATA_FILE = os.path.join(BASE_DIR, 'parfum_zenginlestirilmis.csv')

# Çok dilli embedding modeli (Türkçe için optimize)
print("Embedding modeli yükleniyor...")
EMBEDDING_MODEL = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
print("✓ Model hazır")

def create_perfume_description(row):
    """Her parfüm için zengin bir metin açıklaması oluştur."""
    parts = [f"Parfüm: {row['Parfüm Adı']}"]
    
    for field, label in [
        ('Cinsiyet', 'Cinsiyet'),
        ('koku_ailesi', 'Koku ailesi'),
        ('bas_notalar', 'Baş notalar'),
        ('kalp_notalar', 'Kalp notalar'),
        ('dip_notalar', 'Dip notalar'),
        ('mevsim', 'Mevsim'),
        ('gunun_zamani', 'Gün zamanı'),
        ('ortam', 'Ortam'),
        ('kiyafet_stili', 'Kıyafet stili'),
        ('koku_yogunlugu', 'Yoğunluk'),
        ('duygusal_etiketler', 'Duygusal etiketler'),
        ('aciklama_tr', 'Açıklama'),
    ]:
        val = str(row.get(field, '')).strip()
        if val and val != 'nan':
            parts.append(f"{label}: {val}")
    
    return ". ".join(parts)

def build_embedding_database():
    """Tüm parfümler için embedding vektörleri oluştur."""
    print("Parfüm veri tabanı yükleniyor...")
    df = pd.read_csv(DATA_FILE, encoding='utf-8-sig')
    print(f"Toplam {len(df)} parfüm bulundu")
    
    records = []
    descriptions = []
    
    for _, row in df.iterrows():
        desc = create_perfume_description(row)
        descriptions.append(desc)
        records.append({
            'Kodu': str(row['Kodu']),
            'Parfüm Adı': str(row['Parfüm Adı']),
            'Cinsiyet': str(row.get('Cinsiyet', 'Unisex')),
            'koku_ailesi': str(row.get('koku_ailesi', '')),
            'mevsim': str(row.get('mevsim', '')),
            'ortam': str(row.get('ortam', '')),
            'kiyafet_stili': str(row.get('kiyafet_stili', '')),
            'koku_yogunlugu': str(row.get('koku_yogunlugu', '')),
            'duygusal_etiketler': str(row.get('duygusal_etiketler', '')),
            'bas_notalar': str(row.get('bas_notalar', '')),
            'kalp_notalar': str(row.get('kalp_notalar', '')),
            'dip_notalar': str(row.get('dip_notalar', '')),
            'aciklama_tr': str(row.get('aciklama_tr', '')),
            'description': desc
        })
    
    print("Embedding vektörleri hesaplanıyor...")
    embeddings = EMBEDDING_MODEL.encode(descriptions, show_progress_bar=True, batch_size=32)
    
    data = {
        'embeddings': embeddings,
        'records': records
    }
    
    with open(EMBEDDINGS_FILE, 'wb') as f:
        pickle.dump(data, f)
    
    print(f"✓ {len(records)} parfüm embedding'i kaydedildi")
    return data

def load_embedding_database():
    """Kaydedilmiş embedding veri tabanını yükle."""
    if not os.path.exists(EMBEDDINGS_FILE):
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
    prompt = f"""Kullanıcı şunu söylüyor: \"{user_input}\"

Bu ifadeyi parfüm arama için zenginleştir. Şunları belirt:
- Ortam/durum (kumsal, ofis, gece kulübü, vb.)
- Uygun koku notaları (taze, çiçeksi, odunsu, oryantal, narenciye, vb.)
- Mevsim (yaz, kış, ilkbahar, sonbahar)
- Yoğunluk (hafif, orta, yoğun)
- Duygusal ton (romantik, enerjik, sakin, güçlü, vb.)

Sadece zenginleştirilmiş arama metnini yaz (2-3 cümle Türkçe), başka hiçbir şey ekleme."""

    try:
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": "Sen bir parfüm uzmanısın. Kullanıcı girdilerini parfüm arama sorgularına dönüştürürsün."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=200
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
            cinsiyet = record['Cinsiyet'].strip()
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
                'Ürün Kodu': record['Kodu'],
                'Parfüm Adı': record['Parfüm Adı'],
                'Cinsiyet': record['Cinsiyet'],
                'Benzerlik Skoru': round(float(similarities[idx]) * 100, 1),
                'Koku Ailesi': record.get('koku_ailesi', ''),
                'Mevsim': record.get('mevsim', ''),
                'Ortam': record.get('ortam', ''),
                'Kıyafet Stili': record.get('kiyafet_stili', ''),
                'Yoğunluk': record.get('koku_yogunlugu', ''),
                'Baş Notalar': record.get('bas_notalar', ''),
                'Kalp Notalar': record.get('kalp_notalar', ''),
                'Dip Notalar': record.get('dip_notalar', ''),
                'Açıklama': record.get('aciklama_tr', '')
            })
    
    return results

def smart_perfume_advisor(user_input, db_data, gender_filter=None, use_gpt_enrichment=True):
    """
    Akıllı parfüm danışmanı ana fonksiyonu.
    """
    if use_gpt_enrichment:
        enriched_query = enrich_query_with_gpt(user_input)
    else:
        enriched_query = user_input
    
    matches = find_best_matches(enriched_query, db_data, top_k=5, gender_filter=gender_filter)
    return matches, enriched_query
'''
