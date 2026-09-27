"""Dashboard del experimento 2: orquesta el experimento y agrega el estado REAL.

- GET  /                          -> UI
- GET  /api/estado                -> salud de los servicios + contadores reales
                                     (verificador /stats, alertas, aprobaciones)
- GET  /api/eventos?desde=seq     -> feed de solicitudes (experimento y manuales)
- GET  /api/alertas               -> alertas registradas por el módulo de auditoría
- GET  /api/catalogo              -> escenarios de ataque/legítimos con su descripción
- POST /api/solicitud {escenario} -> dispara UNA solicitud (ataque o legítima)
- GET|PUT /api/usuarios[/<u>]     -> fuente de verdad de roles (proxy al verificador)
- POST /api/verificador/stop|start-> apaga/prende el verificador real (fail-closed)
- POST /api/experimento/iniciar   -> corre run_experimento.ejecutar en un hilo
- GET  /api/experimento/estado    -> fase, progreso y reporte
- GET  /api/historial             -> reportes de corridas anteriores (en memoria)
- POST /api/reset                 -> deja los tres servicios en cero
"""
import itertools
import logging
import os
import sys
import threading
import time
from collections import deque
from datetime import datetime, timezone

import requests
from flask import Flask, jsonify, render_template, request

import controller

_aqui = os.path.dirname(os.path.abspath(__file__))
for _ruta in (os.path.join(_aqui, "experimento"), os.path.join(_aqui, "..", "experimento")):
    if os.path.isdir(_ruta):
        sys.path.insert(0, _ruta)
import run_experimento as rx  # noqa: E402

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dashboard")

app = Flask(__name__)

SINIESTROS_URL = os.environ.get("SINIESTROS_URL", "http://localhost:6001")
VERIFICADOR_URL = os.environ.get("VERIFICADOR_URL", "http://localhost:6002")
ALERTAS_URL = os.environ.get("ALERTAS_URL", "http://localhost:6003")
JWT_SECRET = os.environ.get("JWT_SECRET", rx.SECRETO_DEFECTO)

SERVICIOS = {"siniestros": SINIESTROS_URL, "verificador": VERIFICADOR_URL, "auditoria": ALERTAS_URL}


# ------------------------------------------------------------------ http aux
def _get(url, timeout=2, **params):
    try:
        r = requests.get(url, timeout=timeout, params=params)
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        logger.debug("GET %s falló: %s", url, exc)
        return None


def _ahora():
    return datetime.now(timezone.utc).isoformat()


# -------------------------------------------------------- feed de eventos
_seq = itertools.count(1)
_eventos = deque(maxlen=500)
_eventos_lock = threading.Lock()


def registrar_evento(item, origen):
    """Guarda una solicitud ya respondida para que la UI la anime."""
    clase = "ataque" if item["tipo"] in rx.ATAQUES else "legitima"
    evento = {
        "seq": next(_seq),
        "ts": time.time(),
        "origen": origen,
        "tipo": item["tipo"],
        "clase": clase,
        "solicitud_id": item["solicitud_id"],
        "status": item["status"],
        "ms": round(item["ms"], 2),
        "motivo": item.get("motivo"),
    }
    with _eventos_lock:
        _eventos.append(evento)
    return evento


@app.get("/api/eventos")
def eventos():
    desde = request.args.get("desde", default=0, type=int)
    with _eventos_lock:
        nuevos = [e for e in _eventos if e["seq"] > desde]
    return jsonify(nuevos[-200:])


# ------------------------------------------------------------- estado real
@app.get("/api/estado")
def estado():
    salud = {nombre: _get(f"{url}/health", timeout=1) is not None for nombre, url in SERVICIOS.items()}
    stats = _get(f"{VERIFICADOR_URL}/stats") if salud["verificador"] else None
    alertas = _get(f"{ALERTAS_URL}/alertas", limite=0) if salud["auditoria"] else None
    aprobaciones = _get(f"{SINIESTROS_URL}/aprobaciones") if salud["siniestros"] else None
    return jsonify({
        "salud": salud,
        "verificador": stats,
        "alertas": None if alertas is None else {k: alertas[k] for k in
                                                 ("total", "duplicados", "por_motivo", "latencia_registro_ms")},
        "aprobaciones": None if aprobaciones is None else {"total": aprobaciones["total"],
                                                           "por_usuario": aprobaciones["por_usuario"]},
        "contenedor_verificador": controller.estado_contenedor(),
        "docker_mode": controller.detect_docker_mode(),
        "manual": controller.MANUAL,
        "ts": _ahora(),
    })


