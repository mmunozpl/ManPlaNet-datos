#!/usr/bin/env python3
"""NetScaler ADC y Gateway en las listas de vulnerabilidades explotadas.

Toma del catálogo KEV de CISA las entradas de NetScaler ADC y NetScaler
Gateway (también con su nombre anterior, Citrix ADC y Gateway; fuera las de
SD-WAN), y cruza cada una con tres fuentes públicas: la fecha de publicación
del CVE en la API 2.0 del NVD, la marca de explotada en la EUVD de ENISA con
la fecha de cada fuente (CISA o el EU KEV europeo) y las observaciones de
honeypot que la EUVD recoge de Shadowserver.

Deja al lado:

- `altas.csv`: una fila por CVE con las fechas, las diferencias en días, el
  plazo y la marca de triaje forense del KEV, y la última lectura de honeypot;
- `por-anio.csv`: altas por año y cuántas entraron el mismo día en que se
  publicó el CVE;
- `informes-ajenos.csv`: las fechas de inicio de explotación que solo
  constan en informes de terceros, transcritas con su fuente; no salen de
  ninguna API y se guardan aparte para que no se confundan con lo medido;
- `resumen.json` y la ficha de procedencia `INSTANTANEA.md`.

No redistribuye ningún catálogo: son identificadores públicos, fechas y
recuentos. No interviene ningún dato de ninguna persona.
"""
import csv
import datetime
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

DESTINO = Path(__file__).resolve().parent   # escribe junto a sí mismo
KEV = ("https://www.cisa.gov/sites/default/files/feeds/"
       "known_exploited_vulnerabilities.json")
NVD = "https://services.nvd.nist.gov/rest/json/cves/2.0?cveId="
EUVD = "https://euvdservices.enisa.europa.eu/api/"
AGENTE = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
APERTURA_KEV = "2021-11-03"   # carga inicial del catálogo: fecha sin señal

# fechas que solo dan los informes de respuesta a incidentes; se transcriben
# con su fuente y su grado de precisión, tal como las escribe cada informe
INFORMES = [
    {"cve": "CVE-2026-88772", "hecho": "explotación en curso",
     "fecha": "2026-09-01", "precision": "al menos desde primeros de "
     "septiembre (since at least early September)",
     "fuente": "Google Threat Intelligence Group, 29-09-2026",
     "url": "https://cloud.google.com/blog/topics/threat-intelligence/"
            "defending-against-active-exploitation-of-citrix-netscaler-"
            "adc-and-gateway-appliances"},
    {"cve": "CVE-2026-88771", "hecho": "primer intento de explotación visto",
     "fecha": "2026-09-20", "precision": "2026-09-20T14:28:43 UTC",
     "fuente": "Rapid7, 28-09-2026, actualizado el 30-09-2026",
     "url": "https://www.rapid7.com/blog/post/etr-zero-day-exploitation-"
            "of-citrix-netscaler-adc-and-gateway-cve-2026-88771-and-cve-"
            "2026-88772/"},
    {"cve": "CVE-2026-8452", "hecho": "demostración de ejecución remota",
     "fecha": "2026-08-14", "precision": "día de la publicación",
     "fuente": "watchTowr Labs, 14-08-2026",
     "url": "https://labs.watchtowr.com/youre-back-in-the-room-citrix-"
            "netscaler-pre-auth-rce-cve-2026-8452/"},
    {"cve": "CVE-2026-19490", "hecho": "primeros informes de explotación",
     "fecha": "2026-09-04", "precision": "día del informe; tras publicarse "
     "código de explotación a primeros de septiembre",
     "fuente": "Field Effect, 04-09-2026",
     "url": "https://fieldeffect.com/blog/early-exploitation-citrix-"
            "netscaler-vulnerability"},
]


def leer_json(url: str, intentos: int = 4) -> dict:
    """descarga un json con reintentos; el NVD corta sin clave a 5 por 30 s."""
    for i in range(intentos):
        try:
            req = urllib.request.Request(url, headers=AGENTE)
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.load(r)
        except Exception:
            if i == intentos - 1:
                raise
            time.sleep(10 * (i + 1))
    return {}


def fecha_euvd(s: str | None) -> str:
    """«Sep 27, 2026, 12:00:00 AM» a «2026-09-27»."""
    if not s:
        return ""
    return datetime.datetime.strptime(
        s.split(", ")[0] + ", " + s.split(", ")[1], "%b %d, %Y").date(
    ).isoformat()


