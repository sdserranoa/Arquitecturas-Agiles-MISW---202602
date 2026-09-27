"""API del dashboard: catálogo y validación de parámetros (sin servicios reales)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dashboard"))
import app as dashboard  # noqa: E402
from run_experimento import ATAQUES, LEGITIMAS  # noqa: E402


@pytest.fixture()
def cli():
    return dashboard.app.test_client()


def test_catalogo_describe_todos_los_escenarios(cli):
    datos = cli.get("/api/catalogo").get_json()
    assert {c["tipo"] for c in datos["ataques"]} == set(ATAQUES)
    assert {c["tipo"] for c in datos["legitimas"]} == set(LEGITIMAS)
    assert all(c["motivo_esperado"] != "OK" for c in datos["ataques"])
    assert all(c["motivo_esperado"] == "OK" for c in datos["legitimas"])


@pytest.mark.parametrize("cuerpo", [{"legitimas": 0}, {"ataques": "10"}, {"pausa_ms": 99999}])
def test_iniciar_valida_parametros(cli, cuerpo):
    assert cli.post("/api/experimento/iniciar", json=cuerpo).status_code == 400


def test_solicitud_escenario_desconocido(cli):
    assert cli.post("/api/solicitud", json={"escenario": "nope"}).status_code == 400


def test_verificador_accion_invalida(cli):
    assert cli.post("/api/verificador/reiniciar").status_code == 400


def test_eventos_incrementales(cli):
    item = {"tipo": "evasion_borde", "solicitud_id": "x-1", "status": 403, "ms": 3.2,
            "motivo": "PRIVILEGIO_INSUFICIENTE"}
    ev = dashboard.registrar_evento(item, "manual")
    assert ev["clase"] == "ataque"
    nuevos = cli.get(f"/api/eventos?desde={ev['seq'] - 1}").get_json()
    assert [e["seq"] for e in nuevos] == [ev["seq"]]
    assert cli.get(f"/api/eventos?desde={ev['seq']}").get_json() == []
