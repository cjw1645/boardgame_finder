import pandas as pd
import requests
import os
import time
import xml.etree.ElementTree as ET
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())

class BGGCrawler:
    def __init__(self):
        self.api_url = "https://boardgamegeek.com/xmlapi2/thing"
        
        self.bgg_token = os.environ.get("BGG_API_TOKEN")
        if not self.bgg_token:
            raise ValueError("🚨 환경변수 오류: BGG_API_TOKEN이 설정되지 않았습니다. .env 파일을 확인하세요!")
        
        self.data_dir = "/opt/airflow/data"        
        self.bl_master_path = os.path.join(self.data_dir, "master_boardlife.csv")
        self.bgg_master_path = os.path.join(self.data_dir, "master_bgg_stats.csv")
        self.bgg_comments_path = os.path.join(self.data_dir, "master_bgg_comments.csv")

    def get_target_ids(self):
        if not os.path.exists(self.bl_master_path):
            print("⚠️ 보드라이프 마스터 파일이 없어 BGG 수집을 종료합니다.")
            return []

        df_bl = pd.read_csv(self.bl_master_path)
        all_bgg_ids = df_bl.dropna(subset=['bgg_id'])['bgg_id'].astype(str).str.replace(r'\.0$', '', regex=True).tolist()
        
        if os.path.exists(self.bgg_master_path):
            df_bgg = pd.read_csv(self.bgg_master_path)
            crawled_ids = df_bgg['bgg_id'].astype(str).tolist()
            target_ids = list(set(all_bgg_ids) - set(crawled_ids))
        else:
            target_ids = list(set(all_bgg_ids))

        return [tid for tid in target_ids if tid.isdigit()]

    def fetch_bgg_stats(self, target_ids):
        if not target_ids:
            return pd.DataFrame(), pd.DataFrame()

        print(f"🚀 BGG 글로벌 데이터 및 코멘트 수집 시작 (타겟: {len(target_ids)}건)")
        
        results = []
        comments_results = []
        batch_size = 20 
        
        # ⭐️ 2. HTTP 요청 헤더에 Bearer 토큰 탑재
        headers = {
            "Authorization": f"Bearer {self.bgg_token}"
        }
        
        for i in range(0, len(target_ids), batch_size):
            batch = target_ids[i:i+batch_size]
            id_string = ",".join(batch)
            
            try:
                # comments=1 파라미터 추가하여 코멘트 데이터도 함께 요청
                res = requests.get(f"{self.api_url}?id={id_string}&stats=1&comments=1", headers=headers, timeout=20)
                
                if res.status_code == 200:
                    root = ET.fromstring(res.content)
                    
                    for item in root.findall('item'):
                        bgg_id = item.get('id')
                        
                        # 1. Stats 파싱
                        stats = item.find('statistics/ratings')
                        if stats is not None:
                            avg_rating = stats.find('average').get('value') if stats.find('average') is not None else None
                            weight = stats.find('averageweight').get('value') if stats.find('averageweight') is not None else None
                            
                            results.append({
                                "bgg_id": bgg_id,
                                "bgg_rating": float(avg_rating) if avg_rating and avg_rating != '0' else None,
                                "bgg_weight": float(weight) if weight and weight != '0' else None,
                                "bgg_updated_at": time.strftime("%Y-%m-%d")
                            })
                        
                        # 2. Comments 파싱
                        comments_elem = item.find('comments')
                        if comments_elem is not None:
                            for comment in comments_elem.findall('comment'):
                                username = comment.get('username')
                                rating = comment.get('rating')
                                value = comment.get('value')
                                
                                # 코멘트 내용이 존재하는 경우만 수집
                                if value:
                                    comments_results.append({
                                        "bgg_id": bgg_id,
                                        "username": username,
                                        "rating": float(rating) if rating and rating != 'N/A' else None,
                                        "comment": value,
                                        "bgg_updated_at": time.strftime("%Y-%m-%d")
                                    })
                                    
                    print(f" - 진행률: {min(i+batch_size, len(target_ids))}/{len(target_ids)} 완료")
                    time.sleep(2)
                
                # ⭐️ 3. 인증 실패 시 즉시 에러 뿜기
                elif res.status_code in [401, 403]:
                    print("❌ 인증 에러 (401/403): BGG API 토큰이 유효하지 않거나 입력되지 않았습니다!")
                    break
                else:
                    print(f"⚠️ 기타 에러 발생 (HTTP 상태 코드: {res.status_code})")
                    
            except Exception as e:
                print(f"⚠️ BGG 통신 에러: {e}")

        return pd.DataFrame(results), pd.DataFrame(comments_results)

def run_bgg_extraction():
    crawler = BGGCrawler()
    target_ids = crawler.get_target_ids()
    
    if not target_ids:
        print("✅ 새로 수집할 BGG 데이터가 없습니다. (전체 갱신 생략)")
        return

    df_new, df_comments = crawler.fetch_bgg_stats(target_ids)
    
    # Stats 저장
    if not df_new.empty:
        file_exists = os.path.exists(crawler.bgg_master_path)
        df_new.to_csv(
            crawler.bgg_master_path, 
            mode='a', 
            index=False, 
            header=not file_exists,
            encoding='utf-8-sig'
        )
        print(f"🎉 최신 BGG 데이터 {len(df_new)}건 추가 완료! (경로: {crawler.bgg_master_path})")
    else:
        print("⚠️ 수집된 BGG 데이터가 없습니다. (API 인증 문제인지 확인하세요)")

    # Comments 저장
    if not df_comments.empty:
        comments_file_exists = os.path.exists(crawler.bgg_comments_path)
        df_comments.to_csv(
            crawler.bgg_comments_path,
            mode='a',
            index=False,
            header=not comments_file_exists,
            encoding='utf-8-sig'
        )
        print(f"💬 최신 BGG 코멘트 데이터 {len(df_comments)}건 추가 완료! (경로: {crawler.bgg_comments_path})")

if __name__ == "__main__":
    run_bgg_extraction()