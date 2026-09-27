from collections import Counter

import redis
from flask import request
from flask_restful import Resource

from . import db, logger
from .consumidor import STREAM, cliente_redis, estado
from .models import AlertaIntrusion


def _percentil(valores, p):
    if not valores:
        return None
    ordenados = sorted(valores)
    k = max(0, min(len(ordenados) - 1, round(p / 100 * len(ordenados) + 0.5) - 1))
    return round(ordenados[k], 2)


class VistaAlertas(Resource):
    """GET /alertas?limite=N: total, desglose por motivo, latencia detección->registro y alertas."""
    def get(self):
        limite = request.args.get("limite", default=1000, type=int)
        alertas = db.session.query(AlertaIntrusion).order_by(AlertaIntrusion.registrado_ts.desc()).all()
        latencias = [(a.registrado_ts - a.detectado_ts) * 1000 for a in alertas]
        return {
            "total": len(alertas),
            "duplicados": estado["duplicados"],
            "por_motivo": dict(Counter(a.motivo for a in alertas)),
            "latencia_registro_ms": {"p50": _percentil(latencias, 50),
                                     "p95": _percentil(latencias, 95),
                                     "max": round(max(latencias), 2) if latencias else None},
            "alertas": [a.to_dict() for a in alertas[:limite]],
        }, 200


class VistaReset(Resource):
    """Borra las alertas registradas y vacía el stream para empezar una corrida limpia."""
    def post(self):
        borradas = db.session.query(AlertaIntrusion).delete()
        db.session.commit()
        estado["duplicados"] = 0
        try:
            cliente_redis().delete(STREAM)
        except redis.RedisError as exc:
            logger.warning("No se pudo vaciar el stream: %s", exc)
        return {"borradas": borradas}, 200


class VistaHealth(Resource):
    def get(self):
        return {"status": "ok"}, 200
