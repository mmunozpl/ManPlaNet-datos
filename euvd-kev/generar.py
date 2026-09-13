#!/usr/bin/env python3
"""Las dos listas de vulnerabilidades explotadas, a cada lado del Atlántico.

Descarga el catálogo KEV de CISA y el conjunto de vulnerabilidades marcadas
como explotadas en la base de datos europea de vulnerabilidades (EUVD) de
ENISA, con la fuente que la EUVD declara para cada marca —el KEV de CISA, el
«EU KEV» propio de ENISA o las dos— y las observaciones de honeypot que la
misma API sirve. Cuenta la intersección, las entradas que solo tiene una de
las dos listas, la diferencia de fechas entre ambas cuando comparten entrada,
y las ventanas de plazo del KEV por año y la antigüedad del CVE al entrar.

Solo agregados y las entradas del EU KEV, que son pocas y públicas: no se
redistribuye ninguno de los dos catálogos. Se guarda en csv y se escribe la
ficha de procedencia al lado.
"""
import csv
import datetime
import json
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median

DESTINO = Path(__file__).resolve().parent   # escribe junto a sí mismo
UA = "Mozilla/5.0 (X11; Linux x86_64) Firefox/128.0"
KEV = ("https://www.cisa.gov/sites/default/files/feeds/"
       "known_exploited_vulnerabilities.json")
EUVD = "https://euvdservices.enisa.europa.eu/api"
LOTE = 40                     # ids por petición a los endpoints batch
BOD_26_04 = datetime.date(2026, 6, 10)   # directiva que fijó los plazos nuevos
TRAMOS = ("3 días", "4-7 días", "14 días", "21 días", "6 meses", "otros")


def descarga(url: str) -> dict | list:
    """descarga json con cabecera de navegador; cisa.gov rechaza a curl."""
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.load(r)


def fecha(s: str) -> datetime.date:
    """las fechas de la EUVD vienen como 'Sep 5, 2026, 12:00:00 AM'."""
    if "T" in s or s[:4].isdigit():
        return datetime.date.fromisoformat(s[:10])
    return datetime.datetime.strptime(",".join(s.split(",")[:2]),
                                      "%b %d, %Y").date()


def explotadas_euvd() -> list[dict]:
    """todas las páginas de la búsqueda con exploited=true."""
    items, pagina = [], 0
    while True:
        d = descarga(f"{EUVD}/search?exploited=true&page={pagina}&size=100")
        items += d["items"]
        if not d["items"] or len(items) >= d["total"]:
            return items
        pagina += 1


def por_lotes(endpoint: str, ids: list[str]) -> dict:
    """endpoints batch de la EUVD: kevEntries y honeypotObservations."""
    out = {}
    for i in range(0, len(ids), LOTE):
        lote = ",".join(ids[i:i + LOTE])
        d = descarga(f"{EUVD}/{endpoint}/batch?ids={lote}")
        out.update({k: v for k, v in d.items() if v})
    return out


def tramo(dias: int) -> str:
    """ventana entre el alta y la fecha límite, en los tramos del KEV."""
    if dias <= 3:
        return "3 días"
    if dias <= 7:
        return "4-7 días"
    if dias <= 14:
        return "14 días"
    if dias <= 21:
        return "21 días"
    if dias >= 170:
        return "6 meses"
    return "otros"


def escribe_csv(nombre: str, filas: list[dict]) -> None:
    with (DESTINO / nombre).open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(filas[0]))
        w.writeheader()
        w.writerows(filas)