def dias(a: str, b: str) -> int | str:
    """días naturales de a hasta b; vacío si falta alguna."""
    if not a or not b:
        return ""
    return (datetime.date.fromisoformat(b)
            - datetime.date.fromisoformat(a)).days


def es_netscaler(x: dict) -> bool:
    """NetScaler ADC y Gateway, con su nombre anterior; fuera SD-WAN."""
    p = x["product"]
    return (x["vendorProject"] == "Citrix" and "SD-WAN" not in p.replace(
        "SD-WAN WANOP", "") and p.startswith(
        ("NetScaler", "Application Delivery Controller")))


def main() -> None:
    cat = leer_json(KEV)
    filas_kev = sorted((x for x in cat["vulnerabilities"] if es_netscaler(x)),
                       key=lambda x: (x["dateAdded"], x["cveID"]))
    print(f"KEV {cat['catalogVersion']}: {len(filas_kev)} entradas de "
          "NetScaler ADC y Gateway")

    filas = []
    for x in filas_kev:
        cve = x["cveID"]
        # se pide la ficha al NVD, con pausa por la cuota sin clave
        nvd = leer_json(NVD + cve)["vulnerabilities"][0]["cve"]
        time.sleep(6.5)
        cvss = ""
        for m in ("cvssMetricV40", "cvssMetricV31"):
            for v in nvd.get("metrics", {}).get(m, []):
                if v.get("type") == "Secondary" or v.get("source") != \
                        "nvd@nist.gov":
                    cvss = cvss or f"{v['cvssData']['baseScore']} " \
                        f"({m[10:]})"
        # la entrada de la EUVD, sus fuentes de explotada y su honeypot
        bus = leer_json(EUVD + "search?text=" + urllib.parse.quote(cve)
                        + "&page=0&size=10")
        euvd = next((e for e in bus.get("items", [])
                     if cve in e.get("aliases", "").split()), None)
        eid = euvd["id"] if euvd else ""
        fuentes, honey = {}, {}
        if eid:
            k = leer_json(EUVD + "kevEntries/batch?ids=" + eid).get(eid, [])
            fuentes = {f["kevSource"]["code"]: fecha_euvd(f["dateAdded"])
                       for f in k}
            h = leer_json(EUVD + "honeypotObservations/batch?ids="
                          + eid).get(eid, [])
            honey = h[0] if h else {}
        pub = nvd["published"][:10]
        filas.append({
            "cve": cve, "euvd": eid,
            "publicado_nvd": pub,
            "alta_kev": x["dateAdded"],
            "dias_publicacion_a_kev": dias(pub, x["dateAdded"]),
            "mismo_dia": int(pub == x["dateAdded"]),
            "plazo_kev_dias": dias(x["dateAdded"], x["dueDate"]),
            "triaje_forense": x.get("forensicTriage", ""),
            "ransomware": x.get("knownRansomwareCampaignUse", ""),
            "alta_eu_kev": fuentes.get("EUKEV", ""),
            "eu_kev_menos_cisa_dias": dias(x["dateAdded"],
                                           fuentes.get("EUKEV", "")),
            "cvss_cna": cvss,
            "cwe": x.get("cwes", [""])[0] if x.get("cwes") else "",
            "honeypot_primera": fecha_euvd(honey.get("firstSeenAt")),
            "honeypot_ultima": fecha_euvd(honey.get("lastSeenAt")),
            "honeypot_conexiones_1d": honey.get("connections1d", ""),
            "honeypot_ips_1d": honey.get("uniqueIps1d", ""),
            "honeypot_menos_kev_dias": dias(
                x["dateAdded"], fecha_euvd(honey.get("firstSeenAt"))),
        })
        print(f"  {cve}  NVD {pub}  KEV {x['dateAdded']}  "
              f"EU KEV {fuentes.get('EUKEV', '-')}  honeypot "
              f"{fecha_euvd(honey.get('firstSeenAt')) or '-'}")

    with open(DESTINO / "altas.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0]))
        w.writeheader(); w.writerows(filas)

    # recuentos sobre las altas posteriores a la carga inicial del catálogo
    post = [r for r in filas if r["alta_kev"] > APERTURA_KEV]
    anios: dict[str, dict] = {}
    for r in post:
        a = anios.setdefault(r["alta_kev"][:4], {"altas": 0, "mismo_dia": 0})
        a["altas"] += 1
        a["mismo_dia"] += r["mismo_dia"]
    with open(DESTINO / "por-anio.csv", "w", newline="",
              encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["anio", "altas", "mismo_dia"])
        for a in sorted(anios):
            w.writerow([a, anios[a]["altas"], anios[a]["mismo_dia"]])

    with open(DESTINO / "informes-ajenos.csv", "w", newline="",
              encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(INFORMES[0]))
        w.writeheader(); w.writerows(INFORMES)

    tardias = sorted(r["dias_publicacion_a_kev"] for r in post
                     if not r["mismo_dia"])
    hoy = datetime.date.today().isoformat()
    resumen = {
        "extraido": hoy,
        "kev_version": cat["catalogVersion"],
        "kev_publicado": cat["dateReleased"],
        "kev_entradas": cat["count"],
        "netscaler_en_kev": len(filas),
        "en_carga_inicial": len(filas) - len(post),
        "posteriores_carga_inicial": len(post),
        "mismo_dia_que_publicacion": sum(r["mismo_dia"] for r in post),
        "dias_publicacion_a_kev_resto": tardias,
        "por_anio": anios,
        "triaje_forense_si": [r["cve"] for r in filas
                              if r["triaje_forense"] == "Yes"],
        "con_eu_kev": [r["cve"] for r in filas if r["alta_eu_kev"]],
        "eu_kev_antes_que_cisa": [r["cve"] for r in filas
                                  if r["eu_kev_menos_cisa_dias"] != ""
                                  and r["eu_kev_menos_cisa_dias"] < 0],
        "con_honeypot": [r["cve"] for r in filas if r["honeypot_primera"]],
    }
    (DESTINO / "resumen.json").write_text(
        json.dumps(resumen, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8")

    ficha = f"""# NetScaler ADC y Gateway en las listas de explotadas

Las entradas de NetScaler ADC y NetScaler Gateway (con su nombre anterior,
Citrix ADC y Gateway; fuera las de SD-WAN) del catálogo KEV de CISA,
cruzadas con la fecha de publicación de cada CVE en el NVD y con la EUVD de
ENISA: fuente y fecha de la marca de explotada, y observaciones de honeypot
de Shadowserver. No se redistribuye ningún catálogo. No interviene ningún
dato de ninguna persona.

- KEV: {KEV}, versión `{cat['catalogVersion']}`, publicada
  {cat['dateReleased']}, {cat['count']} entradas
- NVD: API 2.0, `{NVD}<CVE>`, campo `published`
- EUVD: `{EUVD}search?text=<CVE>`, `kevEntries/batch` y
  `honeypotObservations/batch`
- Extraído: {hoy}

## Ficheros

| Fichero | Contenido |
|---|---|
| `altas.csv` | una fila por CVE: id EUVD, publicación en el NVD, alta en el KEV, días entre las dos, si coinciden, plazo y triaje forense del KEV, uso conocido en ransomware, alta en el EU KEV y su diferencia con CISA, CVSS de la CNA, CWE, y primera y última observación de honeypot con las conexiones y las IP del último día |
| `por-anio.csv` | altas por año desde la carga inicial y cuántas entraron el mismo día de la publicación |
| `informes-ajenos.csv` | fechas de inicio de explotación que solo constan en informes de terceros, con su fuente; no son medición |
| `resumen.json` | los recuentos de arriba |

## Cómo se cuenta

Las {len(filas) - len(post)} entradas con alta del {APERTURA_KEV} son la
carga inicial del catálogo y su fecha no dice cuándo se supo de la
explotación: se listan, pero no entran en los recuentos por año ni en la
coincidencia de fechas. «Mismo día» compara la fecha `published` del NVD
con `dateAdded` del KEV; en NetScaler la CNA es Citrix y publica el CVE el
día de su boletín. La fecha del EU KEV y la de honeypot son las que sirve
la EUVD; la de honeypot es la primera vez que los sensores de Shadowserver
reconocen un intento, y solo puede existir después de que haya una firma que
lo reconozca. Las conexiones y las IP son las del último día observado, no
un promedio.
"""
    (DESTINO / "INSTANTANEA.md").write_text(ficha, encoding="utf-8")
    print(f"se guarda en {DESTINO}")


if __name__ == "__main__":
    main()
