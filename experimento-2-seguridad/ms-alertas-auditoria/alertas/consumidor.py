"""Consumidor del bus de auditoría (Redis Stream alertas.intrusion)."""
import json
import os
import threading
import time

import redis
from sqlalchemy.exc import IntegrityError

from . import db, logger
from .models import AlertaIntrusion

STREAM = "alertas.intrusion"
REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))

estado = {"duplicados": 0}


def cliente_redis():
    return redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True, socket_timeout=5)


def registrar_alerta(alerta):
    """INSERT idempotente por alerta_id. Devuelve False si ya estaba registrada."""
    campos = {k: alerta.get(k) for k in ("alerta_id", "solicitud_id", "usuario", "rol_declarado",
                                          "rol_real", "operacion", "recurso", "motivo", "detectado_ts")}
    try:
        db.session.add(AlertaIntrusion(**campos, registrado_ts=time.time()))
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        estado["duplicados"] += 1
        return False
    logger.warning("ALERTA DE INTRUSIÓN registrada: %s usuario=%s (%s -> %s) operacion=%s solicitud=%s",
                   campos["motivo"], campos["usuario"], campos["rol_declarado"], campos["rol_real"],
                   campos["operacion"], campos["solicitud_id"])
    return True


class ConsumidorAlertas(threading.Thread):
    """XREAD bloqueante; reconexión con backoff 0.5 s -> 8 s. Al reiniciar el
    contenedor relee el stream desde 0 y la PK descarta lo ya registrado."""
    def __init__(self, app):
        super().__init__(daemon=True, name="consumidor-alertas")
        self.app = app
        self.ultimo_id = "0"

    def run(self):
        espera = 0.5
        r = None
        while True:
            try:
                r = r or cliente_redis()
                respuesta = r.xread({STREAM: self.ultimo_id}, count=100, block=1000)
                espera = 0.5
                for _stream, mensajes in respuesta or []:
                    for msg_id, campos in mensajes:
                        with self.app.app_context():
                            registrar_alerta(json.loads(campos["alerta"]))
                        self.ultimo_id = msg_id
            except redis.RedisError as exc:
                logger.warning("Bus de auditoría no disponible (%s); reintento en %.1fs", exc, espera)
                r = None
                time.sleep(espera)
                espera = min(espera * 2, 8)
