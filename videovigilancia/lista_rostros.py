"""pliegos que piden reconocimiento facial contra una lista o base de rostros.

Se lee el texto ya extraído de cada pliego con reconocimiento facial
afirmado (nivel B estricto) y se busca, a menos de 300 caracteres de la
mención, una lista de vigilancia, una base de rostros o «personas de
interés». Las listas de matrículas no cuentan: se descarta la coincidencia
si a menos de 80 caracteres aparece matrícula, ANPR o LPR.
"""
import re
import sys
import unicodedata
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent
FACIAL = re.compile(
    r"reconocimiento facial|reconeixement facial|face recognition|"
    r"facial recognition|reconocimiento de (rostros|caras)|"
    r"identificacion facial")
LISTA = re.compile(
    r"listas? de (seguimiento|vigilancia|busqueda)|"
    r"llistes? de (seguiment|vigilancia|persones)|watch ?lists?|"
    r"bases? de datos (de rostros|de caras|faciales)|"
    r"bases? de dades (de rostres|de cares|facials)|"
    r"face (database|library|libraries|pictures)|"
    r"bibliotecas? de (rostros|caras)|\d+ (bibliotecas|libraries)|"
    r"personas de interes|persones d.interes|individuos buscados")
MATRICULA = re.compile(r"matricul|anpr|\blpr\b|plate")
# líneas de ficha de producto: canales, grabador, resolución, códecs, discos
FICHA = re.compile(
    r"\d+\s?(canales|canals|canal|ch\b|-ch|channel)|\bnvr\b|\bdvr\b|"
    r"grabador|gravador|\bmpx\b|megapixel|h\.?26[45]|hdmi|\bsata\b|"
    r"\bpoe\b|\bhdd\b|\bvga\b|ultra265|deepinmind|wizmind")
ACCESO = re.compile(
    r"control (de )?acces|control d.acces|terminal|torno|fichaje|"
    r"asistencia|huella|\bcpd\b|mifare|videoportero")


def norm(texto: str) -> str:
    """minúsculas, sin acentos y con los espacios compactados."""
    t = unicodedata.normalize("NFKD", texto.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return " ".join(t.split())


def contra_lista(texto: str) -> str:
    """primera frase que une reconocimiento facial y lista, o cadena vacía."""
    for m in FACIAL.finditer(texto):
        ventana = texto[max(0, m.start() - 300):m.end() + 300]
        for ml in LISTA.finditer(ventana):
            cerca = ventana[max(0, ml.start() - 80):ml.end() + 80]
            if not MATRICULA.search(cerca):
                return ventana[max(0, ml.start() - 120):ml.end() + 120]
    return ""


def clase(texto: str) -> str:
    """dónde aparece el reconocimiento facial en un pliego.

    Args:
        texto: texto del pliego ya normalizado.

    Returns:
        «contra_lista» si alguna mención une rostro y lista; «solo_ficha» si
        todas están en líneas de ficha de producto; «solo_acceso» si todas
        están junto a control de accesos; «otro» en el resto.
    """
    if contra_lista(texto):
        return "contra_lista"
    ms = list(FACIAL.finditer(texto))
    cerca = [texto[max(0, m.start() - 150):m.end() + 150] for m in ms]
    if ms and all(ACCESO.search(c) and not FICHA.search(c) for c in cerca):
        return "solo_acceso"
    if ms and all(FICHA.search(c) for c in cerca):
        return "solo_ficha"
    return "otro"


def main() -> None:
    d = pd.read_csv(RAIZ / "salidas" / "licitaciones_videovigilancia.csv",
                    low_memory=False)
    fac = d[d["b_facial_estricto_afirm"].fillna(False).astype(bool)].copy()
    frases, clases = [], []
    for _, r in fac.iterrows():
        p = RAIZ / "pliegos" / str(r["pliego_txt"])
        texto = norm(p.read_text(encoding="utf-8", errors="ignore")) \
            if p.exists() else ""
        frases.append(contra_lista(texto))
        clases.append(clase(texto))
    fac["b_facial_contra_lista"] = [bool(f) for f in frases]
    fac["b_frase_contra_lista"] = frases
    fac["b_facial_clase"] = clases
    fac["anio"] = fac["fecha_publicacion"].astype(str).str[:4]
    print("facial estricto:", len(fac), "| contra lista:",
          int(fac["b_facial_contra_lista"].sum()))
    print(fac.groupby("anio")["b_facial_contra_lista"].agg(["sum", "count"]))
    print(fac.groupby("tipo_efectivo")["b_facial_contra_lista"].sum())
    print(pd.crosstab(fac["b_facial_clase"], fac["tipo_efectivo"] == "3"))
    # se repite la frase de catálogo: cuántos pliegos comparten texto
    rep = fac.loc[fac["b_facial_contra_lista"], "b_frase_contra_lista"] \
        .str[60:160].value_counts()
    print("frases repetidas:", rep[rep > 1].to_dict())
    fac[["clave", "tipo_efectivo", "anio", "b_facial_clase",
         "b_facial_contra_lista", "b_frase_contra_lista"]].to_csv(
        RAIZ / "salidas" / "facial_contra_lista.csv", index=False)


if __name__ == "__main__":
    sys.exit(main())
