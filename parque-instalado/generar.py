"""El parque instalado, medido por dos lados.

Uno: la edad del fallo cuando entra en el catálogo de vulnerabilidades
explotadas conocidas de CISA, contada como año de alta menos año del
identificador CVE, y qué proporción de las altas corresponde a dispositivos
de borde de red (cortafuegos, VPN, enrutadores), con una lista de proveedores
declarada abajo. Dos: la cuota mensual de cada versión de Windows en
escritorio, en el mundo y en España, tal como la publica StatCounter.

Escribe junto a sí mismo: `altas-edades.csv`, `edades-por-anio.csv`,
`windows-versiones.csv`, `resumen.json` e `INSTANTANEA.md`.
"""
import csv
import datetime as dt
import io
import json
import urllib.parse
import urllib.request
from pathlib import Path

AQUI = Path(__file__).resolve().parent
KEV = ("https://www.cisa.gov/sites/default/files/feeds/"
       "known_exploited_vulnerabilities.json")
STATCOUNTER = "https://gs.statcounter.com/windows-version-market-share/desktop/"
REGIONES = {"mundo": ("ww", "Worldwide", "worldwide"),
            "espana": ("ES", "Spain", "spain")}
ANIO_INICIAL = 2023
# proveedores de dispositivos de borde de red: cortafuegos, VPN, enrutadores
# y balanceadores, tal como figuran en el campo vendorProject del catálogo
BORDE = {"Cisco", "Fortinet", "Ivanti", "SonicWall", "Palo Alto Networks",
         "Citrix", "F5", "Zyxel", "D-Link", "NETGEAR", "MikroTik", "Juniper",
         "Draytek", "TP-Link", "Ubiquiti", "Check Point", "WatchGuard",
         "Barracuda", "Sophos", "Array Networks", "Cambium", "Sierra Wireless"}


def pide(url: str) -> bytes:
    r = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(r, timeout=120) as f:
        return f.read()


def edades() -> tuple[list[dict], list[dict], str]:
    """Lee el catálogo y devuelve una fila por alta y el agregado por año.

    Returns:
        (altas, por_anio, version_del_catalogo).
    """
    d = json.loads(pide(KEV))
    altas = []
    for v in d["vulnerabilities"]:
        anio_cve = int(v["cveID"].split("-")[1])
        anio_alta = int(v["dateAdded"][:4])
        if anio_alta < ANIO_INICIAL:
            continue
        altas.append({
            "cve": v["cveID"], "anio_cve": anio_cve, "anio_alta": anio_alta,
            "fecha_alta": v["dateAdded"], "edad": anio_alta - anio_cve,
            "proveedor": v["vendorProject"], "producto": v["product"],
            "borde_red": int(v["vendorProject"] in BORDE)})
    por_anio = []
    for a in sorted({x["anio_alta"] for x in altas}):
        f = [x for x in altas if x["anio_alta"] == a]
        e = [x["edad"] for x in f]
        viejo = min(f, key=lambda x: x["anio_cve"])
        por_anio.append({
            "anio_alta": a, "altas": len(f),
            "edad_0": sum(1 for x in e if x == 0),
            "edad_1_4": sum(1 for x in e if 1 <= x <= 4),
            "edad_5_9": sum(1 for x in e if 5 <= x <= 9),
            "edad_10_mas": sum(1 for x in e if x >= 10),
            "pct_5_mas": round(100 * sum(1 for x in e if x >= 5) / len(f), 1),
            "edad_mediana": sorted(e)[len(e) // 2],
            "borde_red": sum(x["borde_red"] for x in f),
            "pct_borde_red": round(100 * sum(x["borde_red"] for x in f)
                                   / len(f), 1),
            "mas_antiguo": viejo["cve"],
            "mas_antiguo_proveedor": viejo["proveedor"]})
    return altas, por_anio, d["catalogVersion"]


def windows(desde: str, hasta: str) -> list[dict]:
    """Descarga la serie mensual de versiones de Windows en escritorio.

    Args:
        desde: mes inicial, `AAAA-MM`.
        hasta: mes final, `AAAA-MM`.

    Returns:
        filas con region, mes y cuota de cada versión.
    """
    filas = []
    for region, (cod, nombre, ruta) in REGIONES.items():
        q = urllib.parse.urlencode({
            "device": "Desktop", "device_hidden": "desktop",
            "statType_hidden": "windows_version", "region_hidden": cod,
            "granularity": "monthly", "statType": "Windows Version",
            "region": nombre, "fromInt": desde.replace("-", ""),
            "toInt": hasta.replace("-", ""), "fromMonthYear": desde,
            "toMonthYear": hasta, "csv": "1"})
        texto = pide(f"{STATCOUNTER}{ruta}/chart.php?{q}").decode("utf-8")
        for r in csv.DictReader(io.StringIO(texto)):
            filas.append({"region": region, "mes": r["Date"],
                          "win11": r.get("Win11", ""), "win10": r.get("Win10", ""),
                          "win7": r.get("Win7", ""), "winxp": r.get("WinXP", ""),
                          "win8": r.get("Win8", ""), "win81": r.get("Win8.1", ""),
                          "otros": r.get("Other", "")})
    return filas


def escribe_csv(ruta: Path, filas: list[dict]) -> None:
    with open(ruta, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0]))
        w.writeheader()
        w.writerows(filas)


