# medidor del laboratorio: Python con psycopg (banco de consultas y cargas),
# boto3 (zona cruda en S3) y pyarrow (Parquet); el usuario se crea con el uid
# del anfitrión para que los CSV queden a su nombre
FROM python:3.12.16-slim
ARG UID=1000
ARG GID=1000
RUN groupadd -g "$GID" medidor && useradd -u "$UID" -g "$GID" -m medidor
COPY requisitos.txt /requisitos.txt
RUN pip install --no-cache-dir -r /requisitos.txt
COPY medir.py /medir.py
USER medidor
WORKDIR /salida
CMD ["python", "/medir.py"]
