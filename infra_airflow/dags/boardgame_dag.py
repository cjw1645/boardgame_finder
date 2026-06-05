from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
import sys
import os

# scripts 폴더 경로 추가
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# 파일명과 함수명을 정확히 매칭하여 Import
from scripts.extract_hero import run_hero_extraction
from scripts.extract_redbutton import run_redbutton_extraction
from scripts.integrate_and_load import run_integration_and_load
from scripts.extract_boardlife import run_boardlife_extraction

default_args = {
    'owner': 'cjw1645',
    'depends_on_past': False,
    'start_date': datetime(2026, 5, 1),
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

with DAG(
    'boardgame_daily_pipeline',
    default_args=default_args,
    schedule_interval='0 3 * * *',
    catchup=False,
) as dag:

    task_extract_hero = PythonOperator(
        task_id='extract_hero_data',
        python_callable=run_hero_extraction, # 괄호() 없이 이름만 적습니다.
    )

    task_extract_redbutton = PythonOperator(
        task_id='extract_redbutton_data',
        python_callable=run_redbutton_extraction,
    )

    task_extract_boardlife = PythonOperator(
        task_id='extract_boardlife_data',
        python_callable=run_boardlife_extraction,
    )

    task_integrate_load = PythonOperator(
        task_id='integrate_and_load_to_db',
        python_callable=run_integration_and_load,
    )



    # 병렬 추출 후 통합 적재 실행
    [task_extract_hero, task_extract_redbutton, task_extract_boardlife] >> task_integrate_load