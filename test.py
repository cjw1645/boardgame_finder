import requests
import time

def debug_redbutton_with_cookie():
    api_url = "https://redbutton.co.kr/wp-admin/admin-ajax.php"
    main_url = "https://redbutton.co.kr/"
    
    # ⭐️ 쿠키를 유지해 주는 Session 객체 생성
    session = requests.Session()
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Referer": main_url
    }

    print("🎟️ [1단계] 메인 홈페이지 방문하여 입장권(Cookie) 발급받기...")
    try:
        session.get(main_url, headers={"User-Agent": headers["User-Agent"]}, timeout=15)
        print(" - 쿠키 발급 성공! (이제 파이썬도 일반 방문객으로 위장 완료)\n")
    except Exception as e:
        print(f" - 메인 홈페이지 접속 에러: {e}\n")

    print("🚀 [2단계] 쿠키를 지닌 채로 특정 매장 게임 목록(POST) 요청...")
    try:
        # 사용자님이 브라우저에서 성공하셨던 그 조건 그대로!
        payload = {
            "action": "get_game_list", 
            "branch_id": "1", 
            "query": ""
        }
        
        # ⭐️ 데이터를 담아 session 객체로 POST 요청 (자동으로 쿠키 포함됨)
        res_post = session.post(api_url, data=payload, headers=headers, timeout=15)
        
        print(f" - 상태 코드: HTTP {res_post.status_code}")
        
        if res_post.status_code == 200:
            print(" - 응답 결과 미리보기 (앞 300자):")
            print(f"   {res_post.text[:300]}...\n")
            
            # 파이썬에서도 드디어 true가 뜨는지 확인!
            if "true" in res_post.text[:50]:
                print("🎉 [성공] 쿠키를 적용하니 드디어 파이썬도 정상적인 데이터를 받아옵니다!!")
            else:
                print("🤔 [확인 요망] 응답은 왔지만 result가 true가 아닙니다.")
        else:
            print(" ❌ 서버 요청 실패")
            
    except Exception as e:
        print(f" ❌ [에러] POST 통신 오류: {e}")

if __name__ == "__main__":
    debug_redbutton_with_cookie()