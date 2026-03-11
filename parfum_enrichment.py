#!/usr/bin/env python3
"""
Parfüm veri zenginleştirme scripti.
GPT-4.1-mini kullanarak 461 parfümün koku notaları, mevsim ve stil bilgilerini doldurur.
"""

import pandas as pd
import json
import time
import os
from openai import OpenAI

client = OpenAI()

def enrich_perfume_batch(perfumes_batch):
    """Bir grup parfümü GPT ile zenginleştir."""
    
    perfume_list = "\n".join([f"{i+1}. {p['Parfüm Adı']} ({p['Cinsiyet']})" 
                               for i, p in enumerate(perfumes_batch)])
    
    prompt = f"""Sen bir parfüm uzmanısın. Aşağıdaki {len(perfumes_batch)} parfüm için detaylı bilgi ver.
Her parfüm için JSON formatında şu bilgileri doldur:

Parfümler:
{perfume_list}

Her parfüm için şu alanları doldur:
- bas_notalar: Baş notalar (ilk 15 dakika hissedilen, virgülle ayrılmış)
- kalp_notalar: Kalp notalar (30 dk - 2 saat arası, virgülle ayrılmış)
- dip_notalar: Dip notalar (uzun süre kalan, virgülle ayrılmış)
- mevsim: En uygun mevsimler (İlkbahar/Yaz/Sonbahar/Kış, virgülle ayrılmış)
- gunun_zamani: Gündüz/Gece/Her İkisi
- ortam: Uygun ortamlar (Ofis/Gece Hayatı/Günlük/Özel Davet/Romantik/Açık Hava, virgülle ayrılmış)
- kiyafet_stili: Uygun kıyafet tarzı (Casual/Formal/Sportif/Şık/Bohem/Klasik, virgülle ayrılmış)
- koku_ailesi: Ana koku ailesi (Çiçeksi/Odunsu/Oryantal/Aromatik/Taze/Narenciye/Gourmand/Pudralı/Deri/Yeşil)
- koku_yogunlugu: Hafif/Orta/Yoğun/Çok Yoğun
- duygusal_etiketler: Bu kokuyu tarif eden 3-5 duygusal kelime (Türkçe, virgülle ayrılmış)
- aciklama_tr: Türkçe kısa açıklama (2 cümle max)

SADECE JSON array döndür, başka hiçbir şey yazma. Format:
[
  {{
    "index": 1,
    "bas_notalar": "...",
    "kalp_notalar": "...",
    "dip_notalar": "...",
    "mevsim": "...",
    "gunun_zamani": "...",
    "ortam": "...",
    "kiyafet_stili": "...",
    "koku_ailesi": "...",
    "koku_yogunlugu": "...",
    "duygusal_etiketler": "...",
    "aciklama_tr": "..."
  }},
  ...
]"""

    try:
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": "Sen bir parfüm uzmanısın. Sadece JSON formatında yanıt ver."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=4000
        )
        
        content = response.choices[0].message.content.strip()
        # JSON temizleme
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        if content.endswith("```"):
            content = content[:-3]
        
        result = json.loads(content.strip())
        return result
    except Exception as e:
        print(f"Hata: {e}")
        return None


