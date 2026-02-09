import json
import logging
from datetime import datetime
from urllib.request import Request, urlopen

from airflow import DAG
from airflow.hooks.base import BaseHook
from airflow.operators.python import PythonOperator


def check_s3_http_conn(conn_id: str) -> None:
    conn = BaseHook.get_connection(conn_id)
    extra = conn.extra or "{}"
    try:
        extra_json = json.loads(extra)
    except Exception:
        extra_json = {}

    endpoint_url = extra_json.get("endpoint_url")
    if endpoint_url:
        url = endpoint_url.rstrip("/")
    else:
        schema = conn.schema or "http"
        host = conn.host
        port = f":{conn.port}" if conn.port else ""
        url = f"{schema}://{host}{port}"

    logging.info("Using URL: %s", url)

    req = Request(url, method="GET")
    with urlopen(req, timeout=10) as resp:
        status = resp.status
        body = resp.read(200)

    logging.info("HTTP status: %s", status)
    logging.info("Body (first 200 bytes): %r", body)


with DAG(
    dag_id="777_s3_http_check",
    start_date=datetime(2024, 1, 1),
    schedule="@daily",
    catchup=False,
    tags=["777", "s3", "http"],
) as dag:
    PythonOperator(
        task_id="check_s3_http",
        python_callable=check_s3_http_conn,
        op_kwargs={"conn_id": "s3_http"},
    )
