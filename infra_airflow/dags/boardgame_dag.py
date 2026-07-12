from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from scripts.extract_hero import run_hero_extraction
from scripts.extract_redbutton import run_redbutton_extraction
from scripts.integrate_and_load import run_integration_and_load
from scripts.extract_boardlife import run_boardlife_extraction
from scripts.extract_bgg import run_bgg_extraction

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
        python_callable=run_hero_extraction,
    )

    task_extract_redbutton = PythonOperator(
        task_id='extract_redbutton_data',
        python_callable=run_redbutton_extraction,
    )

    task_extract_boardlife = PythonOperator(
        task_id='extract_boardlife_data',
        python_callable=run_boardlife_extraction,
    )

    task_extract_bgg = PythonOperator(
        task_id='extract_bgg_data',
        python_callable=run_bgg_extraction,
    )

    task_integrate_load = PythonOperator(
        task_id='integrate_and_load_to_db',
        python_callable=run_integration_and_load,
    )

    task_extract_boardlife >> task_extract_bgg
    
    [task_extract_hero, task_extract_redbutton, task_extract_bgg] >> task_integrate_load