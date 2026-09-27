"""Táctica: notificación de intrusión (asíncrona) hacia el bus de auditoría.

La petición HTTP solo encola la alerta; un hilo aparte hace XADD al Redis
Stream con reintentos, así la latencia de Redis no se suma a la verificación
y una caída momentánea del bus no pierde alertas.
"""
import json
import os
import queue
import threading
import time
import uuid

import redis

from . import logger

STREAM = "alertas.intrusion"
REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))


class PublicadorAlertas(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True, name="publicador-alertas")
        self.cola = queue.Queue()
        self.publicadas = 0
        self._redis = None

    def emitir(self, datos):
        alerta = {**datos, "alerta_id": str(uuid.uuid4()), "detectado_ts": time.time()}
        self.cola.put(alerta)
        logger.warning("Intrusión detectada: %s usuario=%s rol_declarado=%s rol_real=%s solicitud=%s",
                       alerta.get("motivo"), alerta.get("usuario"), alerta.get("rol_declarado"),
                       alerta.get("rol_real"), alerta.get("solicitud_id"))
        return alerta["alerta_id"]

    @property
    def pendientes(self):
        return self.cola.qsize()

    def _cliente(self):
        if self._redis is None:
            self._redis = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, socket_timeout=2)
        return self._redis

    def run(self):
        espera = 0.5
        while True:
            alerta = self.cola.get()
            while True:
                try:
                    self._cliente().xadd(STREAM, {"alerta": json.dumps(alerta)})
                    self.publicadas += 1
                    espera = 0.5
                    break
                except redis.RedisError as exc:
                    logger.warning("No se pudo publicar la alerta (%s); reintento en %.1fs", exc, espera)
                    self._redis = None
                    time.sleep(espera)
                    espera = min(espera * 2, 8)


publicador = PublicadorAlertas()
