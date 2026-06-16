import os
import re
import requests
import pandas as pd
from bs4 import BeautifulSoup
import concurrent.futures
import urllib3
import time

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class BoardlifeCrawler:
    def __init__(self):
        self.base_url = "https://boardlife.co.kr"
        self.session = requests.Session()
        self.session.verify = False
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        self.save_dir = "/opt/airflow/data" if os.path.exists("/opt/airflow/data") else "../data"
        self.file_path = os.path.join(self.save_dir, "master_boardlife.csv")
        
        # ⭐️ 영문 표준 컬럼명 및 순서 강제 고정 (CSV 헤더 변경 시 이 순서와 이름을 꼭 맞춰주세요!)
        self.columns = [
            "BL_ID", "bgg_id", "game_name_kr", "game_name_en", 
            "min_players", "max_players", "best_player", 
            "min_time", "max_time", "weight", "rating", 
            "categories", "themes", "mechanisms", "designers", "url"
        ]

    def get_last_scraped_id(self):
        if os.path.exists(self.file_path):
            try:
                df = pd.read_csv(self.file_path)
                if not df.empty and 'BL_ID' in df.columns:
                    max_id = df['BL_ID'].astype(str).str.replace('bl_', '').astype(int).max()
                    return max_id
            except Exception as e:
                print(f"⚠️ 기존 CSV 읽기 에러: {e}")
        return 0

    def parse_text_to_int(self, text, regex_pattern, group_idx=1):
        if not text: return None
        match = re.search(regex_pattern, text)
        return int(match.group(group_idx)) if match else None

    def fetch_single_game(self, bl_id):
        main_url = f"{self.base_url}/game/{bl_id}"
        credits_url = f"{self.base_url}/game/{bl_id}/credits"
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                res = self.session.get(main_url, headers=self.headers, timeout=15)
                if res.status_code != 200:
                    return None
                
                soup = BeautifulSoup(res.text, 'html.parser')
                
                title_elem = soup.select_one('#boardgame-title')
                if not title_elem: return None
                game_name_kr = title_elem.text.strip()
                
                title_en_elem = soup.select_one('h2.font-17.main-color')
                game_name_en = title_en_elem.text.strip() if title_en_elem else None
                
                bgg_id = None
                bgg_link = soup.select_one("a[href*='boardgamegeek.com/boardgame/']")
                if bgg_link:
                    match = re.search(r'/boardgame/(\d+)', bgg_link['href'])
                    if match: bgg_id = match.group(1)

                weight_elem = soup.select_one('#game-weight')
                weight = float(weight_elem.text.strip()) if weight_elem else None

                min_players, max_players, best_player = None, None, None
                min_time, max_time = None, None
                
                for dt in soup.select('dt.page-title'):
                    dt_text = dt.text.strip()
                    dd = dt.find_next_sibling('dd')
                    if not dd: continue
                    dd_text = dd.text.strip()
                    
                    if dt_text == '인원':
                        p_match = re.search(r'(\d+)(?:-(\d+))?명', dd_text)
                        if p_match:
                            min_players = int(p_match.group(1))
                            max_players = int(p_match.group(2)) if p_match.group(2) else min_players
                        best_player = self.parse_text_to_int(dd_text, r'베스트:(\d+)인')
                        
                    elif dt_text == '플레이 시간':
                        t_match = re.search(r'(\d+)(?:-(\d+))?분', dd_text)
                        if t_match:
                            min_time = int(t_match.group(1))
                            max_time = int(t_match.group(2)) if t_match.group(2) else min_time
                
                rating_dt = soup.find('dt', string=re.compile('평점'))
                rating = None
                if rating_dt:
                    rating_val = rating_dt.find_next_sibling('dd').get_text(strip=True)
                    try: rating = float(rating_val)
                    except: pass

                res_credits = self.session.get(credits_url, headers=self.headers, timeout=15)
                categories, themes, mechanisms, designers = [], [], [], []
                
                if res_credits.status_code == 200:
                    c_soup = BeautifulSoup(res_credits.text, 'html.parser')
                    for title_div in c_soup.select('.title-wrapper.credit .title.flex'):
                        category_name = title_div.get_text(strip=True)
                        content_div = title_div.find_next_sibling('div')
                        if not content_div: continue
                        
                        items = [a.get_text(strip=True) for a in content_div.select('a.title') if a.get_text(strip=True) != '정보없음']
                        
                        if '카테고리' in category_name: categories = items
                        elif '테마' in category_name: themes = items
                        elif '진행방식' in category_name: mechanisms = items
                        elif '디자이너' in category_name: designers = items

                return {
                    "BL_ID": f"bl_{bl_id}",
                    "bgg_id": bgg_id,
                    "game_name_kr": game_name_kr,
                    "game_name_en": game_name_en,
                    "min_players": min_players,
                    "max_players": max_players,
                    "best_player": best_player,
                    "min_time": min_time,
                    "max_time": max_time,
                    "weight": weight,
                    "rating": rating,
                    "categories": ", ".join(categories),
                    "themes": ", ".join(themes),
                    "mechanisms": ", ".join(mechanisms),
                    "designers": ", ".join(designers),
                    "url": main_url
                }
                
            except requests.exceptions.ReadTimeout:
                if attempt < max_retries - 1:
                    time.sleep(2)
                    continue
                return None
            except Exception as e:
                return None

    def crawl_incremental_data(self):
        last_id = self.get_last_scraped_id()
        
        if last_id == 0:
            print("⚠️ 기존 데이터가 없습니다. 최초 1회 전체 수집을 시작합니다.")
            start_id, end_id = 1, 21000
        else:
            start_id = last_id + 1
            end_id = start_id + 100
            
        print(f"🚀 보드라이프 마스터 데이터 수집 타겟 (ID: {start_id} ~ {end_id})")
        results = []
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            future_to_id = {executor.submit(self.fetch_single_game, bl_id): bl_id for bl_id in range(start_id, end_id + 1)}
            for future in concurrent.futures.as_completed(future_to_id):
                data = future.result()
                if data:
                    results.append(data)
                
                if len(results) > 0 and len(results) % 50 == 0:
                    print(f"🔄 현재 {len(results)}개 게임 데이터 수집 완료...")
                    
        # ⭐️ DataFrame 생성 시 컬럼 순서 강제 적용
        return pd.DataFrame(results, columns=self.columns)

def run_boardlife_extraction():
    crawler = BoardlifeCrawler()
    df_new = crawler.crawl_incremental_data()
    
    if df_new.empty:
        print("✅ 새로 등록된 보드게임이 없거나 수집에 실패했습니다.")
        return
    
    os.makedirs(crawler.save_dir, exist_ok=True)
    
    file_exists = os.path.exists(crawler.file_path)
    df_new.to_csv(
        crawler.file_path, 
        mode='a', 
        index=False, 
        header=not file_exists,
        encoding='utf-8-sig'
    )
    
    print(f"✅ 최신 데이터 {len(df_new)}건 업데이트 완료! (경로: {crawler.file_path})")

if __name__ == "__main__":
    run_boardlife_extraction()