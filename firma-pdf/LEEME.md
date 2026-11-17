# Firma de PDF con certificado de la FNMT: la herramienta y su medición

Una aplicación de escritorio que firma documentos PDF en formato PAdES con un
certificado de la FNMT (u otro cualificado), les pone un pie de firma visible
en cada página con un código QR, pide un sello cualificado de tiempo,
comprueba firmas contra la raíz de la FNMT y envía el documento a VALIDe con
el código de seguridad que escribe la persona. Y la medición que respalda la
entrada que la cuenta.

| Carpeta o fichero | Qué es |
|---|---|
| `herramienta/` | el código de la aplicación: `firmar.py` (pie, firma, comprobación, VALIDe), `almacenes.py` (certificados instalados en Linux, Windows y macOS), `firma_gui.py` (ventana en Qt), `construir.py` (ejecutable con PyInstaller) y su entorno fijado (`pyproject.toml`, `uv.lock`) |
| `herramienta/confianza/` | la raíz de la FNMT (`fnmt-raiz.pem`, SHA-256 `ebc5570c…93fa`) y la CA de sellado cualificado de Sectigo (Europe) SL, tomada de la lista de confianza española |
| `generar.py` | la medición: firma un documento real con una CA de pruebas, valida, mide el QR y lee la lista de confianza |
| `datos/` | lo que escribe `generar.py` |

## Qué mide `generar.py`

1. Descarga el PDF del *NIST Cybersecurity Framework 2.0* (CSWP 29, 32
   páginas, sin firma previa), comprueba su SHA-256 y guarda las tres
   primeras páginas en `datos/documento.pdf`.
2. Crea una autoridad de certificación de pruebas y un firmante ficticio con
   la forma de un certificado de la FNMT (`datos/ac-pruebas.pem`,
   `datos/firmante-prueba.p12`, contraseña `prueba`). Es la única pieza
   sintética: un certificado real no se puede publicar.
3. Firma con la herramienta sin sello de tiempo (cinco veces) y con el sello
   cualificado de Sectigo (tres veces, con 16 s de pausa entre peticiones),
   mide tiempo y bytes, y valida cada firma; repite la validación con un byte
   del contenido alterado.
4. Lee con ZXing el QR del pie, dibujado a su tamaño real y rasterizado a
   600 ppp, reducido a resoluciones de 60 a 300 ppp, para cuatro contenidos.
5. Descarga la lista de confianza española (`tsl.digital.gob.es/TSL.xml`) y
   extrae sus servicios de sellado de tiempo cualificado (`TSA/QTST`).
6. Guarda el pie de la última página en `datos/pie.png`.

| Fichero de `datos/` | Contenido |
|---|---|
| `resumen.json` | fecha, carga del sistema, documento y su huella, geometría del pie, tiempos y bytes de cada firma, resultado de cada validación, versiones, y la lista de confianza (emisión, huella y recuentos) |
| `qr_legibilidad.csv` | contenido del QR, bytes, módulos por lado, milímetros por módulo, resolución y si ZXing lo leyó |
| `tsl_sellado_cualificado.csv` | prestador, servicio, estado (`granted` o `withdrawn`) y fecha del estado |
| `firmado-sin-sello.pdf`, `firmado-sello-cualificado.pdf` | los documentos firmados por la medición |
| `pie.png` | el pie de la última página, sin metadatos |

Ningún dato de ninguna persona interviene: el firmante es ficticio y su número
de documento, inventado.

## Reproducir

Requisitos: Python 3.11, `pdftoppm` (poppler) y red. Unos 60 segundos.

```bash
cd herramienta && uv sync --frozen && cd ..
uv pip install --python herramienta/.venv zxing-cpp==3.1.1 tqdm
herramienta/.venv/bin/python generar.py            # con sello cualificado
herramienta/.venv/bin/python generar.py --sin-red-sello
herramienta/.venv/bin/python generar.py --app RUTA/dist   # mide una construcción
```

Las firmas cambian en cada ejecución (claves nuevas, fecha y sello), así que
las huellas de los PDF firmados no se repiten; los recuentos de la lista de
confianza cambian cuando el Ministerio publica una edición nueva.

## La aplicación

```bash
cd herramienta
uv sync --frozen
uv run python firma_gui.py                 # ventana
uv run python firmar.py --help             # línea de órdenes
uv run --group construir python construir.py   # ejecutable del sistema
```

PyInstaller construye solo para el sistema en que se ejecuta: el ejecutable de
Windows se construye en Windows y el de macOS en macOS
(`.github/workflows/construir.yml` lo hace en los tres). Los ejecutables no van
firmados con un certificado de firma de código, así que Windows y macOS avisan
al abrirlos. La lectura de certificados instalados se ha probado en Linux; la
de Windows y la de macOS están escritas y sin probar.

`herramienta/` es la copia con la que se hizo la medición. La aplicación publicada, con los ejecutables de Linux, Windows y macOS y sus huellas, vive en [mmunozpl/firma-pdf](https://github.com/mmunozpl/firma-pdf). Se publica tal cual, sin garantía, sin mantenimiento y sin soporte, y su uso corre por cuenta y bajo la responsabilidad de quien la use.

Licencia: Apache-2.0, como el resto del repositorio.
