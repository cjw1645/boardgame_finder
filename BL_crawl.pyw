import requests
from bs4 import BeautifulSoup
import time
import random
import csv
import os
import re
import pandas as pd
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

class BLDB_UltraFast_Builder:
    def __init__(self):
        self.base_url = "https://boardlife.co.kr"
        self.list_url = f"{self.base_url}/advanced_ajax.php"
        self.base_csv = 'bldb_base_sorted.csv'
        self.final_csv = 'BLDB_final.csv'
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'X-Requested-With': 'XMLHttpRequest'
        })
        self.file_lock = threading.Lock() # 멀티스레딩 파일 쓰기 충돌 방지용 자물쇠

    def step1_build_base_list(self):
        """1단계: 전체 리스트 스캔 및 정렬 (21,000개 타겟 확보)"""
        if os.path.exists(self.base_csv):
            print(f"✅ 정렬된 뼈대 파일('{self.base_csv}')이 이미 존재합니다. 1단계를 건너뜁니다.")
            return

        print("--- 🔍 1단계: 전체 리스트 스캔 시작 (sort 옵션 제외) ---")
        all_games = []
        page = 1

        while True:
            payload = {'action': 'CallAvList', 'pg': page}
            try:
                res = self.session.post(self.list_url, data=payload, timeout=10)
                soup = BeautifulSoup(res.text, 'html.parser')
                rows = soup.find_all('div', class_='rank-row')
                data_rows = [row for row in rows if 'top' not in row.get('class', [])]
                
                if not data_rows: break
                    
                for row in data_rows:
                    check_box = row.find('div', class_='check-box')
                    if not check_box: continue
                    game_id = int(check_box['id'].replace('game-check-', ''))
                    title = row.find('a', class_='title').get_text(strip=True)
                    all_games.append({'BL_ID': game_id, '한글이름': title})
                    
                if page % 50 == 0:
                    print(f"  {page}페이지 스캔 완료... (현재 획득: {len(all_games)}개)")
                page += 1
                time.sleep(0.2)
            except Exception as e:
                print(f"  [경고] {page}페이지 스캔 에러: {e}")
                time.sleep(2)

        print(f"\n✅ 스캔 완료! 총 {len(all_games)}개의 데이터를 확보했습니다.")
        sorted_games = sorted(all_games, key=lambda x: x['BL_ID'])
        
        with open(self.base_csv, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=['BL_ID', '한글이름'])
            writer.writeheader()
            writer.writerows(sorted_games)
        print(f"💾 '{self.base_csv}' 파일 저장 완료!\n")

    def fetch_bgg_worker(self, game):
        """멀티스레드용 BGG ID 수집 워커"""
        bl_id = game['BL_ID']
        result = {'BL_ID': bl_id, '한글이름': game['한글이름'], 'BGG_ID': ''}
        
        try:
            url = f"{self.base_url}/game/{bl_id}"
            res = self.session.get(url, timeout=10)
            soup = BeautifulSoup(res.text, 'html.parser')
            
            bgg_dt = soup.find('dt', string=re.compile('BGG', re.I))
            if bgg_dt:
                bgg_link = bgg_dt.find_next_sibling('dd').find('a')
                if bgg_link and 'href' in bgg_link.attrs:
                    match = re.search(r'/boardgame/(\d+)', bgg_link['href'])
                    if match:
                        result['BGG_ID'] = match.group(1)
        except Exception:
            pass
            
        time.sleep(random.uniform(0.3, 0.8)) # 차단 방지용 딜레이
        return result

    def step2_fast_fetch(self):
        """2단계: 멀티스레딩으로 타겟 상세 페이지 미친듯이 긁어오기"""
        print("--- 🚀 2단계: BGG ID 초고속 멀티스레딩 수집 ---")
        
        base_data = []
        with open(self.base_csv, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                base_data.append(row)

        completed_ids = set()
        mode = 'a'
        if os.path.exists(self.final_csv):
            with open(self.final_csv, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                completed_ids = {row['BL_ID'] for row in reader}
            print(f"📌 기존 최종 DB 발견. 이미 수집된 {len(completed_ids)}개는 건너뜁니다.")
        else:
            mode = 'w'

        targets = [g for g in base_data if str(g['BL_ID']) not in completed_ids]
        if not targets:
            print("🎉 모든 BGG ID 수집이 이미 완료된 상태입니다!")
            return

        print(f"남은 타겟 {len(targets)}개 수집 진행 중 (워커 8개 가동)...")

        with open(self.final_csv, mode, newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=['BL_ID', '한글이름', 'BGG_ID'])
            if mode == 'w': writer.writeheader()
            
            success_count = 0
            with ThreadPoolExecutor(max_workers=8) as executor:
                futures = {executor.submit(self.fetch_bgg_worker, game): game for game in targets}
                
                for future in as_completed(futures):
                    result = future.result()
                    
                    # 스레드 충돌 없이 안전하게 한 줄씩 기록
                    with self.file_lock:
                        writer.writerow(result)
                        f.flush()
                        
                    success_count += 1
                    if success_count % 100 == 0:
                        print(f"  진행 상황: {success_count} / {len(targets)} 개 완료...")

        print("\n✅ 2단계 수집 완료!")

    def step3_final_sort(self):
        """3단계: 수집 완료 후 1초만에 ID 순서대로 완벽하게 재정렬"""
        print("\n--- 🧹 3단계: 최종 DB 오름차순 재정렬 ---")
        try:
            df = pd.read_csv(self.final_csv)
            df['BL_ID'] = pd.to_numeric(df['BL_ID'])
            df_sorted = df.sort_values(by='BL_ID').reset_index(drop=True)
            df_sorted.to_csv(self.final_csv, index=False, encoding='utf-8-sig')
            print(f"🎉 완벽합니다! 총 {len(df_sorted)}개의 데이터가 ID순으로 정렬되어 '{self.final_csv}'에 저장되었습니다.")
        except Exception as e:
            print(f"❌ 정렬 중 오류 발생: {e}")

if __name__ == "__main__":
    builder = BLDB_UltraFast_Builder()
    
    # 1. 21000개 타겟 뼈대 만들기
    builder.step1_build_base_list()
    
    # 2. 멀티스레딩으로 초고속 긁기 (중간에 꺼져도 여기서부터 알아서 재개)
    builder.step2_fast_fetch()
    
    # 3. 마무리 자동 정렬
    builder.step3_final_sort()