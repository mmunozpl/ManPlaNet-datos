"""DAG mensual de la plataforma: descarga de la API (o de la caché), zona
cruda al S3, Parquet preparado, COPY a PostgreSQL y, con dbt, el modelo en
estrella, sus tests y la snapshot de la dimensión con historia. Un run por
mes, con relleno histórico desde enero de 2024; reintentos con espera
exponencial y aviso en el registro cuando una tarea falla del todo. El
parámetro fallos_simulados (0 por defecto) hace fallar a propósito los
primeros intentos de la primera tarea, para medir reintentos y aviso."""
import datetime as dt
import os
from datetime import timedelta

import pendulum
from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import dag, task

PROYECTO = "es.wikipedia"
DBT = ("cd /opt/proyecto-dbt && /opt/dbt/bin/dbt {orden} --profiles-dir /opt/proyecto-dbt "
       "--target-path /opt/airflow/dbt-destino/target --log-path /opt/airflow/dbt-destino/logs "
       "--vars '{{\"estrategia\": \"{estrategia}\"}}'")


def avisar(context) -> None:
    """Lo que en producción sería un correo o un canal: aquí, una línea
    inequívoca en el registro del scheduler, que el medidor recoge."""
    ti = context["task_instance"]
    print(f"AVISO: la tarea {ti.task_id} del run {context['run_id']} ha fallado "
          f"tras {ti.try_number - 1} intento(s)")


@dag(
    dag_id="visualizaciones_mensual",
    schedule="@monthly",
    start_date=pendulum.datetime(2024, 1, 1, tz="UTC"),
    end_date=pendulum.datetime(2026, 10, 31, tz="UTC"),  # el último run es el de octubre de 2026
    catchup=True,
    max_active_runs=1,
    default_args=dict(retries=3, retry_delay=timedelta(seconds=30),
                      retry_exponential_backoff=True, on_failure_callback=avisar),
    tags=["datamart", "wikipedia"],
    params={"fallos_simulados": 0},
    doc_md=__doc__,
)
def visualizaciones_mensual():

    @task
    def descargar(data_interval_start=None, params=None, ti=None) -> dict:
        """La zona cruda nace aquí: un JSON por día y acceso, tal cual lo
        sirve la API; si la caché del laboratorio ya lo tiene, no se pide.
        Con fallos_simulados = n, los n primeros intentos fallan a propósito:
        con 1 el reintento recupera el run; con 4 (tres reintentos) la tarea
        falla del todo y salta el aviso."""
        from ingesta.descargar import descargar_dia
        from ingesta.preparar import ACCESOS, dias_del_mes
        if ti.try_number <= int((params or {}).get("fallos_simulados") or 0):
            raise RuntimeError(f"fallo simulado en el intento {ti.try_number} (fallos_simulados)")
        d = data_interval_start
        resumen = {}
        for acceso in ACCESOS:
            for dia in dias_del_mes(d.year, d.month):
                r = descargar_dia(PROYECTO, acceso, dt.date(dia.year, dia.month, dia.day), os.environ["CACHE_CRUDO"])
                resumen[r["estado"]] = resumen.get(r["estado"], 0) + 1
                if r["estado"].startswith("error"):
                    raise RuntimeError(f"la API no respondió para {acceso} {dia}: {r['estado']}")
        return resumen

    @task
    def subir(data_interval_start=None) -> dict:
        from ingesta import s3
        from ingesta.preparar import subir_mes
        s3.asegurar_bucket()
        d = data_interval_start
        return subir_mes(os.environ["CACHE_CRUDO"], PROYECTO, d.year, d.month)

    @task
    def preparar(data_interval_start=None) -> dict:
        from ingesta.preparar import preparar_mes
        d = data_interval_start
        return preparar_mes(PROYECTO, d.year, d.month)

    @task
    def cargar(data_interval_start=None) -> dict:
        from ingesta.preparar import cargar_mes
        d = data_interval_start
        return cargar_mes(PROYECTO, d.year, d.month, os.environ["DATAMART_DSN"])

    estrategia = os.environ.get("DBT_ESTRATEGIA", "delete+insert")
    dbt_seed = BashOperator(task_id="dbt_seed", bash_command=DBT.format(orden="seed", estrategia=estrategia))
    dbt_run = BashOperator(task_id="dbt_run", bash_command=DBT.format(orden="run", estrategia=estrategia))
    dbt_test = BashOperator(task_id="dbt_test", bash_command=DBT.format(orden="test", estrategia=estrategia))
    dbt_snapshot = BashOperator(task_id="dbt_snapshot", bash_command=DBT.format(orden="snapshot", estrategia=estrategia))

    descargar() >> subir() >> preparar() >> cargar() >> dbt_seed >> dbt_run >> dbt_test >> dbt_snapshot


visualizaciones_mensual()
