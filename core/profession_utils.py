"""Utilitários de matching para profissão e órgão expedidor do RG.

Lógica:
  - Correspondência exata ou muito alta (>= 0.92) → aplica canonical automaticamente
  - Correspondência média (0.70 – 0.92)           → exibe para revisão do usuário ("uncertain")
  - Sem correspondência (< 0.70)                   → mantém o valor original sem alterar
  - Mapeamento manual salvo                        → usa o mapeamento salvo (pode ser None = manter original)

Chamado automaticamente por core/exporter.py para todos os PersonRecord.
"""
from __future__ import annotations
import difflib
import json
import pathlib
import threading
import unicodedata

_DATA_DIR = pathlib.Path(__file__).parent.parent / "data"

_PROFISSOES_PATH     = _DATA_DIR / "profissoes.json"
_ORGAOS_PATH         = _DATA_DIR / "orgaos_expedidores.json"
_CUSTOM_PROF_PATH    = _DATA_DIR / "custom_profissoes.json"
_CUSTOM_ORGAO_PATH   = _DATA_DIR / "custom_orgaos.json"

_lock = threading.Lock()

# Listas canônicas
_profissoes:  list[str] = []   # nam_profession
_orgaos:      list[str] = []   # nam_issuing_institution

# Versões normalizadas (sem acento, minúsculas) para matching
_prof_norm:   list[str] = []
_orgao_norm:  list[str] = []

# Mapeamentos manuais salvos pelo usuário
_custom_prof:  dict[str, str | None] = {}   # source → canonical (None = manter original)
_custom_orgao: dict[str, str | None] = {}


# ── Normalização ──────────────────────────────────────────────────────────────

def _norm(s: str) -> str:
    """Minúsculas + remove diacríticos + strip."""
    return (
        unicodedata.normalize("NFKD", s.strip().lower())
        .encode("ascii", "ignore")
        .decode()
    )


# ── Carga inicial ─────────────────────────────────────────────────────────────

def _load() -> None:
    global _profissoes, _orgaos, _prof_norm, _orgao_norm, _custom_prof, _custom_orgao

    try:
        data = json.loads(_PROFISSOES_PATH.read_text("utf-8"))
        _profissoes = [item["nam_profession"] for item in data]
        _prof_norm  = [_norm(n) for n in _profissoes]
    except Exception:
        _profissoes = []
        _prof_norm  = []

    try:
        data = json.loads(_ORGAOS_PATH.read_text("utf-8"))
        _orgaos    = [item["nam_issuing_institution"] for item in data]
        _orgao_norm = [_norm(n) for n in _orgaos]
    except Exception:
        _orgaos    = []
        _orgao_norm = []

    try:
        _custom_prof = json.loads(_CUSTOM_PROF_PATH.read_text("utf-8"))
    except Exception:
        _custom_prof = {}

    try:
        _custom_orgao = json.loads(_CUSTOM_ORGAO_PATH.read_text("utf-8"))
    except Exception:
        _custom_orgao = {}


def _save_json(path: pathlib.Path, data: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
    except Exception:
        pass


# ── Matching genérico ─────────────────────────────────────────────────────────

def _match(
    name: str,
    canonical_list: list[str],
    norm_list: list[str],
    cutoff_auto: float = 0.92,
    cutoff_review: float = 0.70,
) -> dict:
    """
    Retorna dict com:
      status   : "matched" | "uncertain" | "unmatched"
      canonical: str | None
      score    : float
    """
    if not name or not canonical_list:
        return {"status": "unmatched", "canonical": None, "score": 0.0}

    n = _norm(name)

    # Correspondência exata
    if n in norm_list:
        idx = norm_list.index(n)
        return {"status": "matched", "canonical": canonical_list[idx], "score": 1.0}

    # Fuzzy
    matches = difflib.get_close_matches(n, norm_list, n=1, cutoff=cutoff_review)
    if not matches:
        return {"status": "unmatched", "canonical": None, "score": 0.0}

    idx   = norm_list.index(matches[0])
    score = difflib.SequenceMatcher(None, n, matches[0]).ratio()
    canonical = canonical_list[idx]

    if score >= cutoff_auto:
        return {"status": "matched", "canonical": canonical, "score": score}
    return {"status": "uncertain", "canonical": canonical, "score": score}


# ── API pública — scan ────────────────────────────────────────────────────────

def scan_profession(name: str) -> dict:
    """Retorna info de matching para um valor de profissão."""
    with _lock:
        if name in _custom_prof:
            canonical = _custom_prof[name]
            return {"status": "mapped", "canonical": canonical, "score": 1.0}
    return _match(name, _profissoes, _prof_norm)


def scan_orgao(name: str) -> dict:
    """Retorna info de matching para um valor de órgão expedidor."""
    with _lock:
        if name in _custom_orgao:
            canonical = _custom_orgao[name]
            return {"status": "mapped", "canonical": canonical, "score": 1.0}
    # Órgãos têm lista pequena — usa cutoffs mais flexíveis
    return _match(name, _orgaos, _orgao_norm, cutoff_auto=0.85, cutoff_review=0.60)


# ── API pública — export ──────────────────────────────────────────────────────

def resolve_profession(name: str) -> str:
    """Retorna o nome canônico para profissão, ou o original se não mapeado."""
    if not name:
        return name
    with _lock:
        if name in _custom_prof:
            return _custom_prof[name] or name   # None = manter original
    info = _match(name, _profissoes, _prof_norm)
    return info["canonical"] if info["status"] == "matched" else name


def resolve_orgao(name: str) -> str:
    """Retorna o nome canônico para órgão expedidor, ou o original se não mapeado."""
    if not name:
        return name
    with _lock:
        if name in _custom_orgao:
            return _custom_orgao[name] or name
    info = _match(name, _orgaos, _orgao_norm, cutoff_auto=0.85, cutoff_review=0.60)
    return info["canonical"] if info["status"] == "matched" else name


# ── API pública — persistência ────────────────────────────────────────────────

def save_profession_mapping(source: str, canonical) -> None:
    """Salva mapeamento manual. canonical=None significa 'manter original'."""
    with _lock:
        _custom_prof[source] = canonical
        _save_json(_CUSTOM_PROF_PATH, _custom_prof)


def save_orgao_mapping(source: str, canonical) -> None:
    with _lock:
        _custom_orgao[source] = canonical
        _save_json(_CUSTOM_ORGAO_PATH, _custom_orgao)


def get_profession_options() -> list[str]:
    return list(_profissoes)


def get_orgao_options() -> list[str]:
    return list(_orgaos)


_load()
