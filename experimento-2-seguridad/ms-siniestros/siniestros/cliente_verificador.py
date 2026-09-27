"""Conector HTTP/REST síncrono hacia el Verificador Central de Autorización."""
import requests
from flask import current_app

# Sesión con keep-alive: evita pagar el handshake TCP en cada verificación.
_sesion = requests.Session()


class VerificadorNoDisponible(Exception):
    pass


def verificar(token, operacion, solicitud_id, recurso):
    cfg = current_app.config
    try:
        respuesta = _sesion.post(
            f"{cfg['VERIFICADOR_URL']}/verificar",
            json={"token": token, "operacion": operacion,
                  "solicitud_id": solicitud_id, "recurso": recurso},
            timeout=cfg["VERIFICADOR_TIMEOUT"],
        )
        respuesta.raise_for_status()
        return respuesta.json()
    except requests.RequestException as exc:
        raise VerificadorNoDisponible(str(exc)) from exc
