"""Verificación contextual: cada inconsistencia se detecta y emite alerta."""
import pytest

from conftest import SECRETO
from tokens import alterar_payload, emitir, sin_firma
from verificador.alertas import publicador


def _verificar(app, token, operacion="siniestro:aprobar", solicitud_id="s1"):
    r = app.test_client().post("/verificar", json={"token": token, "operacion": operacion,
                                                    "solicitud_id": solicitud_id, "recurso": "SIN-1"})
    assert r.status_code == 200
    return r.get_json()


def test_liquidador_legitimo_autorizado_sin_alerta(app_verificador):
    d = _verificar(app_verificador, emitir("luis.liquidador", "LiquidadorSiniestros", SECRETO))
    assert d["autorizado"] is True and d["intrusion"] is False and d["motivo"] == "OK"
    assert publicador.pendientes == 0


def test_atencion_puede_consultar(app_verificador):
    d = _verificar(app_verificador, emitir("ana.atencion", "AtencionCliente", SECRETO), "siniestro:consultar")
    assert d["autorizado"] is True
    assert publicador.pendientes == 0


@pytest.mark.parametrize("token, motivo", [
    (lambda: alterar_payload(emitir("ana.atencion", "AtencionCliente", SECRETO), rol="LiquidadorSiniestros"),
     "TOKEN_ALTERADO"),
    (lambda: emitir("ana.atencion", "LiquidadorSiniestros", "otra-clave-cualquiera-de-32-bytes!!"),
     "TOKEN_ALTERADO"),
    (lambda: sin_firma("ana.atencion", "LiquidadorSiniestros"), "TOKEN_ALTERADO"),
    (lambda: emitir("jorge.atencion", "LiquidadorSiniestros", SECRETO), "ROL_INCONSISTENTE"),
    (lambda: emitir("pedro.degradado", "LiquidadorSiniestros", SECRETO), "ROL_INCONSISTENTE"),
    (lambda: emitir("ana.atencion", "AtencionCliente", SECRETO), "PRIVILEGIO_INSUFICIENTE"),
    (lambda: emitir("mallory.externo", "LiquidadorSiniestros", SECRETO), "USUARIO_DESCONOCIDO"),
])
def test_ataques_detectados_y_alertados(app_verificador, token, motivo):
    d = _verificar(app_verificador, token(), solicitud_id="ataque-1")
    assert d["autorizado"] is False and d["intrusion"] is True and d["motivo"] == motivo
    assert publicador.pendientes == 1
    alerta = publicador.cola.get_nowait()
    assert alerta["solicitud_id"] == "ataque-1" and alerta["motivo"] == motivo
    assert alerta["alerta_id"] == d["alerta_id"]


def test_token_expirado_se_niega_sin_alerta(app_verificador):
    d = _verificar(app_verificador, emitir("luis.liquidador", "LiquidadorSiniestros", SECRETO, minutos=-1))
    assert d["autorizado"] is False and d["intrusion"] is False and d["motivo"] == "TOKEN_EXPIRADO"
    assert publicador.pendientes == 0


def test_revocar_rol_invalida_tokens_ya_emitidos(app_verificador):
    """Inmutabilidad: un token válido deja de servir apenas cambia la fuente de verdad."""
    token = emitir("carla.liquidadora", "LiquidadorSiniestros", SECRETO)
    assert _verificar(app_verificador, token)["autorizado"] is True

    r = app_verificador.test_client().put("/usuarios/carla.liquidadora", json={"rol": "AtencionCliente"})
    assert r.status_code == 200

    d = _verificar(app_verificador, token)
    assert d["motivo"] == "ROL_INCONSISTENTE" and d["rol_real"] == "AtencionCliente"


def test_reset_restablece_roles_semilla(app_verificador):
    cli = app_verificador.test_client()
    cli.put("/usuarios/luis.liquidador", json={"activo": False})
    cli.post("/reset")
    usuarios = {u["usuario"]: u for u in cli.get("/usuarios").get_json()}
    assert usuarios["luis.liquidador"]["activo"] is True


def test_faltan_campos(app_verificador):
    assert app_verificador.test_client().post("/verificar", json={}).status_code == 400