def instantanea(hoy: str, version: str, por_anio: list[dict],
                win: list[dict]) -> str:
    lineas = [
        "# Instantánea — el parque instalado", "",
        f"- Extracción: {hoy}.",
        f"- Catálogo de explotadas de CISA, versión {version} (`{KEV}`). La edad"
        " es el año de alta menos el año del identificador CVE; es una cota"
        " inferior de la edad del fallo, porque el identificador se reserva"
        " en el año de asignación.",
        "- Dispositivos de borde de red: los proveedores de la lista `BORDE`"
        " de `generar.py`, declarada y ampliable.",
        "- Versiones de Windows en escritorio: StatCounter Global Stats"
        f" (`{STATCOUNTER}`), serie mensual descargada en CSV para el mundo y"
        " para España. Es una estimación por tráfico web, no un censo.",
        "", "| año de alta | altas | 0 años | 1-4 | 5-9 | ≥10 | ≥5 años | "
        "borde de red | más antiguo |", "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in por_anio:
        lineas.append(f"| {r['anio_alta']} | {r['altas']} | {r['edad_0']} | "
                      f"{r['edad_1_4']} | {r['edad_5_9']} | {r['edad_10_mas']}"
                      f" | {r['pct_5_mas']} % | {r['borde_red']} "
                      f"({r['pct_borde_red']} %) | {r['mas_antiguo']} "
                      f"({r['mas_antiguo_proveedor']}) |")
    ult = [w for w in win if w["mes"] == max(x["mes"] for x in win)]
    lineas += ["", f"Windows en escritorio, último mes de la serie:", ""]
    lineas += [f"- {w['region']}, {w['mes']}: Windows 11 {w['win11']} %, "
               f"Windows 10 {w['win10']} %, Windows 7 {w['win7']} %"
               for w in ult]
    lineas += ["", "No interviene ningún dato de ninguna persona."]
    return "\n".join(lineas) + "\n"


def main() -> None:
    hoy = dt.date.today()
    altas, por_anio, version = edades()
    hasta = (hoy.replace(day=1) - dt.timedelta(days=1)).strftime("%Y-%m")
    desde = f"{hoy.year - 1}-{hoy.month:02d}"
    win = windows(desde, hasta)
    escribe_csv(AQUI / "altas-edades.csv", altas)
    escribe_csv(AQUI / "edades-por-anio.csv", por_anio)
    escribe_csv(AQUI / "windows-versiones.csv", win)
    (AQUI / "resumen.json").write_text(json.dumps({
        "extraccion": hoy.isoformat(), "kev_version": version,
        "por_anio": por_anio, "windows_ultimo_mes": [
            w for w in win if w["mes"] == max(x["mes"] for x in win)]},
        ensure_ascii=False, indent=1), encoding="utf-8")
    (AQUI / "INSTANTANEA.md").write_text(
        instantanea(hoy.strftime("%d-%m-%Y"), version, por_anio, win),
        encoding="utf-8")
    print("hecho:", len(altas), "altas ·", len(win), "meses de Windows")


if __name__ == "__main__":
    main()
