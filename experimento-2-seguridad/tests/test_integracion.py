"""Experimento real contra los contenedores: docker compose up -d && pytest -m integration"""
import pytest

from run_experimento import ejecutar


@pytest.mark.integration
def test_hipotesis_asr_seg_09():
    r = ejecutar(n_legitimas=40, n_ataques=49, n_latencia=50)
    assert r["no_detectados"] == []
    assert r["cumple"], r
    assert r["hipotesis_confirmada"], r["cumple"]
