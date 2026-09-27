"""Experimento 2 — Detección de elevación de privilegios (ASR-SEG-09).

Envía a MS-Siniestros una mezcla aleatoria (semilla fija) de solicitudes
legítimas y de ataques donde la vulnerabilidad se asume materializada, y
audita por solicitud_id qué detectó el componente de seguridad:

  * Detección      = ataques con alerta registrada / ataques      (meta 100 %)
  * Falsos positivos = legítimas con alerta o rechazadas / legítimas (meta 0 %)
  * Integridad     = aprobaciones ejecutadas por solicitudes de ataque (meta 0)
  * Sobrecosto     = latencia con verificador central - latencia RBAC local (meta < 50 ms)

Uso:
    python experimento/run_experimento.py --legitimas 60 --ataques 70 --latencia 100
"""
import argparse
import json
import os
import random
import sys
import time
from collections import defaultdict
from datetime import datetime

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tokens import alterar_payload, emitir, sin_firma  # noqa: E402

SECRETO_DEFECTO = "solventa-secreto-dev-no-usar-en-produccion"
CLAVE_ATACANTE = "clave-del-atacante-que-no-es-la-del-borde"

APROBAR, CONSULTAR = "aprobar", "consultar"

# tipo -> (acción, fábrica de token). La vulnerabilidad se asume materializada:
# todos estos tokens llegaron al core pese a la autorización de borde.
ATAQUES = {
    "firma_alterada":   (APROBAR, lambda s: alterar_payload(emitir("ana.atencion", "AtencionCliente", s),
                                                            rol="LiquidadorSiniestros")),
    "firma_otra_clave": (APROBAR, lambda s: emitir("ana.atencion", "LiquidadorSiniestros", CLAVE_ATACANTE)),
    "alg_none":         (APROBAR, lambda s: sin_firma("ana.atencion", "LiquidadorSiniestros")),
    "rol_inyectado":    (APROBAR, lambda s: emitir("jorge.atencion", "LiquidadorSiniestros", s)),
    "evasion_borde":    (APROBAR, lambda s: emitir("ana.atencion", "AtencionCliente", s)),
    "rol_revocado":     (APROBAR, lambda s: emitir("pedro.degradado", "LiquidadorSiniestros", s)),
    "usuario_fantasma": (APROBAR, lambda s: emitir("mallory.externo", "LiquidadorSiniestros", s)),
}

LEGITIMAS = {
    "liquidador_aprueba":  (APROBAR, lambda s: emitir("luis.liquidador", "LiquidadorSiniestros", s)),
    "liquidadora_aprueba": (APROBAR, lambda s: emitir("carla.liquidadora", "LiquidadorSiniestros", s)),
    "atencion_consulta":   (CONSULTAR, lambda s: emitir("ana.atencion", "AtencionCliente", s)),
    "degradado_consulta":  (CONSULTAR, lambda s: emitir("pedro.degradado", "AtencionCliente", s)),
}

# tipo -> (descripción corta, motivo que debe reportar el verificador)
DESCRIPCIONES = {
    "firma_alterada":      ("Token de ana con el rol editado a Liquidador, firma original", "TOKEN_ALTERADO"),
    "firma_otra_clave":    ("Token firmado con una clave distinta a la del borde", "TOKEN_ALTERADO"),
    "alg_none":            ("Token sin firma (alg=none)", "TOKEN_ALTERADO"),
    "rol_inyectado":       ("Token bien firmado de jorge que declara Liquidador", "ROL_INCONSISTENTE"),
    "evasion_borde":       ("Atención al cliente llama directo a la aprobación", "PRIVILEGIO_INSUFICIENTE"),
    "rol_revocado":        ("Token viejo de pedro que aún declara Liquidador", "ROL_INCONSISTENTE"),
    "usuario_fantasma":    ("Token firmado para un usuario que no existe", "USUARIO_DESCONOCIDO"),
    "liquidador_aprueba":  ("luis.liquidador aprueba un siniestro", "OK"),
    "liquidadora_aprueba": ("carla.liquidadora aprueba un siniestro", "OK"),
    "atencion_consulta":   ("ana.atencion consulta un siniestro", "OK"),
    "degradado_consulta":  ("pedro.degradado consulta con su rol actual", "OK"),
}


