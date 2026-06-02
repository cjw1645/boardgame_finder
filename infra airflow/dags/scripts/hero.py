import requests
import pandas as pd
import time
import re
from bs4 import BeautifulSoup
from datetime import datetime

class HeroDataCrawler:
    # (이전과 동일한 크롤러 로직. 지면상 유틸리티 및 크롤링 함수 세부 구현 생략)
    def __init__(self, kakao_api_key):
        self.base_url = "https://funhero.co.kr"
        self.session = requests.Session()
        self.headers = {"User-Agent": "Mozilla/5.0"}
        self.kakao_api_key = kakao_api_key

    def _get_kakao_location(self, address):
        if not address: return None, None
        url = "https://dapi.kakao.com/v2/local/search/address.json"
        headers = {"Authorization": f"KakaoAK {self.kakao_api_key}"}
        clean_addr = re.sub(r'\(.*?\)', '', address).strip()
        try:
            res = requests.get(url, headers=headers, params={"query": clean_addr})
            docs = res.json().get('documents')
            if docs: return float(docs[0]['y']), float(docs[0]['x'])
        except: pass
        return None, None

    def _parse_players(self, text):
        nums = [int(n) for n in re.findall(r'\d+', str(text))]
        if len(nums) >= 2: return nums[0], nums[1]
        elif len(nums) == 1: return nums[0], nums[0]
        return None, None

    def extract_dim_store(self):
        # 매장 추출 로직
        regions = ['서울', '경기', '인천', '강원', '충남', '충북', '대전', '대구', '경남', '경북', '전북', '전남', '울산', '광주', '부산', '제주']
        seen_idx, stores = set(), []
        for region in regions:
            api_url = f"{self.base_url}/admin/bbs/mapAddrList.php"
            try:
                res = self.session.get(api_url, params={"code": "map_store", "searchopt": "subcon", "searchkey": region}, headers=self.headers)
                for item in res.json():
                    if item['idx'] not in seen_idx:
                        seen_idx.add(item['idx'])
                        lat, lng = self._get_kakao_location(item['address'])
                        stores.append({
                            "store_id": f"hero_{item['idx']}", "branch_name": item['title'].strip(),
                            "region": item['address'].split()[0] if item['address'] else None,
                            "address": item['address'], "latitude": lat, "longitude": lng,
                            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        })
                time.sleep(0.1)
            except: continue
        return pd.DataFrame(stores)

    def extract_dim_game(self):
        # 게임 추출 로직
        api_url = f"{self.base_url}/store/segame.php"
        all_games, page = [], 1
        while True:
            try:
                res = self.session.get(api_url, params={"category_info_id": 0, "store_id": 0, "page": page}, headers=self.headers)
                soup = BeautifulSoup(res.text, 'html.parser')
                items = soup.select('.listBox.faqQDiv')
                if not items: break
                for item in items:
                    btn = item.select_one('.storeBtn.btn')
                    if not btn or 'data-game-code' not in btn.attrs: continue
                    raw_title = item.select_one('h2').text if item.select_one('h2') else "이름 없음"
                    title_ko = re.sub(r'\[.*?\]\s*', '', raw_title).strip()
                    difficulty, min_p, max_p, playtime = None, None, None, None
                    for dl in item.select('.txtList dl'):
                        dt = dl.select_one('dt').text.strip() if dl.select_one('dt') else ""
                        dd = dl.select_one('dd').text.strip() if dl.select_one('dd') else ""
                        if dt == "난이도": difficulty = dd
                        elif dt == "인원": min_p, max_p = self._parse_players(dd)
                        elif dt == "게임시간": playtime = self._parse_players(dd)[0]
                    all_games.append({
                        "game_id": f"hero_{btn['data-game-code']}", "title_ko": title_ko,
                        "difficulty": difficulty, "min_players": min_p, "max_players": max_p, "playtime_min": playtime,
                        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    })
                page += 1
            except: break
        return pd.DataFrame(all_games).drop_duplicates(subset=['game_id']).reset_index(drop=True)

    def extract_fact_inventory(self, df_dim_store, df_dim_game):
        # 재고 추출 로직
        store_map = {name: sid for name, sid in zip(df_dim_store['branch_name'], df_dim_store['store_id'])}
        fact_inventory, api_url = [], f"{self.base_url}/store/get_store_list.php"
        today_date = datetime.now().strftime("%Y-%m-%d")
        for _, row in df_dim_game.iterrows():
            raw_game_code = row['game_id'].replace("hero_", "")
            try:
                res = self.session.get(api_url, params={"code": raw_game_code}, timeout=5)
                json_res = res.json()
                region_list = json_res.get('data', []) if isinstance(json_res, dict) else json_res
                if not region_list: continue
                for region_data in region_list:
                    if not isinstance(region_data, dict): continue
                    for market in region_data.get('market_list', []):
                        store_id = store_map.get(market.get('title', '').strip())
                        if store_id:
                            fact_inventory.append({"store_id": store_id, "game_id": row['game_id'], "collected_date": today_date})
            except: continue
        return pd.DataFrame(fact_inventory)

def run_hero_extraction(kakao_api_key):
    print("🚀 Hero 추출 시작")
    crawler = HeroDataCrawler(kakao_api_key)
    df_store = crawler.extract_dim_store()
    df_game = crawler.extract_dim_game()
    df_fact = crawler.extract_fact_inventory(df_store, df_game)
    
    # Airflow 워커에서 접근 가능한 임시 경로에 저장
    df_store.to_csv("/tmp/dim_store_hero.csv", index=False, encoding="utf-8-sig")
    df_game.to_csv("/tmp/dim_game_hero.csv", index=False, encoding="utf-8-sig")
    df_fact.to_csv("/tmp/fact_inventory_hero.csv", index=False, encoding="utf-8-sig")
    print("✅ Hero 추출 완료 및 CSV 임시 저장 성공")