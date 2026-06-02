import requests
import pandas as pd
import time
import re
from bs4 import BeautifulSoup
from datetime import datetime

class RedButtonPipeline:
    def __init__(self):
        self.api_url = "https://redbutton.co.kr/wp-admin/admin-ajax.php"
        self.session = requests.Session()
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "X-Requested-With": "XMLHttpRequest"
        }

    def _parse_players(self, text):
        nums = re.findall(r'\d+', str(text))
        if len(nums) >= 2: return int(nums[0]), int(nums[1])
        elif len(nums) == 1: return int(nums[0]), int(nums[0])
        return None, None

    def build_dim_store(self):
        print("🌐 [Red Button] 매장 데이터 수집 중...")
        res = self.session.get(self.api_url, params={"action": "luke_stores_list_json"}, headers=self.headers)
        stores = []
        for s in res.json().get('stores', []):
            stores.append({
                "store_id": f"red_{s.get('ID')}", # 접두사 추가
                "branch_id": s.get('branch_id'),
                "branch_name": s.get('title'),
                "region": s.get('location'),
                "address": s.get('address'),
                "latitude": float(s.get('lat')) if s.get('lat') else 0.0,
                "longitude": float(s.get('lng')) if s.get('lng') else 0.0,
                "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
        return pd.DataFrame(stores)

    def build_dim_game(self):
        print("🎲 [Red Button] 게임 마스터 수집 중...")
        payload = {"action": "get_game_list", "branch_id": "", "query": ""}
        res = self.session.post(self.api_url, data=payload, headers=self.headers)
        soup = BeautifulSoup(res.json().get('html', ''), 'html.parser')
        items = soup.select('.red-game-wrap')
        games = []
        for item in items:
            rules = item.select('.content-rule')
            min_p, max_p = self._parse_players(rules[1].text) if len(rules) > 1 else (None, None)
            playtime = self._parse_players(rules[2].text)[0] if len(rules) > 2 else None
            games.append({
                "game_id": f"red_{item.select_one('.content-store')['data-game-id']}", # 접두사 추가
                "title_ko": item.select_one('.game-title').text.strip(),
                "difficulty": rules[0].text.replace("난이도", "").strip() if len(rules) > 0 else None,
                "min_players": min_p,
                "max_players": max_p,
                "playtime_min": playtime,
                "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
        return pd.DataFrame(games).drop_duplicates(subset=['game_id']).reset_index(drop=True)

    def build_fact_inventory(self, df_store):
        print("📦 [Red Button] 매장별 재고 수집 중...")
        inventory = []
        for i, row in df_store.iterrows():
            payload = {"action": "get_game_list", "branch_id": row['branch_id'], "query": ""}
            try:
                res = self.session.post(self.api_url, data=payload, headers=self.headers)
                soup = BeautifulSoup(res.json().get('html', ''), 'html.parser')
                items = soup.select('.red-game-wrap')
                for item in items:
                    inventory.append({
                        "store_id": row['store_id'],
                        "game_id": f"red_{item.select_one('.content-store')['data-game-id']}",
                        "collected_date": datetime.now().strftime("%Y-%m-%d")
                    })
                time.sleep(0.1)
            except: continue
        return pd.DataFrame(inventory)

# Airflow에서 호출할 래퍼 함수
def run_redbutton_extraction():
    pipeline = RedButtonPipeline()
    df_store = pipeline.build_dim_store()
    df_game = pipeline.build_dim_game()
    df_fact = pipeline.build_fact_inventory(df_store)
    
    # 통합 로직에서 읽을 수 있도록 /tmp에 저장
    df_store.to_csv("/tmp/dim_store_redbutton.csv", index=False, encoding="utf-8-sig")
    df_game.to_csv("/tmp/dim_game_redbutton.csv", index=False, encoding="utf-8-sig")
    df_fact.to_csv("/tmp/fact_inventory_redbutton.csv", index=False, encoding="utf-8-sig")
    print("✅ Red Button 데이터 추출 및 임시 저장 완료")