@app.get("/api/alertas")
def alertas():
    datos = _get(f"{ALERTAS_URL}/alertas", timeout=3, limite=request.args.get("limite", 300, type=int))
    if datos is None:
        return jsonify({"ok": False, "error": "módulo de auditoría no disponible"}), 503
    return jsonify(datos)


@app.get("/api/catalogo")
def catalogo():
    def filas(catalogo):
        return [{"tipo": t, "accion": accion, "descripcion": rx.DESCRIPCIONES[t][0],
                 "motivo_esperado": rx.DESCRIPCIONES[t][1]} for t, (accion, _) in catalogo.items()]
    return jsonify({"ataques": filas(rx.ATAQUES), "legitimas": filas(rx.LEGITIMAS)})


# ------------------------------------------------------ solicitud manual
_manual_seq = itertools.count(1)


@app.post("/api/solicitud")
def solicitud():
    escenario = (request.get_json(silent=True) or {}).get("escenario")
    catalogo = {**rx.ATAQUES, **rx.LEGITIMAS}
    if escenario not in catalogo:
        return jsonify({"ok": False, "error": "escenario desconocido"}), 400
    accion, fabrica = catalogo[escenario]
    n = next(_manual_seq)
    item = {"tipo": escenario, "accion": accion, "token": fabrica(JWT_SECRET),
            "solicitud_id": f"manual-{n:04d}-{escenario}", "siniestro_id": f"MAN-{n}"}
    try:
        item["status"], item["ms"], cuerpo = rx.enviar(requests, SINIESTROS_URL, item)
    except requests.RequestException as exc:
        return jsonify({"ok": False, "error": f"ms-siniestros no responde: {exc}"}), 503
    item["motivo"] = cuerpo.get("motivo") or ("OK" if 200 <= item["status"] < 300 else None)
    evento = registrar_evento(item, "manual")
    return jsonify({"ok": True, **evento, "respuesta": cuerpo})


# ------------------------------------------------- fuente de verdad (roles)
@app.get("/api/usuarios")
def usuarios():
    datos = _get(f"{VERIFICADOR_URL}/usuarios")
    if datos is None:
        return jsonify({"ok": False, "error": "verificador no disponible"}), 503
    return jsonify(datos)


@app.put("/api/usuarios/<usuario>")
def usuario(usuario):
    try:
        r = requests.put(f"{VERIFICADOR_URL}/usuarios/{usuario}", json=request.get_json(silent=True) or {},
                         timeout=3)
        return jsonify(r.json()), r.status_code
    except requests.RequestException as exc:
        return jsonify({"ok": False, "error": str(exc)}), 503


# ------------------------------------------------ control del verificador
@app.post("/api/verificador/<accion>")
def verificador(accion):
    if accion not in ("stop", "start"):
        return jsonify({"ok": False, "error": "accion debe ser stop|start"}), 400
    resultado = controller.controlar(accion)
    return jsonify(resultado), 200 if resultado["ok"] else 503


