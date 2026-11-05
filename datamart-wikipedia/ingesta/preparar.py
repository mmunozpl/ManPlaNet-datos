"""Las tres etapas de un mes en la plataforma, pensadas para ser tareas de
Airflow: subir la zona cruda (los JSON tal cual) al almacén S3, prepararla
(un Parquet por acceso y mes, con los tipos ya fijados) y cargarla en la
tabla de aterrizaje de PostgreSQL con COPY, de forma idempotente (el mes se
borra y se vuelve a cargar en la misma transacción)."""
import datetime as dt
import gzip
import io
import json
import os
import time

import pyarrow as pa
import pyarrow.csv as pcsv
import pyarrow.parquet as pq

from ingesta import s3

ACCESOS = ["all-access", "desktop", "mobile-web", "mobile-app"]
ESQUEMA = pa.schema([
    ("proyecto", pa.string()), ("acceso", pa.string()), ("fecha", pa.date32()),
    ("articulo", pa.string()), ("visitas", pa.int64()), ("posicion", pa.int32()),
])


def dias_del_mes(anio: int, mes: int) -> list[dt.date]:
    primero = dt.date(anio, mes, 1)
    siguiente = dt.date(anio + (mes == 12), (mes % 12) + 1, 1)
    return [primero + dt.timedelta(d) for d in range((siguiente - primero).days)]


def ruta_cruda(cache: str, acceso: str, dia: dt.date) -> str:
    return os.path.join(cache, "crudo", acceso, f"{dia:%Y}", f"{dia:%m}", f"{dia:%d}.json.gz")


def clave_cruda(proyecto: str, acceso: str, dia: dt.date) -> str:
    return f"crudo/{proyecto}/{acceso}/{dia:%Y}/{dia:%m}/{dia:%d}.json.gz"


def clave_parquet(proyecto: str, acceso: str, anio: int, mes: int) -> str:
    return f"preparado/{proyecto}/acceso={acceso}/anio={anio}/mes={mes:02d}/datos.parquet"


def subir_mes(cache: str, proyecto: str, anio: int, mes: int) -> dict:
    """Zona cruda al S3: cada JSON del mes, sin tocar; los días sin datos
    (marca .404) quedan anotados en el resultado."""
    subidos, sin_datos, octetos = 0, 0, 0
    for acceso in ACCESOS:
        for dia in dias_del_mes(anio, mes):
            ruta = ruta_cruda(cache, acceso, dia)
            if os.path.exists(ruta):
                octetos += s3.subir(ruta, clave_cruda(proyecto, acceso, dia)); subidos += 1
            elif os.path.exists(ruta + ".404"):
                sin_datos += 1
    return dict(ficheros=subidos, sin_datos=sin_datos, octetos=octetos)


def preparar_mes(proyecto: str, anio: int, mes: int) -> dict:
    """Zona preparada: los JSON del mes de cada acceso, leídos del S3, pasan
    a un Parquet con tipos (fecha, enteros) y una fila por artículo y día."""
    filas_total, octetos = 0, 0
    for acceso in ACCESOS:
        columnas = {c: [] for c in ESQUEMA.names}
        for dia in dias_del_mes(anio, mes):
            try:
                crudo = s3.descargar(clave_cruda(proyecto, acceso, dia))
            except s3.cliente().exceptions.NoSuchKey:
                continue
            items = json.loads(gzip.decompress(crudo))["items"]
            for it in items:
                for a in it["articles"]:
                    columnas["proyecto"].append(proyecto); columnas["acceso"].append(acceso)
                    columnas["fecha"].append(dia); columnas["articulo"].append(a["article"])
                    columnas["visitas"].append(a["views"]); columnas["posicion"].append(a["rank"])
        tabla = pa.table(columnas, schema=ESQUEMA)
        buf = io.BytesIO()
        pq.write_table(tabla, buf, compression="zstd")
        octetos += s3.subir_bytes(buf.getvalue(), clave_parquet(proyecto, acceso, anio, mes))
        filas_total += tabla.num_rows
    return dict(filas=filas_total, octetos=octetos)


def cargar_mes(proyecto: str, anio: int, mes: int, dsn: str) -> dict:
    """De la zona preparada a la tabla de aterrizaje con COPY: el Parquet
    del mes se vuelca como CSV por la entrada estándar de COPY (lo que en
    Aurora haría aws_s3.table_import_from_s3), tras borrar el mes en la
    misma transacción, para que repetir la tarea no duplique."""
    import psycopg
    t0 = time.time()
    filas = 0
    with psycopg.connect(dsn) as con:
        with con.cursor() as cur:
            cur.execute("DELETE FROM crudo.visualizaciones_top WHERE proyecto = %s AND fecha >= %s AND fecha < %s",
                        (proyecto, dt.date(anio, mes, 1), dt.date(anio + (mes == 12), (mes % 12) + 1, 1)))
            for acceso in ACCESOS:
                try:
                    datos = s3.descargar(clave_parquet(proyecto, acceso, anio, mes))
                except s3.cliente().exceptions.NoSuchKey:
                    continue
                tabla = pq.read_table(io.BytesIO(datos))
                if tabla.num_rows == 0:
                    continue
                buf = io.BytesIO()
                pcsv.write_csv(tabla, buf, pcsv.WriteOptions(include_header=False))
                with cur.copy("COPY crudo.visualizaciones_top (proyecto, acceso, fecha, articulo, visitas, posicion) FROM STDIN WITH (FORMAT csv)") as copia:
                    copia.write(buf.getvalue())
                filas += tabla.num_rows
        con.commit()
    return dict(filas=filas, segundos=round(time.time() - t0, 2))
