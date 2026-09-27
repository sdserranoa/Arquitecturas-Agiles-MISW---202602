"""Fixtures compartidas: cada servicio con su SQLite temporal, sin Redis ni Docker."""
import os
import sys

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for sub in ("verificador-autorizacion", "ms-siniestros", "ms-alertas-auditoria", "experimento"):
    sys.path.insert(0, os.path.join(RAIZ, sub))

import alertas  # noqa: E402
import siniestros  # noqa: E402
import verificador  # noqa: E402
from alertas.consumidor import registrar_alerta  # noqa: E402
from verificador.alertas import publicador  # noqa: E402

SECRETO = "secreto-de-pruebas-con-longitud-suficiente-32"


def _vaciar_cola():
    while not publicador.cola.empty():
        publicador.cola.get_nowait()


@pytest.fixture()
def app_verificador(tmp_path):
    _vaciar_cola()
    app = verificador.create_app({
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'autorizacion.db'}",
        "JWT_SECRET": SECRETO,
        "TESTING": True,
    })
    yield app
    _vaciar_cola()


@pytest.fixture()
def app_siniestros(tmp_path):
    return siniestros.create_app({
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'siniestros.db'}",
        "JWT_SECRET": SECRETO,
        "HABILITAR_BASELINE": True,
        "TESTING": True,
    })


@pytest.fixture()
def app_alertas(tmp_path):
    return alertas.create_app({
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'alertas.db'}",
        "TESTING": True,
    })


@pytest.fixture()
def sistema(app_verificador, app_siniestros, app_alertas, monkeypatch):
    """Los tres componentes cableados en proceso: Siniestros -> Verificador por
    test client (en vez de HTTP) y la cola del publicador -> registrar_alerta
    (en vez de Redis). Devuelve (cliente_siniestros, drenar_alertas)."""
    from siniestros import cliente_verificador

    cli_verificador = app_verificador.test_client()

    def verificar_en_proceso(token, operacion, solicitud_id, recurso):
        r = cli_verificador.post("/verificar", json={"token": token, "operacion": operacion,
                                                      "solicitud_id": solicitud_id, "recurso": recurso})
        return r.get_json()

    monkeypatch.setattr(cliente_verificador, "verificar", verificar_en_proceso)

    def drenar_alertas():
        with app_alertas.app_context():
            while not publicador.cola.empty():
                registrar_alerta(publicador.cola.get_nowait())
        return app_alertas.test_client().get("/alertas").get_json()

    return app_siniestros.test_client(), drenar_alertas
