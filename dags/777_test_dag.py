from datetime import datetime

from airflow import DAG
from airflow.operators.empty import EmptyOperator


with DAG(
    dag_id="777_test_dag",
    start_date=datetime(2024, 1, 1),
    schedule="@daily",
    catchup=False,
    tags=["777"],
) as dag:
    start = EmptyOperator(task_id="start")
    end = EmptyOperator(task_id="end")

    start >> end
