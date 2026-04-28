import pytest
from core.phone_utils import processar_telefone


def test_celular_9_digitos():
    r = processar_telefone("11987654321")
    assert r is not None
    assert r["ddd"] == "11"
    assert r["numero"] == "987654321"
    assert r["tipo"] == "M"
    assert r["ddi"] == "55"


def test_fixo_8_digitos():
    r = processar_telefone("1134567890")
    assert r is not None
    assert r["ddd"] == "11"
    assert r["numero"] == "34567890"
    assert r["tipo"] == "R"


def test_remove_ddi_55():
    r = processar_telefone("5511987654321")
    assert r is not None
    assert r["ddd"] == "11"
    assert r["numero"] == "987654321"


def test_ddi_55_nao_removido_se_numero_curto():
    # "5511" + 8 dígitos = 12 dígitos — NÃO remove DDI (seria ddd=55, num=11...)
    # Comportamento: 55 só é removido se len > 11
    r = processar_telefone("551134567890")  # 12 dígitos → remove DDI → "1134567890"
    assert r is not None
    assert r["ddd"] == "11"
    assert r["numero"] == "34567890"


def test_todos_digitos_iguais_invalido():
    assert processar_telefone("11111111111") is None
    assert processar_telefone("00000000000") is None


def test_numero_muito_curto_invalido():
    assert processar_telefone("1234567") is None


def test_vazio_invalido():
    assert processar_telefone("") is None


def test_apenas_nao_digitos_invalido():
    assert processar_telefone("(-)") is None


def test_ddd_invalido_zerado():
    # DDD 10 < 11 → ddd vira "00"
    r = processar_telefone("1034567890")
    assert r is not None
    assert r["ddd"] == "00"


def test_tipo_fixo_sem_9_inicial():
    r = processar_telefone("1134567890")
    assert r["tipo"] == "R"


def test_tipo_celular_com_9_inicial():
    r = processar_telefone("11987654321")
    assert r["tipo"] == "M"


def test_pontuacao_ignorada():
    r = processar_telefone("(11) 9.8765-4321")
    assert r is not None
    assert r["ddd"] == "11"
    assert r["numero"] == "987654321"
