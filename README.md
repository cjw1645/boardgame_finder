# boardgame_finder

AI 기반 오프라인 보드게임 추천 및 실시간 재고 탐색 서비스 (O2O)
사용자의 자연어 질의와 위치 정보를 결합하여, 현재 방문 가능한 주변 매장의 보드게임 재고를 실시간으로 찾아주는 AI RAG 챗봇 서비스입니다.

개인 프로젝트 | 2026.03 ~ 2026.07
1. 프로젝트 개요
배경 
오프라인 보드게임 카페 방문 전, 원하는 게임의 재고 여부를 파악하기 어렵고, 키워드 위주의 단순 검색으로는 사용자의 다양한 취향(예: "4명이서 1시간 동안 할 수 있는 마피아 게임")을 반영하기 어려움.

목표
대형 프랜차이즈(레드버튼, 히어로 보드게임카페)의 실시간 재고를 통합하는 데이터 파이프라인 구축.
LLM과 PostGIS를 결합하여, 반경 N km 이내의 실제 플레이 가능한 게임을 추천하는 하이브리드 추천 시스템 개발.

2. 기술 스택
Data Engineering: Python, Apache Airflow, BeautifulSoup, Pandas
Database: PostgreSQL, PostGIS, pgvector
AI & NLP: Google Gemini API (LLM & 768차원 Embedding)
Backend / Frontend: Streamlit, SQLAlchemy
Infrastructure: Docker, Docker Compose

3. System Architecture (시스템 아키텍처)
Data Collection (Extract): Airflow를 통해 각 브랜드 매장의 지점 정보 및 재고 리스트 정기 크롤링.
Data Integration (Transform/Load): 수집된 데이터를 마스터 정적 데이터(보드라이프 CSV)와 매핑(Entity Resolution)하여 PostgreSQL 기반의 정규화된 Data Warehouse(Dim, Fact 테이블)에 적재.
AI Embedding: 마스터 보드게임 메타데이터를 구글 Gemini 모델을 통해 768차원 벡터로 변환 후 pgvector 인덱스 생성.
Service (RAG): 사용자의 위치(위경도)와 프롬프트를 입력받아, 반경 거리 필터링(PostGIS)과 의미 기반 검색(Semantic Search)을 동시 수행하여 최적의 결과를 챗봇 UI로 제공.

4. Key Features (핵심 기능)
- 단순 키워드 매칭이 아닌, 사용자의 맥락을 이해하여 768차원의 벡터 공간에서 가장 유사한 특징을 가진 보드게임을 탐색.
- PostGIS의 ST_DistanceSphere 함수를 활용해 사용자의 현재 위도/경도 기준 지정 반경(예: 5km) 내의 매장만 필터링. 
- 추천된 게임이 현재 매장에 실제로 존재하는지 Fact Inventory 테이블과 실시간 JOIN하여 헛걸음을 방지.
- Streamlit을 활용하여 실제 매장 직원과 대화하는 듯한 자연스러운 챗봇 인터페이스 구현.