def percentil(valores, p):
    if not valores:
        return None
    ordenados = sorted(valores)
    k = max(0, min(len(ordenados) - 1, round(p / 100 * len(ordenados) + 0.5) - 1))
    return round(ordenados[k], 2)


def construir_plan(n_legitimas, n_ataques, secreto, semilla):
    plan = []
    for clase, catalogo, n in (("ataque", ATAQUES, n_ataques), ("legitima", LEGITIMAS, n_legitimas)):
        tipos = list(catalogo)
        for i in range(n):
            tipo = tipos[i % len(tipos)]
            accion, fabrica = catalogo[tipo]
            plan.append({"clase": clase, "tipo": tipo, "accion": accion, "token": fabrica(secreto)})
    random.Random(semilla).shuffle(plan)
    for i, item in enumerate(plan):
        item["solicitud_id"] = f"{i:04d}-{item['clase']}-{item['tipo']}"
        item["siniestro_id"] = f"SIN-{1000 + i}"
    return plan


def enviar(sesion, base, item, prefijo=""):
    url = f"{base}{prefijo}/siniestros/{item['siniestro_id']}"
    cabeceras = {"Authorization": f"Bearer {item['token']}", "X-Solicitud-Id": item["solicitud_id"]}
    t0 = time.perf_counter()
    if item["accion"] == APROBAR:
        r = sesion.post(url + "/aprobacion", headers=cabeceras, timeout=10)
    else:
        r = sesion.get(url, headers=cabeceras, timeout=10)
    ms = (time.perf_counter() - t0) * 1000
    try:
        cuerpo = r.json()
    except ValueError:
        cuerpo = {}
    return r.status_code, ms, cuerpo


def esperar_servicios(urls, timeout=60):
    limite = time.time() + timeout
    pendientes = dict(urls)
    while pendientes and time.time() < limite:
        for nombre, url in list(pendientes.items()):
            try:
                if requests.get(f"{url}/health", timeout=2).ok:
                    del pendientes[nombre]
            except requests.RequestException:
                pass
        if pendientes:
            time.sleep(1)
    if pendientes:
        raise RuntimeError(f"Servicios no disponibles: {', '.join(pendientes)}")


def esperar_alertas(url_alertas, esperadas, timeout=15):
    limite = time.time() + timeout
    while True:
        datos = requests.get(f"{url_alertas}/alertas", params={"limite": 100000}, timeout=5).json()
        if datos["total"] >= esperadas or time.time() > limite:
            return datos
        time.sleep(0.3)


