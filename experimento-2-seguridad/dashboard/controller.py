"""Control del contenedor verificador-autorizacion (para demostrar fail-closed).

Camino principal: Docker SDK sobre el docker.sock montado. Respaldo:
subprocess con comandos fijos (nunca entrada del usuario). Si ninguno
funciona, se devuelven las instrucciones manuales.
"""
import logging
import os
import subprocess
import time

logger = logging.getLogger("controller")

CONTAINER = "verificador-autorizacion"  # nombre fijo en docker-compose.yml
MANUAL = {"stop": f"docker stop {CONTAINER}", "start": f"docker start {CONTAINER}"}


def _cliente():
    import docker
    socket = os.environ.get("DOCKER_SOCKET", "/var/run/docker.sock")
    return docker.DockerClient(base_url="unix://" + socket)


_modo_cache = {"valor": None, "hasta": 0.0}


def detect_docker_mode():
    """Cacheado 15 s: la UI consulta /api/estado cada segundo."""
    if time.time() < _modo_cache["hasta"]:
        return _modo_cache["valor"]
    _modo_cache.update(valor=_detectar(), hasta=time.time() + 15)
    return _modo_cache["valor"]


def _detectar():
    try:
        _cliente().ping()
        return "sdk"
    except Exception:
        try:
            if subprocess.run(["docker", "info"], capture_output=True, timeout=10).returncode == 0:
                return "fallback"
        except Exception:
            pass
        return "manual"


def estado_contenedor():
    try:
        return "running" if _cliente().containers.get(CONTAINER).attrs["State"]["Running"] else "stopped"
    except Exception:
        return "unknown"


def controlar(accion):
    """accion: 'stop' | 'start'. Devuelve {ok, mode, manual?}."""
    try:
        contenedor = _cliente().containers.get(CONTAINER)
        contenedor.stop(timeout=3) if accion == "stop" else contenedor.start()
        return {"ok": True, "mode": "sdk"}
    except Exception as exc_sdk:
        logger.warning("SDK %s falló: %s; probando subprocess", accion, exc_sdk)
        try:
            r = subprocess.run(["docker", accion, CONTAINER], capture_output=True, text=True, timeout=60)
            if r.returncode == 0:
                return {"ok": True, "mode": "fallback"}
            logger.error("docker %s falló: %s", accion, r.stderr.strip())
        except Exception as exc_sub:
            logger.error("subprocess %s falló: %s", accion, exc_sub)
        return {"ok": False, "mode": "manual", "manual": MANUAL[accion]}
