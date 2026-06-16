import requests
import pandas as pd
import time
import re
from bs4 import BeautifulSoup
from datetime import datetime

class RedButtonPipeline:
    def __init__(self):
        self.api_url = "https://redbutton.co.kr/wp-admin/admin-ajax.php"
        self.main_url = "https://redbutton.co.kr/"
        self.session = requests.Session()
        
        # ⭐️ 봇 차단 우회용 헤더
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Referer": self.main_url
        }
        self.timeout = 30 
        
        # 파이프라인 시작 전 무조건 쿠키부터 챙김
        self._init_session_cookie()

    def _init_session_cookie(self):
        """메인 홈페이지를 먼저 방문하여 세션 쿠키를 획득합니다."""
        print("🎟️ [Red Button] 서버 입장권(Session Cookie) 획득 중...")
        try:
            self.session.get(self.main_url, headers={"User-Agent": self.headers["User-Agent"]}, timeout=self.timeout)
            print(" - 쿠키 획득 완료!")
        except Exception as e:
            print(f"⚠️ 쿠키 획득 에러: {e}")

    def _parse_players(self, text):
        nums = re.findall(r'\d+', str(text))
        if len(nums) >= 2: return int(nums[0]), int(nums[1])
        elif len(nums) == 1: return int(nums[0]), int(nums[0])
        return None, None

    def build_dim_store(self):
        print("🌐 [Red Button] 매장 데이터 수집 중...")
        try:
            res = self.session.get(self.api_url, params={"action": "luke_stores_list_json"}, headers=self.headers, timeout=self.timeout)
            stores = []
            for s in res.json().get('stores', []):
                stores.append({
                    "store_id": f"red_{s.get('ID')}",
                    "branch_id": s.get('branch_id'),
                    "branch_name": s.get('title'),
                    "region": s.get('location'),
                    "address": s.get('address'),
                    "latitude": float(s.get('lat')) if s.get('lat') else 0.0,
                    "longitude": float(s.get('lng')) if s.get('lng') else 0.0,
                    "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })
            return pd.DataFrame(stores)
        except Exception as e:
            print(f"⚠️ 매장 데이터 수집 에러: {e}")
            return pd.DataFrame()

    def build_dim_game(self):
        print("🎲 [Red Button] 게임 마스터 수집 중...")
        payload = {"action": "get_game_list", "branch_id": "", "query": ""}
        try:
            res = self.session.post(self.api_url, data=payload, headers=self.headers, timeout=self.timeout)
            soup = BeautifulSoup(res.json().get('html', ''), 'html.parser')
            items = soup.select('.red-game-wrap')
            games = []
            for item in items:
                rules = item.select('.content-rule')
                min_p, max_p = self._parse_players(rules[1].text) if len(rules) > 1 else (None, None)
                playtime = self._parse_players(rules[2].text)[0] if len(rules) > 2 else None
                games.append({
                    "game_id": f"red_{item.select_one('.content-store')['data-game-id']}",
                    "title_ko": item.select_one('.game-title').text.strip(),
                    "difficulty": rules[0].text.replace("난이도", "").strip() if len(rules) > 0 else None,
                    "min_players": min_p,
                    "max_players": max_p,
                    "playtime_min": playtime,
                    "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })
            return pd.DataFrame(games).drop_duplicates(subset=['game_id']).reset_index(drop=True)
        except Exception as e:
            print(f"⚠️ 게임 마스터 수집 에러: {e}")
            return pd.DataFrame()

    def build_fact_inventory(self, df_store):
        print("📦 [Red Button] 매장별 재고 수집 중...")
        if df_store.empty:
            return pd.DataFrame()

        inventory = []
        for i, row in df_store.iterrows():
            payload = {"action": "get_game_list", "branch_id": row['branch_id'], "query": ""}
            try:
                res = self.session.post(self.api_url, data=payload, headers=self.headers, timeout=self.timeout)
                soup = BeautifulSoup(res.json().get('html', ''), 'html.parser')
                items = soup.select('.red-game-wrap')
                for item in items:
                    inventory.append({
                        "store_id": row['store_id'],
                        "game_id": f"red_{item.select_one('.content-store')['data-game-id']}",
                        "collected_date": datetime.now().strftime("%Y-%m-%d")
                    })
                time.sleep(0.1)
            except: 
                continue
        return pd.DataFrame(inventory)

def run_redbutton_extraction():
    pipeline = RedButtonPipeline()
    df_store = pipeline.build_dim_store()
    df_game = pipeline.build_dim_game()
    df_fact = pipeline.build_fact_inventory(df_store)
    
    if not df_store.empty:
        df_store.to_csv("/opt/airflow/data/dim_store_redbutton.csv", index=False, encoding="utf-8-sig")
    if not df_game.empty:
        df_game.to_csv("/opt/airflow/data/dim_game_redbutton.csv", index=False, encoding="utf-8-sig")
    if not df_fact.empty:
        df_fact.to_csv("/opt/airflow/data/fact_inventory_redbutton.csv", index=False, encoding="utf-8-sig")
        
    print(f"✅ Red Button 데이터 추출 완료 (매장: {len(df_store)}, 게임: {len(df_game)}, 재고: {len(df_fact)})")

if __name__ == "__main__":
    run_redbutton_extraction()