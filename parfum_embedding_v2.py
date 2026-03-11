#!/usr/bin/env python3
"""
Parfüm Akıllı Eşleştirme Sistemi v2
Sentence-Transformers (çok dilli) + GPT-4.1-mini kullanarak
müşteri sorgularını en uygun parfümle eşleştirir.

Mimari:
- Embedding: paraphrase-multilingual-MiniLM-L12-v2 (Türkçe destekli, ücretsiz)
- Sorgu zenginleştirme: GPT-4.1-mini
- Benzerlik: Kosinüs benzerliği
- Üretim için: Gemini text-embedding-004 ile değiştirilebilir
"""

import pandas as pd
import numpy as np
import json
import os
import pickle
import warnings
warnings.filterwarnings('ignore')

from sentence_transformers import SentenceTransformer
from openai import OpenAI

client = OpenAI()

EMBEDDINGS_FILE = '/home/ubuntu/upload/parfum_embeddings_v2.pkl'
DATA_FILE = '/home/ubuntu/upload/parfum_zenginlestirilmis.csv'

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
    prompt = f"""Kullanıcı şunu söylüyor: "{user_input}"

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
    # Sorgu embedding'i
    query_embedding = EMBEDDING_MODEL.encode([query])[0]
    
    embeddings = db_data['embeddings']
    records = db_data['records']
    
    # Tüm benzerlikler
    similarities = cosine_similarity_matrix(query_embedding, embeddings)
    
    # Cinsiyet filtresi uygula
    if gender_filter and gender_filter != 'Hepsi':
        for i, record in enumerate(records):
            cinsiyet = record['Cinsiyet'].strip()
            if gender_filter == 'Erkek' and cinsiyet not in ['Erkek', 'Unisex']:
                similarities[i] = -1
            elif gender_filter == 'Kadın' and cinsiyet not in ['Kadın', 'Unisex']:
                similarities[i] = -1
    
    # En yüksek benzerlikli indeksler
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
    
    Args:
        user_input: Kullanıcının metin/duygu girişi
        db_data: Embedding veri tabanı
        gender_filter: 'Erkek', 'Kadın', 'Unisex', 'Hepsi' veya None
        use_gpt_enrichment: GPT ile sorgu zenginleştirme kullanılsın mı
    
    Returns:
        (matches, enriched_query) tuple
    """
    if use_gpt_enrichment:
        enriched_query = enrich_query_with_gpt(user_input)
    else:
        enriched_query = user_input
    
    matches = find_best_matches(enriched_query, db_data, top_k=5, gender_filter=gender_filter)
    return matches, enriched_query


def run_demo_tests(db_data):
    """Demo test sorguları."""
    test_cases = [
        ("Kumsalda ferah bir akşam", None),
        ("Romantik gece yemeği, zarif ve çekici", "Kadın"),
        ("Ofis için hafif, profesyonel bir koku", "Erkek"),
        ("Kışın sıcak ve samimi, odunsu", None),
        ("Taze ve enerjik, spor sonrası", "Erkek"),
        ("Çiçekli bahar bahçesi, hafif ve neşeli", "Kadın"),
        ("Derin ve gizemli, gece kulübü", None),
        ("Düğün için özel, unutulmaz", "Kadın"),
        ("Doğa yürüyüşü, yeşil ve taze", None),
        ("Şeker ve vanilya, tatlı ve sıcak", None),
    ]
    
    print("\n" + "="*80)
    print("AKILLI KOKU DANIŞMANI - DEMO TEST SONUÇLARI")
    print("="*80)
    
    all_results = []
    
    for query, gender in test_cases:
        print(f"\n🔍 Sorgu: '{query}'")
        if gender:
            print(f"   Cinsiyet filtresi: {gender}")
        
        matches, enriched = smart_perfume_advisor(query, db_data, gender)
        
        print(f"   Zenginleştirilmiş: {enriched[:80]}...")
        print(f"\n   Top 5 Öneri:")
        
        for i, m in enumerate(matches, 1):
            print(f"   {i}. [{m['Ürün Kodu']}] {m['Parfüm Adı']}")
            print(f"      Benzerlik: %{m['Benzerlik Skoru']} | {m['Cinsiyet']} | {m['Koku Ailesi']}")
            if i == 1:
                print(f"      Mevsim: {m['Mevsim']}")
                print(f"      Ortam: {m['Ortam']}")
                print(f"      Açıklama: {m['Açıklama'][:80]}...")
        
        all_results.append({
            'Sorgu': query,
            'Cinsiyet Filtresi': gender or 'Hepsi',
            'Zenginleştirilmiş Sorgu': enriched,
            '1. Öneri Kodu': matches[0]['Ürün Kodu'] if matches else '',
            '1. Öneri Adı': matches[0]['Parfüm Adı'] if matches else '',
            '1. Benzerlik': matches[0]['Benzerlik Skoru'] if matches else 0,
            '2. Öneri Kodu': matches[1]['Ürün Kodu'] if len(matches) > 1 else '',
            '2. Öneri Adı': matches[1]['Parfüm Adı'] if len(matches) > 1 else '',
            '3. Öneri Kodu': matches[2]['Ürün Kodu'] if len(matches) > 2 else '',
            '3. Öneri Adı': matches[2]['Parfüm Adı'] if len(matches) > 2 else '',
        })
    
    # Kaydet
    df_results = pd.DataFrame(all_results)
    df_results.to_csv('/home/ubuntu/upload/demo_test_sonuclari.csv', index=False, encoding='utf-8-sig')
    print(f"\n✓ Sonuçlar kaydedildi: /home/ubuntu/upload/demo_test_sonuclari.csv")
    
    return all_results


if __name__ == "__main__":
    print("="*60)
    print("SARE PERFUME - AKILLI KOK DANIŞMANI SİSTEMİ")
    print("="*60)
    
    # Veri tabanını oluştur
    db_data = build_embedding_database()
    
    # Demo testleri çalıştır
    results = run_demo_tests(db_data)
    
    print("\n" + "="*60)
    print(f"✓ Sistem hazır! {len(db_data['records'])} parfüm indekslendi.")
    print("="*60)
