"""Acceso al almacén de objetos compatible con S3 del laboratorio (RustFS):
el mismo cliente boto3 que se usaría contra S3, apuntado a otro endpoint."""
import os

import boto3
from botocore.config import Config


def cliente():
    return boto3.client(
        "s3", endpoint_url=os.environ["S3_ENDPOINT"],
        aws_access_key_id=os.environ["S3_ACCESS_KEY"],
        aws_secret_access_key=os.environ["S3_SECRET_KEY"],
        region_name="us-east-1",
        config=Config(s3={"addressing_style": "path"}, retries={"max_attempts": 5}))


def bucket() -> str:
    return os.environ.get("S3_BUCKET", "datalake")


def asegurar_bucket() -> None:
    c = cliente()
    existentes = {b["Name"] for b in c.list_buckets().get("Buckets", [])}
    if bucket() not in existentes:
        c.create_bucket(Bucket=bucket())


def subir(ruta_local: str, clave: str) -> int:
    c = cliente()
    c.upload_file(ruta_local, bucket(), clave)
    return os.path.getsize(ruta_local)


def subir_bytes(datos: bytes, clave: str) -> int:
    cliente().put_object(Bucket=bucket(), Key=clave, Body=datos)
    return len(datos)


def descargar(clave: str) -> bytes:
    return cliente().get_object(Bucket=bucket(), Key=clave)["Body"].read()


def listar(prefijo: str) -> list[str]:
    c = cliente()
    claves, token = [], None
    while True:
        kw = dict(Bucket=bucket(), Prefix=prefijo)
        if token:
            kw["ContinuationToken"] = token
        r = c.list_objects_v2(**kw)
        claves += [o["Key"] for o in r.get("Contents", [])]
        if not r.get("IsTruncated"):
            return claves
        token = r.get("NextContinuationToken")
