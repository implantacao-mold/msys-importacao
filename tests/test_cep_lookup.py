from __future__ import annotations
from unittest.mock import MagicMock, patch

import core.cep_lookup as cep_module
from core.cep_lookup import lookup_cep, fill_city_state


def _make_conn_mock(row: dict | None):
    cur = MagicMock()
    cur.fetchone.return_value = row
    conn = MagicMock()
    conn.is_connected.return_value = False  # force reconnect each time
    conn.cursor.return_value = cur
    return conn


def test_lookup_cep_invalid_digits():
    assert lookup_cep("123") is None
    assert lookup_cep("abc") is None
    assert lookup_cep("") is None


def test_fill_city_state_already_filled():
    assert fill_city_state("01310100", "São Paulo", "SP") == ("São Paulo", "SP")


def test_fill_city_state_invalid_cep():
    assert fill_city_state("", "", "") == ("", "")
    assert fill_city_state("123", "", "") == ("", "")


def test_fill_city_state_from_lookup():
    mock_conn = _make_conn_mock({"nam_city": "Curitiba", "sgl_uf": "PR"})
    # clear cache entry so the DB is actually queried
    cep_module._cache.pop("80010000", None)
    with patch("mysql.connector.connect", return_value=mock_conn):
        result = fill_city_state("80010000", "", "")
    assert result == ("Curitiba", "PR")


def test_fill_city_state_partial():
    mock_conn = _make_conn_mock({"nam_city": "Curitiba", "sgl_uf": "PR"})
    cep_module._cache.pop("80020000", None)
    with patch("mysql.connector.connect", return_value=mock_conn):
        cidade, estado = fill_city_state("80020000", "Curitiba", "")
    assert cidade == "Curitiba"
    assert estado == "PR"


def test_lookup_cep_not_found():
    mock_conn = _make_conn_mock(None)
    cep_module._cache.pop("00000000", None)
    with patch("mysql.connector.connect", return_value=mock_conn):
        result = lookup_cep("00000000")
    assert result is None
