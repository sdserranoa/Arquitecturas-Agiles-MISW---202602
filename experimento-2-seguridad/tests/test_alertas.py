"""Registro idempotente de alertas en el módulo de auditoría."""
import time

from alertas import consumidor
from alertas.consumidor import registrar_alerta


def _alerta(alerta_id="a1", motivo="ROL_INCONSISTENTE"):
    return {"alerta_id": alerta_id, "solicitud_id": "s-" + alerta_id, "usuario": "ana.atencion",
            "rol_declarado": "LiquidadorSiniestros", "rol_real": "AtencionCliente",
            "operacion": "siniestro:aprobar", "recurso": "SIN-1", "motivo": motivo,
            "detectado_ts": time.time()}


def test_registra_y_expone(app_alertas):
    with app_alertas.app_context():
        assert registrar_alerta(_alerta("a1")) is True
        assert registrar_alerta(_alerta("a2", "TOKEN_ALTERADO")) is True
    datos = app_alertas.test_client().get("/alertas").get_json()
    assert datos["total"] == 2
    assert datos["por_motivo"] == {"ROL_INCONSISTENTE": 1, "TOKEN_ALTERADO": 1}
    assert datos["latencia_registro_ms"]["p95"] is not None


def test_reentrega_no_duplica(app_alertas):
    consumidor.estado["duplicados"] = 0
    with app_alertas.app_context():
        registrar_alerta(_alerta("a1"))
        assert registrar_alerta(_alerta("a1")) is False
    datos = app_alertas.test_client().get("/alertas").get_json()
    assert datos["total"] == 1 and datos["duplicados"] == 1


def test_reset_borra(app_alertas, monkeypatch):
    monkeypatch.setattr("alertas.vistas.cliente_redis", lambda: type("R", (), {"delete": lambda *a: 0})())
    with app_alertas.app_context():
        registrar_alerta(_alerta("a1"))
    cli = app_alertas.test_client()
    assert cli.post("/reset").get_json()["borradas"] == 1
    assert cli.get("/alertas").get_json()["total"] == 0