def ejecutar(siniestros_url="http://localhost:6001", verificador_url="http://localhost:6002",
             alertas_url="http://localhost:6003", n_legitimas=60, n_ataques=70, n_latencia=100,
             secreto=SECRETO_DEFECTO, semilla=7, meta_sobrecosto_ms=50.0, pausa_s=0.0, notificar=None):
    """Corre el experimento completo. `notificar(fase, **datos)` (opcional) recibe el
    progreso en vivo: lo usa el dashboard para animar cada solicitud."""
    notificar = notificar or (lambda fase, **datos: None)
    notificar("preparando")
    esperar_servicios({"ms-siniestros": siniestros_url, "verificador-autorizacion": verificador_url,
                       "ms-alertas-auditoria": alertas_url})
    for url in (siniestros_url, verificador_url, alertas_url):
        requests.post(f"{url}/reset", timeout=5).raise_for_status()

    sesion = requests.Session()
    plan = construir_plan(n_legitimas, n_ataques, secreto, semilla)
    notificar("enviando", hechas=0, total=len(plan))
    for n, item in enumerate(plan, 1):
        item["status"], item["ms"], cuerpo = enviar(sesion, siniestros_url, item)
        item["motivo"] = cuerpo.get("motivo") or ("OK" if 200 <= item["status"] < 300 else None)
        notificar("enviando", hechas=n, total=len(plan), item=item)
        if pausa_s:
            time.sleep(pausa_s)

    ataques = [i for i in plan if i["clase"] == "ataque"]
    legitimas = [i for i in plan if i["clase"] == "legitima"]

    notificar("auditando")
    datos_alertas = esperar_alertas(alertas_url, len(ataques))
    alertadas = {a["solicitud_id"] for a in datos_alertas["alertas"]}
    aprobadas = set(requests.get(f"{siniestros_url}/aprobaciones", timeout=5).json()["solicitud_ids"])

    por_tipo = defaultdict(lambda: {"enviadas": 0, "detectadas": 0, "bloqueadas": 0, "falsos_positivos": 0})
    for i in plan:
        t = por_tipo[i["tipo"]]
        t["enviadas"] += 1
        if i["clase"] == "ataque":
            t["detectadas"] += i["solicitud_id"] in alertadas
            t["bloqueadas"] += i["status"] == 403
        else:
            t["falsos_positivos"] += i["solicitud_id"] in alertadas or not 200 <= i["status"] < 300

    detectados = sum(i["solicitud_id"] in alertadas for i in ataques)
    bloqueados = sum(i["status"] == 403 for i in ataques)
    aprob_indebidas = sum(i["solicitud_id"] in aprobadas for i in ataques)
    falsos_positivos = sum(por_tipo[t]["falsos_positivos"] for t in LEGITIMAS)

    # Sobrecosto: pares alternados RBAC local (baseline) vs verificador central.
    lat_base, lat_central = [], []
    token_liq = emitir("luis.liquidador", "LiquidadorSiniestros", secreto)
    for k in range(n_latencia):
        if k % 10 == 0:
            notificar("midiendo_latencia", hechas=k, total=n_latencia)
        for prefijo, destino in (("/baseline", lat_base), ("", lat_central)):
            item = {"accion": APROBAR, "token": token_liq, "siniestro_id": f"LAT-{k}",
                    "solicitud_id": f"lat{prefijo.replace('/', '-')}-{k:04d}"}
            status, ms, _ = enviar(sesion, siniestros_url, item, prefijo)
            if status != 201:
                raise RuntimeError(f"Medición de latencia falló ({prefijo or 'central'}): HTTP {status}")
            destino.append(ms)

    latencia = {
        "rbac_local_ms": {"p50": percentil(lat_base, 50), "p95": percentil(lat_base, 95)},
        "verificador_central_ms": {"p50": percentil(lat_central, 50), "p95": percentil(lat_central, 95)},
    }
    latencia["sobrecosto_ms"] = {
        p: round(latencia["verificador_central_ms"][p] - latencia["rbac_local_ms"][p], 2) for p in ("p50", "p95")
    }
    latencia["muestras_ms"] = {"rbac_local": [round(x, 2) for x in lat_base],
                               "verificador_central": [round(x, 2) for x in lat_central]}

    resultado = {
        "fecha": datetime.now().isoformat(timespec="seconds"),
        "parametros": {"legitimas": n_legitimas, "ataques": n_ataques, "latencia": n_latencia, "semilla": semilla},
        "deteccion_pct": round(100 * detectados / len(ataques), 2) if ataques else None,
        "bloqueo_pct": round(100 * bloqueados / len(ataques), 2) if ataques else None,
        "falsos_positivos_pct": round(100 * falsos_positivos / len(legitimas), 2) if legitimas else None,
        "aprobaciones_indebidas": aprob_indebidas,
        "alertas": {"total": datos_alertas["total"], "duplicados": datos_alertas["duplicados"],
                    "por_motivo": datos_alertas["por_motivo"],
                    "latencia_deteccion_a_registro_ms": datos_alertas["latencia_registro_ms"]},
        "latencia": latencia,
        "por_tipo": dict(por_tipo),
        "no_detectados": [i["solicitud_id"] for i in ataques if i["solicitud_id"] not in alertadas],
    }
    resultado["cumple"] = {
        "deteccion_100": resultado["deteccion_pct"] == 100.0,
        "falsos_positivos_0": resultado["falsos_positivos_pct"] == 0.0,
        "integridad_0_aprobaciones_indebidas": aprob_indebidas == 0,
        f"sobrecosto_p95_menor_{int(meta_sobrecosto_ms)}ms": latencia["sobrecosto_ms"]["p95"] < meta_sobrecosto_ms,
    }
    resultado["hipotesis_confirmada"] = all(resultado["cumple"].values())
    return resultado