def main() -> None:
    hoy = datetime.date.today().isoformat()
    kev = descarga(KEV)
    K = {v["cveID"]: v for v in kev["vulnerabilities"]}
    print(f"[kev] versión {kev['catalogVersion']} · {len(K)} entradas")
    E = explotadas_euvd()
    ids = [e["id"] for e in E]
    print(f"[euvd] explotadas: {len(E)}")
    fuentes = por_lotes("kevEntries", ids)
    honeypot = por_lotes("honeypotObservations", ids)
    print(f"[euvd] con fuente de explotación: {len(fuentes)} · "
          f"con honeypot: {len(honeypot)}")

    # --- fuentes de la marca de explotación en la EUVD
    combos = Counter()
    eukev = []
    cves_euvd = set()
    for e in E:
        lst = fuentes.get(e["id"], [])
        codigos = tuple(sorted({x["kevSource"]["code"] for x in lst}))
        combos[codigos] += 1
        for x in lst:
            cves_euvd.add(x["cveId"])
        eu = [x for x in lst if x["kevSource"]["code"] != "CISA"]
        if eu:
            cve = eu[0]["cveId"]
            f_eu = fecha(eu[0]["dateAdded"])
            f_cisa = fecha(K[cve]["dateAdded"]) if cve in K else None
            eukev.append({
                "cve": cve, "euvd": e["id"], "alta_eu_kev": f_eu.isoformat(),
                "alta_cisa_kev": f_cisa.isoformat() if f_cisa else "",
                "eu_menos_cisa_dias": (f_eu - f_cisa).days if f_cisa else "",
                "asignador": e.get("assigner", ""),
                "proveedor": ((e.get("enisaIdVendor") or [{}])[0]
                              .get("vendor", {}).get("name", "")),
                "honeypot": "sí" if e["id"] in honeypot else "no"})
    eukev.sort(key=lambda f: f["alta_eu_kev"])
    escribe_csv("eu-kev.csv", eukev)
    dif = [f["eu_menos_cisa_dias"] for f in eukev
           if f["eu_menos_cisa_dias"] != ""]

    # --- intersección con el JSON del KEV
    solo_euvd = sorted(cves_euvd - set(K))
    solo_kev = sorted(set(K) - cves_euvd)
    mismo_dia = 0
    for e in E:
        for x in fuentes.get(e["id"], []):
            if x["kevSource"]["code"] == "CISA" and x["cveId"] in K:
                if fecha(x["dateAdded"]) == fecha(K[x["cveId"]]["dateAdded"]):
                    mismo_dia += 1

    # --- KEV: ventanas por año y antigüedad al entrar
    ventanas = defaultdict(Counter)
    antiguedad = Counter()
    desde_bod = Counter()
    for v in K.values():
        alta = fecha(v["dateAdded"])
        dias = (fecha(v["dueDate"]) - alta).days
        ventanas[alta.year][tramo(dias)] += 1
        antiguedad[min(alta.year - int(v["cveID"].split("-")[1]), 10)] += 1
        if alta >= BOD_26_04:
            desde_bod[(dias, v.get("forensicTriage", ""))] += 1
    escribe_csv("ventanas-kev.csv", [
        {"anio": y, **{t: ventanas[y].get(t, 0) for t in TRAMOS}}
        for y in sorted(ventanas)])
    escribe_csv("antiguedad-kev.csv", [
        {"anios_desde_el_cve": a, "entradas": antiguedad[a]}
        for a in sorted(antiguedad)])

    # --- altas por mes en las dos listas, desde 2025
    mes_kev = Counter(fecha(v["dateAdded"]).strftime("%Y-%m")
                      for v in K.values()
                      if fecha(v["dateAdded"]).year >= 2025)
    mes_eu = Counter(f["alta_eu_kev"][:7] for f in eukev)
    meses = sorted(set(mes_kev) | set(mes_eu))
    escribe_csv("altas-mensuales.csv", [
        {"mes": m, "cisa_kev": mes_kev.get(m, 0), "eu_kev": mes_eu.get(m, 0)}
        for m in meses])

    resumen = {
        "extraido": hoy,
        "kev_version": kev["catalogVersion"],
        "kev_publicado": kev["dateReleased"],
        "kev_entradas": len(K),
        "kev_primera_alta": min(v["dateAdded"] for v in K.values())[:10],
        "kev_ultima_alta": max(v["dateAdded"] for v in K.values())[:10],
        "kev_triaje_forense": sum(1 for v in K.values()
                                  if v.get("forensicTriage") == "Yes"),
        "kev_desde_bod_26_04": {f"{d} días · triaje {t}": n for (d, t), n
                                in sorted(desde_bod.items())},
        "euvd_explotadas": len(E),
        "euvd_fuentes": {" + ".join(c) if c else "sin fuente": n
                         for c, n in combos.most_common()},
        "eu_kev_entradas": len(eukev),
        "eu_kev_primera_alta": eukev[0]["alta_eu_kev"] if eukev else "",
        "eu_kev_solo": sum(1 for f in eukev if not f["alta_cisa_kev"]),
        "eu_kev_compartidas": len(dif),
        "eu_antes_que_cisa": sum(1 for x in dif if x < 0),
        "mismo_dia_eu_cisa": sum(1 for x in dif if x == 0),
        "eu_despues_que_cisa": sum(1 for x in dif if x > 0),
        "mediana_eu_menos_cisa_dias": median(dif) if dif else None,
        "solo_euvd_cves": solo_euvd,
        "solo_kev_cves": solo_kev,
        "cisa_en_euvd_mismo_dia_que_kev": mismo_dia,
        "honeypot_entradas": len(honeypot),
        "honeypot_fuentes": dict(Counter(
            o["source"] for lst in honeypot.values() for o in lst)),
    }
    (DESTINO / "resumen.json").write_text(
        json.dumps(resumen, ensure_ascii=False, indent=1), encoding="utf-8")
    for k, v in resumen.items():
        print(f"[resumen] {k}: {v}")

    (DESTINO / "INSTANTANEA.md").write_text(f"""\
# Las dos listas de vulnerabilidades explotadas

Recuento comparado del catálogo KEV de CISA y de las vulnerabilidades que la
EUVD de ENISA marca como explotadas, con la fuente de cada marca. No se
redistribuye ninguno de los dos catálogos: `eu-kev.csv` lleva solo las
entradas que la EUVD atribuye a su lista propia, el «EU KEV», y el resto son
agregados. No interviene ningún dato de ninguna persona.

- KEV: {KEV} — versión `{kev['catalogVersion']}`, publicada
  {kev['dateReleased']}, {len(K)} entradas
- EUVD: `{EUVD}/search?exploited=true`, más `kevEntries/batch` y
  `honeypotObservations/batch` — {len(E)} entradas explotadas
- Extraído: {hoy}

## Ficheros

| Fichero | Contenido |
|---|---|
| `resumen.json` | recuentos: entradas, fuentes de la marca, intersección, fechas, honeypot |
| `eu-kev.csv` | una fila por entrada del EU KEV: CVE, id EUVD, fecha de alta en el EU KEV y en el KEV de CISA, diferencia en días, asignador del CVE, proveedor, si tiene observación de honeypot |
| `ventanas-kev.csv` | entradas del KEV por año de alta y ventana entre el alta y la fecha límite |
| `antiguedad-kev.csv` | entradas del KEV por años entre el año del CVE y el del alta (10 = diez o más) |
| `altas-mensuales.csv` | altas por mes desde enero de 2025 en el KEV de CISA y en el EU KEV |

## Cómo se cuenta

La EUVD sirve, para cada entrada explotada, una lista de fuentes con código
`CISA` o `EUKEV` y la fecha de alta en cada una; la marca «explotada» de una
entrada puede venir de una fuente, de la otra o de las dos. La fecha del KEV
de CISA se toma del JSON de CISA, no de la copia de la EUVD, salvo para
comprobar que coinciden. Las ventanas del KEV son `dueDate` menos
`dateAdded`, en días naturales. La antigüedad al entrar es el año del alta
menos el año del identificador CVE, que es el de su asignación y no el del
descubrimiento.
""", encoding="utf-8")


if __name__ == "__main__":
    main()
