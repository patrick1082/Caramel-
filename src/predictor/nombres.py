"""Empareja nombres de equipos entre fuentes ("Man United" ↔ "Manchester United")."""

from __future__ import annotations

import difflib
import logging
import re
import unicodedata
from collections.abc import Iterable

logger = logging.getLogger(__name__)

# Siglas y palabras de relleno que una fuente incluye y la otra no.
_RELLENO = {
    "fc", "afc", "cf", "sc", "ac", "as", "bc", "rc", "ca", "tsg", "vfb", "fsv", "sv", "club", "de",
}  # fmt: skip

# Abreviaturas por palabra.
_PALABRAS = {
    "man": "manchester",
    "nottm": "nottingham",
    "ein": "eintracht",
    "mgladbach": "monchengladbach",
    "hamburger": "hamburg",
    "ath": "athletic",
    "sg": "saint germain",
    "la": "los angeles",
}

# Nombres completos que no se resuelven palabra por palabra (ya normalizados).
_ALIAS = {
    "athletic madrid": "atletico madrid",
    "espanol": "espanyol",
    "inter milan": "inter",  # Si no, también contiene a "milan".
}


def clave(nombre: str) -> str:
    """Forma normalizada: sin tildes, minúsculas, sin siglas de club ni números sueltos."""
    texto = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode()
    texto = re.sub(r"[^a-z0-9 ]", "", texto.lower().replace("-", " ").replace(".", " "))
    palabras = []
    for palabra in texto.split():
        if palabra in _RELLENO or palabra.isdigit():
            continue
        palabras.extend(_PALABRAS.get(palabra, palabra).split())
    normal = " ".join(palabras)
    return _ALIAS.get(normal, normal)


def emparejar(nombre: str, candidatos: Iterable[str]) -> str | None:
    """Busca `nombre` entre `candidatos` (otra fuente); None si no hay un único candidato claro."""
    por_clave = {clave(c): c for c in candidatos}
    buscada = clave(nombre)
    if buscada in por_clave:
        return por_clave[buscada]

    palabras = set(buscada.split())
    contenidos = [
        c for k, c in por_clave.items() if palabras <= set(k.split()) or set(k.split()) <= palabras
    ]
    if len(contenidos) == 1:
        return contenidos[0]

    parecidos = difflib.get_close_matches(buscada, list(por_clave), n=1, cutoff=0.8)
    if parecidos:
        return por_clave[parecidos[0]]
    logger.warning("Sin equivalencia para el equipo '%s'", nombre)
    return None