def imprimir(r):
    print("\n=== Experimento 2 — Elevación de privilegios (ASR-SEG-09) ===\n")
    print(f"{'Tipo':<22}{'Clase':<10}{'Enviadas':>9}{'Detect.':>9}{'Bloq.':>7}{'FP':>5}")
    for tipo, t in r["por_tipo"].items():
        clase = "ataque" if tipo in ATAQUES else "legítima"
        det = t["detectadas"] if clase == "ataque" else "-"
        bloq = t["bloqueadas"] if clase == "ataque" else "-"
        fp = t["falsos_positivos"] if clase != "ataque" else "-"
        print(f"{tipo:<22}{clase:<10}{t['enviadas']:>9}{det:>9}{bloq:>7}{fp:>5}")
    lat = r["latencia"]
    print(f"\nDetección:              {r['deteccion_pct']} %   (bloqueo HTTP 403: {r['bloqueo_pct']} %)")
    print(f"Falsos positivos:       {r['falsos_positivos_pct']} %")
    print(f"Aprobaciones indebidas: {r['aprobaciones_indebidas']}")
    print(f"Alertas por motivo:     {r['alertas']['por_motivo']}")
    print(f"Detección -> registro:  {r['alertas']['latencia_deteccion_a_registro_ms']} ms")
    print(f"Latencia RBAC local:    p50 {lat['rbac_local_ms']['p50']} ms · p95 {lat['rbac_local_ms']['p95']} ms")
    print(f"Latencia verif.central: p50 {lat['verificador_central_ms']['p50']} ms · "
          f"p95 {lat['verificador_central_ms']['p95']} ms")
    print(f"Sobrecosto:             p50 {lat['sobrecosto_ms']['p50']} ms · p95 {lat['sobrecosto_ms']['p95']} ms")
    print("\nCriterios:")
    for criterio, ok in r["cumple"].items():
        print(f"  {'✅' if ok else '❌'} {criterio}")
    print(f"\nHipótesis {'CONFIRMADA' if r['hipotesis_confirmada'] else 'NO confirmada'}\n")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--siniestros-url", default=os.environ.get("SINIESTROS_URL", "http://localhost:6001"))
    p.add_argument("--verificador-url", default=os.environ.get("VERIFICADOR_URL", "http://localhost:6002"))
    p.add_argument("--alertas-url", default=os.environ.get("ALERTAS_URL", "http://localhost:6003"))
    p.add_argument("--legitimas", type=int, default=60)
    p.add_argument("--ataques", type=int, default=70)
    p.add_argument("--latencia", type=int, default=100, help="pares baseline/central para medir sobrecosto")
    p.add_argument("--secreto", default=os.environ.get("JWT_SECRET", SECRETO_DEFECTO))
    p.add_argument("--semilla", type=int, default=7)
    p.add_argument("--salida", default=os.path.join("resultados",
                                                    f"resultado-{datetime.now():%Y%m%d-%H%M%S}.json"))
    a = p.parse_args()

    r = ejecutar(a.siniestros_url, a.verificador_url, a.alertas_url, a.legitimas, a.ataques,
                 a.latencia, a.secreto, a.semilla)
    imprimir(r)
    os.makedirs(os.path.dirname(a.salida) or ".", exist_ok=True)
    with open(a.salida, "w", encoding="utf-8") as f:
        json.dump(r, f, ensure_ascii=False, indent=2)
    print(f"Resultados guardados en {a.salida}")
    sys.exit(0 if r["hipotesis_confirmada"] else 1)


if __name__ == "__main__":
    main()
