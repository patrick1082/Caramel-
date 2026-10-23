"""Respuestas HTTP falsas para probar los clientes sin red."""

from __future__ import annotations

import json
from pathlib import Path

DATOS = Path(__file__).parent / "datos"


class RespuestaFalsa:
    def __init__(self, cuerpo: bytes = b"", status_code: int = 200, headers: dict | None = None):
        self.content = cuerpo
        self.status_code = status_code
        self.headers = headers or {}

    def json(self):
        return json.loads(self.content)


class ObtenerFalso:
    """Reemplazo de `requests.get` que registra las llamadas y devuelve respuestas fijas."""

    def __init__(self, *respuestas: RespuestaFalsa | Exception):
        self.respuestas = list(respuestas)
        self.llamadas: list[tuple[str, dict]] = []

    def __call__(self, url: str, params: dict | None = None, timeout: float | None = None):
        self.llamadas.append((url, params or {}))
        respuesta = self.respuestas.pop(0) if len(self.respuestas) > 1 else self.respuestas[0]
        if isinstance(respuesta, Exception):
            raise respuesta
        return respuesta


def respuesta_odds(archivo: str, restantes: int = 494, usados: int = 6) -> RespuestaFalsa:
    return RespuestaFalsa(
        (DATOS / archivo).read_bytes(),
        headers={"x-requests-remaining": str(restantes), "x-requests-used": str(usados)},
    )