def main():
    # Veriyi yükle
    df = pd.read_excel('/home/ubuntu/upload/enson07.10.25.xlsx')
    df_clean = df.dropna(subset=['Kodu', 'Parfüm Adı']).copy()
    df_clean['Kodu'] = df_clean['Kodu'].astype(str).str.strip()
    df_clean['Parfüm Adı'] = df_clean['Parfüm Adı'].astype(str).str.strip()
    df_clean['Cinsiyet'] = df_clean['Cinsiyet'].astype(str).str.strip()
    
    # Cinsiyet standardizasyonu
    cinsiyet_map = {
        'unisex': 'Unisex', 'kadın': 'Kadın', 'Woman': 'Kadın',
        'Unisex/Kadın': 'Unisex', 'Unisex/Erkek': 'Unisex',
        'Unisex/erkek': 'Unisex', 'Erkek/Unisex': 'Unisex',
        'Kadın/Unisex': 'Unisex', 'Kadınsı': 'Kadın', ' Unisex': 'Unisex',
        'nan': 'Unisex'
    }
    df_clean['Cinsiyet'] = df_clean['Cinsiyet'].replace(cinsiyet_map)
    
    # Zenginleştirme sütunları ekle
    enrichment_cols = ['bas_notalar', 'kalp_notalar', 'dip_notalar', 'mevsim', 
                       'gunun_zamani', 'ortam', 'kiyafet_stili', 'koku_ailesi', 
                       'koku_yogunlugu', 'duygusal_etiketler', 'aciklama_tr']
    for col in enrichment_cols:
        df_clean[col] = ''
    
    # Daha önce kaydedilmiş ilerleme var mı kontrol et
    progress_file = '/home/ubuntu/upload/parfum_enriched_progress.csv'
    if os.path.exists(progress_file):
        df_progress = pd.read_csv(progress_file, encoding='utf-8-sig')
        # Zaten işlenmiş olanları bul
        processed_mask = df_progress['bas_notalar'].notna() & (df_progress['bas_notalar'] != '')
        print(f"Önceki ilerleme: {processed_mask.sum()} parfüm zaten işlenmiş")
        df_clean = df_progress.copy()
    
    records = df_clean.to_dict('records')
    total = len(records)
    
    # Batch boyutu: 15 parfüm
    batch_size = 15
    
    print(f"Toplam {total} parfüm işlenecek")
    print(f"Batch boyutu: {batch_size}")
    print(f"Tahmini batch sayısı: {(total + batch_size - 1) // batch_size}")
    print()
    
    processed_count = 0
    
    for batch_start in range(0, total, batch_size):
        batch_end = min(batch_start + batch_size, total)
        batch = records[batch_start:batch_end]
        
        # Bu batch'te işlenmemiş olanlar var mı?
        needs_processing = any(
            not str(r.get('bas_notalar', '')).strip() or str(r.get('bas_notalar', '')) == 'nan'
            for r in batch
        )
        
        if not needs_processing:
            print(f"Batch {batch_start//batch_size + 1}: Zaten işlenmiş, atlanıyor...")
            continue
        
        print(f"Batch {batch_start//batch_size + 1}/{(total + batch_size - 1) // batch_size}: "
              f"Parfüm {batch_start+1}-{batch_end} işleniyor...")
        
        result = enrich_perfume_batch(batch)
        
        if result:
            for item in result:
                idx = batch_start + item['index'] - 1
                if idx < total:
                    for col in enrichment_cols:
                        records[idx][col] = item.get(col, '')
            processed_count += len(batch)
            print(f"  ✓ {len(batch)} parfüm zenginleştirildi")
        else:
            print(f"  ✗ Bu batch başarısız oldu, tekrar deneniyor...")
            time.sleep(5)
            result = enrich_perfume_batch(batch)
            if result:
                for item in result:
                    idx = batch_start + item['index'] - 1
                    if idx < total:
                        for col in enrichment_cols:
                            records[idx][col] = item.get(col, '')
                processed_count += len(batch)
                print(f"  ✓ {len(batch)} parfüm zenginleştirildi (2. deneme)")
        
        # Her batch sonrası kaydet
        df_result = pd.DataFrame(records)
        df_result.to_csv(progress_file, index=False, encoding='utf-8-sig')
        
        # Rate limiting
        time.sleep(1)
    
    # Final kayıt
    df_result = pd.DataFrame(records)
    output_file = '/home/ubuntu/upload/parfum_zenginlestirilmis.csv'
    df_result.to_csv(output_file, index=False, encoding='utf-8-sig')
    
    # Excel olarak da kaydet
    output_excel = '/home/ubuntu/upload/parfum_zenginlestirilmis.xlsx'
    df_result.to_excel(output_excel, index=False)
    
    print(f"\n✓ Tamamlandı! {processed_count} parfüm zenginleştirildi.")
    print(f"CSV: {output_file}")
    print(f"Excel: {output_excel}")
    
    return df_result


if __name__ == "__main__":
    df_result = main()
    print("\nİlk 3 satır önizleme:")
    print(df_result[['Kodu', 'Parfüm Adı', 'bas_notalar', 'mevsim', 'koku_ailesi']].head(3).to_string())
