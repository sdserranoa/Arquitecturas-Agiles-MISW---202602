"""El experimento completo con los tres componentes en proceso (sin Docker):
mismos escenarios que run_experimento.py, auditados por solicitud_id."""
from conftest import SECRETO
from run_experimento import APROBAR, ATAQUES, LEGITIMAS, construir_plan


def _enviar(cli, item):
    cab = {"Authorization": f"Bearer {item['token']}", "X-Solicitud-Id": item["solicitud_id"]}
    url = f"/siniestros/{item['siniestro_id']}"
    if item["accion"] == APROBAR:
        return cli.post(url + "/aprobacion", headers=cab).status_code
    return cli.get(url, headers=cab).status_code


def test_deteccion_100_falsos_positivos_0_integridad(sistema):
    cli, drenar_alertas = sistema
    plan = construir_plan(n_legitimas=40, n_ataques=49, secreto=SECRETO, semilla=7)
    for item in plan:
        item["status"] = _enviar(cli, item)

    alertas = drenar_alertas()
    alertadas = {a["solicitud_id"] for a in alertas["alertas"]}
    aprobadas = set(cli.get("/aprobaciones").get_json()["solicitud_ids"])
    ataques = [i for i in plan if i["clase"] == "ataque"]
    legitimas = [i for i in plan if i["clase"] == "legitima"]

    no_detectados = [i["solicitud_id"] for i in ataques if i["solicitud_id"] not in alertadas]
    assert no_detectados == []                                               # detección 100 %
    assert all(i["status"] == 403 for i in ataques)                          # bloqueados
    assert not aprobadas & {i["solicitud_id"] for i in ataques}              # integridad
    assert not alertadas & {i["solicitud_id"] for i in legitimas}            # 0 falsos positivos
    assert all(200 <= i["status"] < 300 for i in legitimas)
    assert alertas["total"] == len(ataques)                                  # 1 alerta por ataque
    assert {i["tipo"] for i in ataques} == set(ATAQUES)
    assert {i["tipo"] for i in legitimas} == set(LEGITIMAS)
