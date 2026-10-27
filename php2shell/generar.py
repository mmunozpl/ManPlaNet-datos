"""PHP2Shell (CVE-2026-109618 y CVE-2026-109619): avisos, parches y ramas.

Se mide, sobre fuentes públicas con API, cuánto tardó cada aviso, cuándo
llegó el parche a cada sistema y qué parte de los WordPress corre una rama
de PHP sin parche oficial:

1. ``kev``: las entradas del catálogo KEV de CISA con la fecha de
   publicación de su CVE en el NVD (filtro ``hasKev`` de la API 2.0), para
   situar la demora de PHP2Shell (del CVE al catálogo) en la distribución
   de todo el catálogo.
2. ``fichas``: las dos CVE en el NVD, en la EUVD de ENISA y en los avisos
   de seguridad de GitHub del proyecto PHP (fechas y puntuaciones).
3. ``sistemas``: cuándo publicó cada sistema su versión corregida (Ubuntu
   por su API de CVE, Red Hat por su API de datos de seguridad, Debian por
   el rastreador y sus anuncios, Alpine por los commits de aports y la
   imagen oficial de Docker por las etiquetas de Docker Hub).
4. ``wordpress``: la cuota de cada versión de PHP entre los WordPress que
   informan a WordPress.org, agrupada en ramas con parche binario, ramas
   con parche solo de fuente y ramas sin parche.
5. ``ncsc``: la lista TLP:CLEAR de productos que dependen de PHP que
   mantiene el NCSC de los Países Bajos, contada por estado.

Cada etapa escribe sus CSV junto a este fichero. ``cronologia.csv`` se
mantiene a mano con las fechas de las fuentes que no tienen API.

Uso::

    python generar.py                 # todas las etapas
    python generar.py --etapa kev     # una sola
"""

import argparse
import csv
import json
import random
import re
import statistics
import subprocess
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

DIR = Path(__file__).resolve().parent
# el NVD devuelve 403 a los agentes largos
UA = "ManPlaNet"
SEMILLA = 20261027
CVES = ["CVE-2026-109618", "CVE-2026-109619"]
# publicación de los parches: php.net, 21-10-2026, 14:00 UTC; las etiquetas
# de php-src llevan 14:06 a 14:09
PARCHE_UTC = datetime(2026, 10, 21, 14, 0, tzinfo=timezone.utc)
VERSIONES = {"8.5": "8.5.12", "8.4": "8.4.27", "8.3": "8.3.36",
             "8.2": "8.2.35"}
KEV_URL = ("https://www.cisa.gov/sites/default/files/feeds/"
           "known_exploited_vulnerabilities.json")
NVD_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"
EUVD_URL = "https://euvdservices.enisa.europa.eu/api/search"
UBUNTU_URL = "https://ubuntu.com/security/cves/{cve}.json"
REDHAT_URL = ("https://access.redhat.com/hydra/rest/securitydata/cve/"
              "{cve}.json")
DEBIAN_URL = "https://security-tracker.debian.org/tracker/{cve}"
DOCKER_URL = ("https://hub.docker.com/v2/repositories/library/php/tags"
              "?name={tag}&page_size=10")
WP_URL = "https://api.wordpress.org/stats/php/1.0/"
# ramas de Alpine con paquetes php8x y la rama de desarrollo
ALPINE_RAMAS = ["3.21-stable", "3.22-stable", "3.23-stable", "master"]


def leer_json(url: str, pausa: float = 0.0) -> dict:
    """Descarga un JSON con el agente corto y una pausa opcional."""
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        datos = json.load(r)
    if pausa:
        time.sleep(pausa)
    return datos


