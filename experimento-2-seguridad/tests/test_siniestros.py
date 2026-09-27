"""MS-Siniestros aplica la decisión del verificador y falla cerrado."""
from conftest import SECRETO
from siniestros import cliente_verificador
from tokens import emitir


def _decision(autorizado, motivo="OK", usuario="luis.liquidador"):
    return {"autorizado": autorizado, "intrusion": not autorizado, "motivo": motivo, "usuario": usuario}


def _aprobar(cli, token="x", sid="s1"):
    return cli.post("/siniestros/SIN-1/aprobacion",
                    headers={"Authorization": f"Bearer {token}", "X-Solicitud-Id": sid})


def test_sin_token_401(app_siniestros):
    assert app_siniestros.test_client().post("/siniestros/SIN-1/aprobacion").status_code == 401


def test_autorizado_aprueba_y_audita(app_siniestros, monkeypatch):
    monkeypatch.setattr(cliente_verificador, "verificar", lambda *a: _decision(True))
    cli = app_siniestros.test_client()
    r = _aprobar(cli, sid="legit-1")
    assert r.status_code == 201 and r.get_json()["aprobado_por"] == "luis.liquidador"
    assert cli.get("/aprobaciones").get_json()["solicitud_ids"] == ["legit-1"]


def test_denegado_403_y_no_ejecuta(app_siniestros, monkeypatch):
    monkeypatch.setattr(cliente_verificador, "verificar",
                        lambda *a: _decision(False, "ROL_INCONSISTENTE", "ana.atencion"))
    cli = app_siniestros.test_client()
    r = _aprobar(cli, sid="ataque-1")
    assert r.status_code == 403 and r.get_json()["motivo"] == "ROL_INCONSISTENTE"
    assert cli.get("/aprobaciones").get_json()["total"] == 0


def test_verificador_caido_falla_cerrado(app_siniestros, monkeypatch):
    def caido(*a):
        raise cliente_verificador.VerificadorNoDisponible("connection refused")
    monkeypatch.setattr(cliente_verificador, "verificar", caido)
    cli = app_siniestros.test_client()
    assert _aprobar(cli).status_code == 503
    assert cli.get("/aprobaciones").get_json()["total"] == 0


def test_baseline_rbac_local_no_cuenta_en_auditoria(app_siniestros):
    cli = app_siniestros.test_client()
    token = emitir("luis.liquidador", "LiquidadorSiniestros", SECRETO)
    r = cli.post("/baseline/siniestros/SIN-9/aprobacion", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 201
    assert cli.get("/aprobaciones").get_json()["total"] == 0


def test_baseline_deshabilitado_404(app_siniestros):
    app_siniestros.config["HABILITAR_BASELINE"] = False
    assert app_siniestros.test_client().post("/baseline/siniestros/SIN-9/aprobacion").status_code == 404
