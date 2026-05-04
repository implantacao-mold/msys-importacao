from __future__ import annotations
import json
import pathlib
import re
import threading

# Mapeamento nome completo → sigla UF (case-insensitive via .upper())
_ESTADO_NOME_PARA_UF: dict[str, str] = {
    "ACRE": "AC", "ALAGOAS": "AL", "AMAPÁ": "AP", "AMAPA": "AP",
    "AMAZONAS": "AM", "BAHIA": "BA", "CEARÁ": "CE", "CEARA": "CE",
    "DISTRITO FEDERAL": "DF", "ESPÍRITO SANTO": "ES", "ESPIRITO SANTO": "ES",
    "GOIÁS": "GO", "GOIAS": "GO", "MARANHÃO": "MA", "MARANHAO": "MA",
    "MATO GROSSO DO SUL": "MS", "MATO GROSSO": "MT",
    "MINAS GERAIS": "MG", "PARÁ": "PA", "PARA": "PA",
    "PARAÍBA": "PB", "PARAIBA": "PB", "PARANÁ": "PR", "PARANA": "PR",
    "PERNAMBUCO": "PE", "PIAUÍ": "PI", "PIAUI": "PI",
    "RIO DE JANEIRO": "RJ", "RIO GRANDE DO NORTE": "RN",
    "RIO GRANDE DO SUL": "RS", "RONDÔNIA": "RO", "RONDONIA": "RO",
    "RORAIMA": "RR", "SANTA CATARINA": "SC", "SÃO PAULO": "SP", "SAO PAULO": "SP",
    "SERGIPE": "SE", "TOCANTINS": "TO",
}


def normalize_estado_uf(estado: str) -> str:
    """Converte nome completo de estado para sigla de 2 letras.

    Se já for uma sigla de 2 letras, retorna em maiúsculas sem alteração.
    Útil para mappers cujo sistema de origem armazena o nome por extenso.
    """
    if not estado:
        return ""
    s = estado.strip()
    if len(s) == 2:
        return s.upper()
    return _ESTADO_NOME_PARA_UF.get(s.upper(), s)

_CACHE_PATH = pathlib.Path(__file__).parent.parent / "data" / "cep_cache.json"
_DB_CONFIG_PATH = pathlib.Path(__file__).parent.parent / "data" / "db_config.json"

_cache: dict[str, dict | None] = {}
_lock = threading.Lock()
_conn = None


def _load_db_config() -> dict:
    try:
        return json.loads(_DB_CONFIG_PATH.read_text("utf-8"))
    except Exception:
        return {}


_DB_CONFIG = _load_db_config()


def _load_cache() -> None:
    global _cache
    if _CACHE_PATH.exists():
        try:
            _cache = json.loads(_CACHE_PATH.read_text("utf-8"))
        except Exception:
            _cache = {}


def _save_cache() -> None:
    try:
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_PATH.write_text(json.dumps(_cache, ensure_ascii=False, indent=2), "utf-8")
    except Exception:
        pass


def _get_conn():
    global _conn
    try:
        if _conn and _conn.is_connected():
            return _conn
    except Exception:
        pass
    import mysql.connector
    _conn = mysql.connector.connect(
        **_DB_CONFIG,
        connect_timeout=5,
        charset="utf8",
        use_pure=True,
    )
    return _conn


def lookup_cep(cep: str) -> dict[str, str] | None:
    """Consulta o banco de CEPs e retorna {"cidade": ..., "estado": ...} ou None."""
    digits = re.sub(r"\D", "", cep)
    if len(digits) != 8:
        return None

    with _lock:
        if digits in _cache:
            return _cache[digits]

    try:
        conn = _get_conn()
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT nam_city, sgl_uf FROM address WHERE num_postal_code = %s LIMIT 1",
            (digits,),
        )
        row = cur.fetchone()
        result: dict | None = (
            {"cidade": row["nam_city"], "estado": row["sgl_uf"]} if row else None
        )
    except Exception:
        return None  # falha de conexão: não cacheia, tenta de novo na próxima exportação

    with _lock:
        _cache[digits] = result
        _save_cache()

    return result


def lookup_cep_by_city(cidade: str, estado: str) -> str | None:
    """Busca o CEP geral de uma cidade/UF (sufixo 000, sem endereço específico).

    Útil como fallback quando o imóvel não possui CEP no sistema de origem.
    Aceita tanto siglas (MG) quanto nomes completos (Minas Gerais) — normaliza
    automaticamente para sigla de 2 letras antes de consultar o banco.
    Retorna string de 8 dígitos ou None se não encontrado / falha de conexão.
    """
    if not cidade or not estado:
        return None

    uf = normalize_estado_uf(estado)
    cache_key = f"city:{uf.upper()}:{cidade.strip().upper()}"
    with _lock:
        if cache_key in _cache:
            return _cache[cache_key]  # type: ignore[return-value]

    try:
        conn = _get_conn()
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """SELECT num_postal_code FROM address
               WHERE UPPER(nam_city) = UPPER(%s)
                 AND sgl_uf = UPPER(%s)
                 AND num_postal_code LIKE %s
               ORDER BY num_postal_code ASC
               LIMIT 1""",
            (cidade.strip(), uf, "%000"),
        )
        row = cur.fetchone()
        result: str | None = row["num_postal_code"] if row else None
    except Exception:
        return None

    with _lock:
        _cache[cache_key] = result  # type: ignore[assignment]
        _save_cache()

    return result


_CEP_PLACEHOLDERS = {"00000000", "99999999"}


def is_valid_cep(cep: str) -> bool:
    """Returns True only if *cep* is exactly 8 digits and not a known placeholder."""
    return len(cep) == 8 and cep not in _CEP_PLACEHOLDERS


def fill_city_state(cep: str, cidade: str, estado: str) -> tuple[str, str]:
    """Preenche cidade/estado ausentes via CEP. Retorna os valores inalterados se já preenchidos."""
    if cidade and estado:
        return cidade, estado
    result = lookup_cep(cep)
    if result:
        return (
            result["cidade"] if not cidade else cidade,
            result["estado"] if not estado else estado,
        )
    return cidade, estado


def fix_record_cep(record) -> None:
    """Normaliza CEP em qualquer record com atributos .cep / .cidade / .estado.

    Regras (aplicadas em ordem):
    1. Strip de não-dígitos no CEP.
    2. CEP válido (8 dígitos, fora dos placeholders) → fill_city_state para
       preencher cidade/estado ausentes.
    3. CEP inválido/incompleto/placeholder → lookup_cep_by_city como fallback,
       desde que cidade e estado estejam disponíveis.

    Chamada automaticamente pelos exporters para TODOS os records de todos os
    mappers. Mappers individuais não precisam chamar fill_city_state nem
    lookup_cep_by_city — estas chamadas nos mappers são redundantes mas inofensivas.
    """
    cep    = re.sub(r"\D", "", str(getattr(record, "cep",    "") or ""))
    cidade = str(getattr(record, "cidade", "") or "")
    estado = normalize_estado_uf(str(getattr(record, "estado", "") or ""))

    if is_valid_cep(cep):
        cidade, estado = fill_city_state(cep, cidade, estado)
    elif cidade and estado:
        looked_up = lookup_cep_by_city(cidade, estado)
        if looked_up:
            cep = looked_up

    record.cep    = cep
    record.cidade = cidade
    record.estado = estado


_load_cache()