def leer_texto(url: str) -> str:
    """Descarga una página como texto plano, sin etiquetas."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as r:
        t = r.read().decode("utf-8", "replace")
    t = re.sub(r"<script.*?</script>|<style.*?</style>", "", t, flags=re.S)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", t)


def escribir_csv(nombre: str, filas: list[dict], campos: list[str]) -> None:
    """Escribe un CSV junto al guion y muestra 15 filas al azar."""
    ruta = DIR / nombre
    with ruta.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=campos, extrasaction="ignore")
        w.writeheader()
        w.writerows(filas)
    rng = random.Random(SEMILLA)
    muestra = rng.sample(filas, min(15, len(filas)))
    print(f"\n== {nombre}: {len(filas)} filas; {len(muestra)} al azar ==")
    for fila in muestra:
        print({k: (str(v)[:60]) for k, v in fila.items()})


def horas_desde_parche(marca: str) -> float | str:
    """Horas entre la publicación del parche y una marca ISO (UTC)."""
    try:
        d = datetime.fromisoformat(marca.replace("Z", "+00:00"))
    except ValueError:
        return ""
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return round((d - PARCHE_UTC).total_seconds() / 3600, 1)


# --------------------------------------------------------------------
# 1. KEV: demora del CVE al catálogo, para todo el catálogo
# --------------------------------------------------------------------

def etapa_kev() -> None:
    """Cruza el KEV con las fechas de publicación del NVD."""
    kev = leer_json(KEV_URL)
    print("KEV", kev["catalogVersion"], kev["count"], "entradas")
    publicado: dict[str, str] = {}
    inicio, total = 0, None
    while total is None or inicio < total:
        d = leer_json(f"{NVD_URL}?hasKev&resultsPerPage=2000"
                      f"&startIndex={inicio}", pausa=6)
        total = d["totalResults"]
        for v in d["vulnerabilities"]:
            publicado[v["cve"]["id"]] = v["cve"]["published"]
        inicio += d["resultsPerPage"]
    print("NVD hasKev", total, "CVE con fecha de publicación")
    filas = []
    for v in kev["vulnerabilities"]:
        cve = v["cveID"]
        pub = publicado.get(cve, "")
        demora = ""
        if pub:
            d_pub = datetime.fromisoformat(pub).date()
            d_kev = datetime.fromisoformat(v["dateAdded"]).date()
            demora = (d_kev - d_pub).days
        d_due = (datetime.fromisoformat(v["dueDate"]).date()
                 - datetime.fromisoformat(v["dateAdded"]).date()).days
        filas.append({
            "cve": cve, "vendor": v["vendorProject"], "product": v["product"],
            "nvd_publicado": pub[:10], "kev_alta": v["dateAdded"],
            "kev_plazo": v["dueDate"], "plazo_dias": d_due,
            "triaje_forense": v.get("forensicTriage", ""),
            "ransomware": v.get("knownRansomwareCampaignUse", ""),
            "demora_dias": demora,
        })
    filas.sort(key=lambda r: (r["kev_alta"], r["cve"]))
    escribir_csv("kev_demoras.csv", filas,
                 ["cve", "vendor", "product", "nvd_publicado", "kev_alta",
                  "kev_plazo", "plazo_dias", "triaje_forense", "ransomware",
                  "demora_dias"])
    con = [r for r in filas if r["demora_dias"] != ""]
    demoras = sorted(r["demora_dias"] for r in con)
    php = [r for r in filas if r["cve"] in CVES]
    d_php = php[0]["demora_dias"] if php else None

    def resumen(lista: list[int]) -> dict:
        if not lista:
            return {}
        return {
            "n": len(lista), "mediana": statistics.median(lista),
            "p25": lista[len(lista) // 4], "p75": lista[3 * len(lista) // 4],
            "hasta_5_dias": sum(x <= 5 for x in lista),
            "mismo_dia": sum(x <= 0 for x in lista),
            "mas_de_un_ano": sum(x > 365 for x in lista),
        }

    r2026 = sorted(r["demora_dias"] for r in con
                   if r["kev_alta"] >= "2026-01-01")
    r_bod = sorted(r["demora_dias"] for r in con
                   if r["kev_alta"] >= "2026-06-10")
    res = {
        "catalogo_version": kev["catalogVersion"], "entradas": kev["count"],
        "con_fecha_nvd": len(con),
        "todo": resumen(demoras), "altas_2026": resumen(r2026),
        "desde_bod_26_04": resumen(r_bod),
        "php2shell": {
            "demora_dias": d_php,
            "percentil_todo": round(100 * sum(x <= d_php for x in demoras)
                                    / len(demoras), 1) if d_php is not None
            else None,
            "percentil_2026": round(100 * sum(x <= d_php for x in r2026)
                                    / len(r2026), 1) if d_php is not None
            and r2026 else None,
        },
        "triaje_forense_total": sum(r["triaje_forense"] == "Yes"
                                    for r in filas),
        "plazo_3_dias_total": sum(r["plazo_dias"] == 3 for r in filas),
    }
    (DIR / "resumen_kev.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8")
    print(json.dumps(res, ensure_ascii=False, indent=1))


# --------------------------------------------------------------------
# 2. fichas de las dos CVE
# --------------------------------------------------------------------

def etapa_fichas() -> None:
    """NVD, EUVD y GitHub Security Advisories de las dos CVE."""
    filas = []
    for cve in CVES:
        d = leer_json(f"{NVD_URL}?cveId={cve}", pausa=6)
        v = d["vulnerabilities"][0]["cve"]
        m31 = v.get("metrics", {}).get("cvssMetricV31", [])
        m40 = v.get("metrics", {}).get("cvssMetricV40", [])
        e = leer_json(f"{EUVD_URL}?text={cve}&size=5")
        item = next((i for i in e.get("items", [])
                     if cve in json.dumps(i)), {})
        try:
            g = json.loads(subprocess.run(
                ["gh", "api", f"repos/php/php-src/security-advisories"
                 f"?per_page=50", "--jq",
                 f'[.[] | select(.cve_id == "{cve}")] | first'],
                capture_output=True, text=True, timeout=60).stdout or "{}")
        except (json.JSONDecodeError, subprocess.TimeoutExpired):
            g = {}
        filas.append({
            "cve": cve,
            "nvd_publicado": v["published"], "nvd_estado": v["vulnStatus"],
            "cvss31": m31[0]["cvssData"]["baseScore"] if m31 else "",
            "cvss40": m40[0]["cvssData"]["baseScore"] if m40 else "",
            "cwe": ";".join(sorted({x["value"] for w in v.get("weaknesses", [])
                                    for x in w["description"]})),
            "euvd_id": item.get("id", ""),
            "euvd_publicado": item.get("datePublished", ""),
            "euvd_explotada_desde": item.get("exploitedSince", ""),
            "euvd_puntuacion": item.get("baseScore", ""),
            "ghsa": (g or {}).get("ghsa_id", ""),
            "ghsa_publicado": (g or {}).get("published_at", ""),
            "ghsa_resumen": (g or {}).get("summary", ""),
            "descripcion": v["descriptions"][0]["value"][:400],
        })
    escribir_csv("fichas.csv", filas, list(filas[0].keys()))


# --------------------------------------------------------------------
# 3. cuándo llegó el parche a cada sistema
# --------------------------------------------------------------------

def _ubuntu(cve: str) -> list[dict]:
    d = leer_json(UBUNTU_URL.format(cve=cve))
    filas = []
    avisos = {n["id"]: n["published"] for n in d.get("notices", [])}
    primero = min(avisos.values()) if avisos else ""
    for p in d.get("packages", []):
        for s in p.get("statuses", []):
            if s["status"] == "released" and s.get("description"):
                filas.append({
                    "sistema": "Ubuntu", "rama": s["release_codename"],
                    "paquete": p["name"], "version": s["description"],
                    "fecha_utc": primero, "aviso": ";".join(sorted(avisos)),
                    "fuente": UBUNTU_URL.format(cve=cve),
                    "nota": "fecha del primer USN de la CVE (la API no da "
                            "fecha por versión)",
                })
    return filas


def _redhat(cve: str) -> list[dict]:
    d = leer_json(REDHAT_URL.format(cve=cve))
    return [{
        "sistema": "Red Hat", "rama": r.get("product_name", ""),
        "paquete": r.get("package", ""), "version": r.get("package", ""),
        "fecha_utc": r.get("release_date", ""), "aviso": r.get("advisory", ""),
        "fuente": REDHAT_URL.format(cve=cve), "nota": "",
    } for r in d.get("affected_release", [])]


def _debian(cve: str) -> list[dict]:
    t = leer_texto(DEBIAN_URL.format(cve=cve))
    filas = []
    for m in re.finditer(r"(php\d\.\d) source (\w+) ([\w.~+-]+) ([A-Z]{3}-\d+-\d)",
                         t):
        aviso = m.group(4)
        fecha = ""
        try:
            if aviso.startswith("DSA"):
                url = f"https://www.debian.org/security/2026/{aviso[:-2].lower()}"
            else:
                url = f"https://www.debian.org/lts/security/2026/{aviso[:-2].lower()}"
            txt = leer_texto(url)
            f = re.search(r"Date Reported:?\s*(\d{1,2} \w{3} \d{4})", txt) \
                or re.search(r"(\d{1,2} \w{3} \d{4})", txt)
            if f:
                fecha = datetime.strptime(f.group(1), "%d %b %Y").strftime(
                    "%Y-%m-%d")
        except Exception:  # noqa: BLE001 - la fecha es complementaria
            url = DEBIAN_URL.format(cve=cve)
        filas.append({
            "sistema": "Debian", "rama": m.group(2), "paquete": m.group(1),
            "version": m.group(3), "fecha_utc": fecha, "aviso": aviso,
            "fuente": url, "nota": "día del anuncio DSA/DLA",
        })
    return filas


def _alpine() -> list[dict]:
    filas = []
    for rama in ALPINE_RAMAS:
        for pkg, ver in (("php82", "8.2.35"), ("php83", "8.3.36"),
                         ("php84", "8.4.27"), ("php85", "8.5.12")):
            r = subprocess.run(
                ["gh", "api", f"repos/alpinelinux/aports/commits?path="
                 f"community/{pkg}/APKBUILD&sha={rama}&per_page=5",
                 "--jq", "[.[] | {d: .commit.committer.date, "
                 "m: .commit.message}]"],
                capture_output=True, text=True, timeout=60)
            try:
                commits = json.loads(r.stdout or "[]")
            except json.JSONDecodeError:
                commits = []
            for c in commits:
                if ver in c["m"]:
                    filas.append({
                        "sistema": "Alpine", "rama": rama, "paquete": pkg,
                        "version": ver, "fecha_utc": c["d"],
                        "aviso": c["m"].splitlines()[0][:80],
                        "fuente": "https://github.com/alpinelinux/aports/"
                                  f"commits/{rama}/community/{pkg}/APKBUILD",
                        "nota": "commit de aports",
                    })
                    break
    return filas


def _docker() -> list[dict]:
    filas = []
    for rama, ver in VERSIONES.items():
        for variante in ("apache", "fpm", "cli"):
            tag = f"{ver}-{variante}"
            d = leer_json(DOCKER_URL.format(tag=urllib.parse.quote(tag)))
            exactas = [t for t in d.get("results", []) if t["name"] == tag]
            if exactas:
                filas.append({
                    "sistema": "Docker (imagen oficial php)", "rama": rama,
                    "paquete": tag, "version": ver,
                    "fecha_utc": exactas[0]["tag_last_pushed"], "aviso": "",
                    "fuente": "https://hub.docker.com/_/php",
                    "nota": "tag_last_pushed de Docker Hub",
                })
            time.sleep(0.5)
    return filas


def etapa_sistemas() -> None:
    """Reúne las fechas de parche de cada sistema."""
    filas = []
    for cve in CVES[:1]:
        filas += _ubuntu(cve) + _redhat(cve) + _debian(cve)
    filas += _alpine() + _docker()
    for f in filas:
        f["horas_desde_parche"] = horas_desde_parche(f["fecha_utc"]) \
            if f["fecha_utc"] else ""
    escribir_csv("parches_sistemas.csv", filas,
                 ["sistema", "rama", "paquete", "version", "fecha_utc",
                  "horas_desde_parche", "aviso", "fuente", "nota"])


# --------------------------------------------------------------------
# 4. versiones de PHP en WordPress
# --------------------------------------------------------------------

def etapa_wordpress() -> None:
    """Cuota de cada versión de PHP entre los WordPress que informan."""
    d = leer_json(WP_URL)
    hoy = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    filas = []
    for ver, cuota in d.items():
        mayor = float(ver)
        if mayor >= 8.2:
            grupo = "con parche binario (8.2 a 8.5)"
        elif mayor >= 7.4:
            grupo = "solo parche de fuente (7.4, 8.0, 8.1)"
        else:
            grupo = "sin parche (anterior a 7.4)"
        filas.append({"fecha": hoy, "version": ver, "cuota_pct": cuota,
                      "grupo": grupo})
    filas.sort(key=lambda r: float(r["version"]))
    escribir_csv("wordpress_php.csv", filas,
                 ["fecha", "version", "cuota_pct", "grupo"])
    grupos = {}
    for r in filas:
        grupos[r["grupo"]] = round(grupos.get(r["grupo"], 0) + r["cuota_pct"], 3)
    (DIR / "resumen_wordpress.json").write_text(
        json.dumps({"fecha": hoy, "fuente": WP_URL, "grupos": grupos},
                   ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(grupos, ensure_ascii=False, indent=1))


# --------------------------------------------------------------------
# 5. la lista de productos afectados del NCSC de los Países Bajos
# --------------------------------------------------------------------

NCSC_RAW = ("https://raw.githubusercontent.com/NCSC-NL/php2shell/main/"
            "software/software_list_{letra}.md")
LETRAS = ["0-9"] + [chr(c) for c in range(ord("a"), ord("z") + 1)]


def etapa_ncsc() -> None:
    """Cuenta los productos de la lista del NCSC-NL por estado.

    La lista (TLP:CLEAR) tiene una fila por producto con el estado para
    cada CVE: Investigation, Vulnerable, Fix, Workaround o Not vuln.
    """
    filas = []
    for letra in LETRAS:
        req = urllib.request.Request(NCSC_RAW.format(letra=letra),
                                     headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                texto = r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError:
            continue
        for linea in texto.splitlines():
            if not linea.startswith("|") or linea.startswith("|:") \
                    or linea.startswith("| Supplier"):
                continue
            celdas = [c.strip() for c in linea.strip("|").split("|")]
            if len(celdas) < 5:
                continue
            filas.append({
                "letra": letra, "proveedor": celdas[0], "producto": celdas[1],
                "version": celdas[2][:120], "estado_109618": celdas[3],
                "estado_109619": celdas[4],
            })
        time.sleep(0.3)
    escribir_csv("ncsc_productos.csv", filas,
                 ["letra", "proveedor", "producto", "version",
                  "estado_109618", "estado_109619"])
    estados: dict[str, int] = {}
    for f in filas:
        estados[f["estado_109618"]] = estados.get(f["estado_109618"], 0) + 1
    res = {"fecha": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
           "productos": len(filas),
           "proveedores": len({f["proveedor"] for f in filas}),
           "estados_109618": estados}
    (DIR / "resumen_ncsc.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8")
    print(json.dumps(res, ensure_ascii=False, indent=1))


def main() -> None:
    """Punto de entrada."""
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--etapa", choices=["kev", "fichas", "sistemas",
                                        "wordpress", "ncsc", "todas"],
                    default="todas")
    args = ap.parse_args()
    etapas = (["kev", "fichas", "sistemas", "wordpress", "ncsc"]
              if args.etapa == "todas" else [args.etapa])
    for e in etapas:
        print(f"\n### etapa {e}")
        {"kev": etapa_kev, "fichas": etapa_fichas, "sistemas": etapa_sistemas,
         "wordpress": etapa_wordpress, "ncsc": etapa_ncsc}[e]()


if __name__ == "__main__":
    main()
