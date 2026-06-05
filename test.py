import os
import re
import requests
import pandas as pd
from bs4 import BeautifulSoup
import concurrent.futures
import urllib3
import time

# SSL 경고창 숨기기
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class BoardlifeLocalCrawler:
    def __init__(self):
        self.base_url = "https://boardlife.co.kr"
        self.session = requests.Session()
        self.session.verify = False
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        # 로컬 다운로드용 경로 설정 (프로젝트 내 data 폴더)
        self.save_dir = "./data"
        self.file_path = os.path.join(self.save_dir, "master_boardlife.csv")
        
        # 폴더가 없으면 미리 생성
        os.makedirs(self.save_dir, exist_ok=True)

    def get_last_scraped_id(self):
        """CSV 파일을 읽어 가장 마지막으로 수집된(또는 결번 처리된) ID 번호를 찾습니다."""
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
        """정규식을 활용한 숫자 안전 추출 함수"""
        if not text: return None
        match = re.search(regex_pattern, text)
        return int(match.group(group_idx)) if match else None

    def fetch_single_game(self, bl_id):
        main_url = f"{self.base_url}/game/{bl_id}"
        credits_url = f"{self.base_url}/game/{bl_id}/credits"
        
        # 기본 템플릿 (결번 시에도 이 구조를 유지하여 에러 방지)
        empty_result = {
            "BL_ID": f"bl_{bl_id}", "bgg_id": None, "game_name_kr": "결번", "game_name_en": None,
            "min_players": None, "max_players": None, "best_player": None,
            "min_time": None, "max_time": None, "weight": None, "rating": None,
            "categories": None, "themes": None, "mechanisms": None, "designers": None, "url": main_url
        }
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # 1. 기본 정보 페이지 수집
                res = self.session.get(main_url, headers=self.headers, timeout=15)
                if res.status_code != 200:
                    return empty_result
                
                soup = BeautifulSoup(res.text, 'html.parser')
                
                # 게임 이름 추출
                title_elem = soup.select_one('#boardgame-title')
                if not title_elem: return empty_result
                
                game_name_kr = title_elem.text.strip()
                title_en_elem = soup.select_one('h2.font-17.main-color')
                game_name_en = title_en_elem.text.strip() if title_en_elem else None
                
                # BGG ID 추출
                bgg_id = None
                bgg_link = soup.select_one("a[href*='boardgamegeek.com/boardgame/']")
                if bgg_link:
                    match = re.search(r'/boardgame/(\d+)', bgg_link['href'])
                    if match: bgg_id = match.group(1)

                # Weight (난이도)
                weight_elem = soup.select_one('#game-weight')
                weight = float(weight_elem.text.strip()) if weight_elem else None

                # 인원, 시간 파싱
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
                
                # 평점 
                rating_dt = soup.find('dt', string=re.compile('평점'))
                rating = None
                if rating_dt:
                    rating_val = rating_dt.find_next_sibling('dd').get_text(strip=True)
                    try: rating = float(rating_val)
                    except: pass

                # 2. 크레딧(상세 분류) 페이지 수집
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
                return empty_result
            except Exception:
                return empty_result

    def crawl_in_chunks(self, target_end_id=21000, chunk_size=100):
        start_id = self.get_last_scraped_id() + 1
        
        if start_id > target_end_id:
            print("🎉 모든 목표 데이터(21000개) 수집이 이미 완료되어 있습니다!")
            return

        print(f"🚀 총 목표: {target_end_id}개 / 현재 시작 지점: {start_id}번")
        
        # 100개씩 쪼개서 수집 및 즉시 저장
        for chunk_start in range(start_id, target_end_id + 1, chunk_size):
            chunk_end = min(chunk_start + chunk_size - 1, target_end_id)
            print(f"\n🔄 묶음 처리 중: ID {chunk_start} ~ {chunk_end} (동시 접속 10개)")
            
            results = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                future_to_id = {executor.submit(self.fetch_single_game, bl_id): bl_id for bl_id in range(chunk_start, chunk_end + 1)}
                for future in concurrent.futures.as_completed(future_to_id):
                    data = future.result()
                    if data:
                        results.append(data)
            
            # 묶음 단위로 바로 CSV 저장 (데이터 유실 완벽 방지)
            if results:
                # 결과 리스트를 원래 ID 순서대로 정렬 (옵션)
                results = sorted(results, key=lambda x: int(x['BL_ID'].replace('bl_', '')))
                
                df = pd.DataFrame(results)
                file_exists = os.path.exists(self.file_path)
                
                df.to_csv(
                    self.file_path, 
                    mode='a', 
                    index=False, 
                    header=not file_exists,
                    encoding='utf-8-sig'
                )
                print(f"💾 {chunk_start}~{chunk_end} 구간 저장 완료! (누적 저장됨)")
            
            # 서버 부하를 줄이기 위해 묶음 사이에 1초 휴식
            time.sleep(1)

if __name__ == "__main__":
    crawler = BoardlifeLocalCrawler()
    # 21,178번까지 100개씩 끊어서 수집 시작
    crawler.crawl_in_chunks(target_end_id=21178, chunk_size=100)