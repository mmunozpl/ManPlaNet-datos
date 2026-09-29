# Entorno de los cuadernos de ManPlaNet-datos, con las versiones fijadas.
#
#   docker build -t manplanet-datos .
#   docker run --rm manplanet-datos                      # ejecuta los cuadernos
#   docker run --rm -p 8888:8888 manplanet-datos jupyter lab \
#       --ip 0.0.0.0 --no-browser                        # los abre en el navegador
#
# Las dos imágenes de partida van por huella, no por etiqueta: una etiqueta
# puede apuntar mañana a otro contenido; una huella, no.

FROM ghcr.io/astral-sh/uv:0.9.8@sha256:08f409e1d53e77dfb5b65c788491f8ca70fe1d2d459f41c89afa2fcbef998abe AS uv

FROM python:3.11.14-slim-bookworm@sha256:65a93d69fa75478d554f4ad27c85c1e69fa184956261b4301ebaf6dbb0a3543d

COPY --from=uv /uv /usr/local/bin/uv

ENV UV_PROJECT_ENVIRONMENT=/opt/entorno \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    PATH=/opt/entorno/bin:$PATH

WORKDIR /datos

# primero el bloqueo: la capa del entorno solo se rehace si cambia
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --group interactivo

COPY . .

# sin privilegios dentro del contenedor
RUN useradd --create-home --uid 1000 lector \
    && chown -R lector:lector /datos
USER lector

EXPOSE 8888
CMD ["python", "comprobar.py"]