# ------------------------------------------------------------ orquestador
class Corrida(threading.Thread):
    def __init__(self, params):
        super().__init__(daemon=True, name="corrida-experimento")
        self.params = params
        self.state = {"status": "running", "fase": "preparando", "hechas": 0, "total": 0,
                      "parcial": {"legitimas_ok": 0, "ataques_bloqueados": 0, "enviadas": 0},
                      "params": params, "started_at": _ahora(), "finished_at": None,
                      "error": None, "reporte": None}

    def _notificar(self, fase, hechas=None, total=None, item=None):
        self.state["fase"] = fase
        if total is not None:
            self.state["hechas"], self.state["total"] = hechas or 0, total
        if item is not None:
            registrar_evento(item, "experimento")
            p = self.state["parcial"]
            p["enviadas"] += 1
            if item["clase"] == "ataque" and item["status"] == 403:
                p["ataques_bloqueados"] += 1
            elif item["clase"] == "legitima" and 200 <= item["status"] < 300:
                p["legitimas_ok"] += 1

    def run(self):
        try:
            reporte = rx.ejecutar(SINIESTROS_URL, VERIFICADOR_URL, ALERTAS_URL,
                                  n_legitimas=self.params["legitimas"], n_ataques=self.params["ataques"],
                                  n_latencia=self.params["latencia"], secreto=JWT_SECRET,
                                  pausa_s=self.params["pausa_ms"] / 1000, notificar=self._notificar)
            reporte["descripciones"] = {t: {"descripcion": d, "motivo_esperado": m}
                                        for t, (d, m) in rx.DESCRIPCIONES.items()}
            self.state.update(status="done", fase="reporte", reporte=reporte)
            with _historial_lock:
                _historial.appendleft(reporte)
        except Exception as exc:
            logger.exception("la corrida falló")
            self.state.update(status="error", error=str(exc))
        finally:
            self.state["finished_at"] = _ahora()


_corrida = None
_corrida_lock = threading.Lock()
_historial = deque(maxlen=10)
_historial_lock = threading.Lock()

LIMITES = {"legitimas": (1, 2000), "ataques": (1, 2000), "latencia": (5, 1000), "pausa_ms": (0, 2000)}
DEFECTOS = {"legitimas": 60, "ataques": 70, "latencia": 100, "pausa_ms": 120}


@app.post("/api/experimento/iniciar")
def iniciar():
    global _corrida
    cuerpo = request.get_json(silent=True) or {}
    params = {}
    for campo, (minimo, maximo) in LIMITES.items():
        valor = cuerpo.get(campo, DEFECTOS[campo])
        if not isinstance(valor, int) or not minimo <= valor <= maximo:
            return jsonify({"ok": False, "error": f"{campo} debe ser entero {minimo}..{maximo}"}), 400
        params[campo] = valor
    with _corrida_lock:
        if _corrida is not None and _corrida.is_alive():
            return jsonify({"ok": False, "error": "ya hay un experimento en curso"}), 409
        _corrida = Corrida(params)
        _corrida.start()
    return jsonify({"ok": True, **params})


@app.get("/api/experimento/estado")
def estado_experimento():
    with _corrida_lock:
        corrida = _corrida
    return jsonify(dict(corrida.state) if corrida else {"status": "idle"})


@app.get("/api/historial")
def historial():
    with _historial_lock:
        return jsonify([{k: r[k] for k in ("fecha", "parametros", "deteccion_pct", "falsos_positivos_pct",
                                            "aprobaciones_indebidas", "hipotesis_confirmada")}
                        | {"sobrecosto_p95": r["latencia"]["sobrecosto_ms"]["p95"], "indice": i}
                        for i, r in enumerate(_historial)])


@app.get("/api/historial/<int:indice>")
def historial_detalle(indice):
    with _historial_lock:
        if not 0 <= indice < len(_historial):
            return jsonify({"ok": False, "error": "no existe"}), 404
        return jsonify(_historial[indice])


@app.post("/api/reset")
def reset():
    with _corrida_lock:
        if _corrida is not None and _corrida.is_alive():
            return jsonify({"ok": False, "error": "hay un experimento en curso"}), 409
    errores = []
    for nombre, url in SERVICIOS.items():
        try:
            requests.post(f"{url}/reset", timeout=5).raise_for_status()
        except requests.RequestException as exc:
            errores.append(f"{nombre}: {exc}")
    with _eventos_lock:
        _eventos.clear()
    if errores:
        return jsonify({"ok": False, "error": "; ".join(errores)}), 502
    return jsonify({"ok": True})


# --------------------------------------------------------------------- UI
@app.get("/")
def index():
    return render_template("index.html")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, threaded=True)
