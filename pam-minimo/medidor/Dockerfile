# medidor del laboratorio: Python con el ssh de OpenSSH (entra por el
# bastión con contraseña y TOTP contestados por un askpass), paramiko (entra
# en el servidor con un certificado de la bóveda) y psycopg (PostgreSQL).
# El usuario del contenedor se crea con el uid y gid del anfitrión para que
# los CSV queden a su nombre y ssh encuentre su cuenta.
FROM python:3.12.16-slim
ARG UID=1000
ARG GID=1000
RUN apt-get update && apt-get install -y --no-install-recommends \
        openssh-client && \
    rm -rf /var/lib/apt/lists/* && \
    groupadd -g "$GID" medidor && \
    useradd -u "$UID" -g "$GID" -m medidor
COPY requisitos.txt /requisitos.txt
RUN pip install --no-cache-dir -r /requisitos.txt
COPY medir.py /medir.py
USER medidor
WORKDIR /salida
CMD ["python", "/medir.py"]
