from __future__ import annotations
import difflib
import json
import pathlib
import re
import threading
import unicodedata
import urllib.request

_CACHE_PATH = pathlib.Path(__file__).parent.parent / "data" / "bank_codes_cache.json"
_BRASILAPI_URL = "https://brasilapi.com.br/api/banks/v1"

_lock = threading.Lock()
_norm_to_code: dict[str, str] = {}   # normalizado → código FEBRABAN
_loaded = False


# Dicionário de apelidos e variações que a API não cobre
_ALIASES: dict[str, str] = {
    "bb": "1",
    "bdo brasil": "1",
    "cef": "104",
    "caixa": "104",
    "itau": "341",
    "bradesco": "237",
    "santander": "33",
    "nubank": "260",
    "nu pagamentos": "260",
    "inter": "77",
    "c6": "336",
    "c6 bank": "336",
    "xp": "102",
    "btg": "208",
    "btg pactual": "208",
    "sicredi": "748",
    "cooperativo sicredi": "748",
    "sicoob": "756",
    "cooperativo sicoob": "756",
    "banrisul": "41",
    "estado do rs": "41",
    "pagbank": "290",
    "pagseguro": "290",
    "mercado pago": "323",
    "picpay": "380",
    "neon": "735",
    "next": "237",
    "bv": "655",
    "safra": "422",
    "original": "212",
    "daycoval": "707",
    "pan": "623",
    "pine": "643",
    "modal": "746",
    "rendimento": "633",
    "agibank": "121",
    "bs2": "218",
    "stone": "197",
    "will bank": "280",
    "will": "280",
    "digio": "335",
    "bari": "330",
    "cresol": "133",
    "unicred": "136",
    "ailos": "85",
    "uniprime": "84",
    "brb": "70",
    "banese": "47",
    "banpara": "37",
    "banestes": "21",
}

_STRIP_RE = re.compile(
    r"\s*[\(\[].*?[\)\]]"                       # parênteses/colchetes: "(Brasil)", "[RJ]"
    r"|\bs\.?\s*[/.]?\s*a\.?(?=\s|$|[,;])"     # S.A, S/A, S. A., S.A.
    r"|\b(ltda|eireli|me|epp)\.?(?=\s|$)",      # tipos societários
    re.IGNORECASE,
)


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode().lower()
    s = _STRIP_RE.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def _fmt_code(code) -> str:
    """Garante código sem zeros à esquerda desnecessários (API retorna int)."""
    try:
        return str(int(code))
    except (TypeError, ValueError):
        return str(code)


def _load() -> None:
    global _loaded
    with _lock:
        if _loaded:
            return
        raw: list[dict] = []

        # 1. Tenta cache local
        if _CACHE_PATH.exists():
            try:
                raw = json.loads(_CACHE_PATH.read_text("utf-8"))
            except Exception:
                raw = []

        # 2. Se cache vazio, busca na API
        if not raw:
            try:
                req = urllib.request.Request(_BRASILAPI_URL, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=8) as resp:
                    raw = json.loads(resp.read().decode("utf-8"))
                _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
                _CACHE_PATH.write_text(json.dumps(raw, ensure_ascii=False), "utf-8")
            except Exception:
                raw = []

        # 3. Constrói índice normalizado → código
        for bank in raw:
            code = _fmt_code(bank.get("code") or bank.get("codigo") or "")
            if not code or code == "0":
                continue
            for field in ("name", "fullName", "nome", "nomeCompleto"):
                name = bank.get(field) or ""
                if name:
                    _norm_to_code[_norm(name)] = code

        # 4. Adiciona apelidos
        for alias, code in _ALIASES.items():
            _norm_to_code.setdefault(alias, code)

        _loaded = True


_BANK_PREFIXES = ("banco do ", "banco da ", "banco dos ", "banco das ", "banco ", "bco do ", "bco da ", "bco ")


def bank_name_to_code(name: str) -> str:
    """Converte nome de banco para código FEBRABAN.

    Estratégia em 4 passos:
    1. Já é código numérico → retorna direto.
    2. Match exato após normalização.
    3. Tenta sem prefixo "banco/bco" (ex: "Banco Sicredi" → "sicredi").
    4. Verifica se o input está contido em alguma chave conhecida (ex: "btg pactual" ⊂ "banco btg pactual").
    5. Fuzzy match com cutoff 0.78.
    Retorna o valor original se não encontrar.
    """
    if not name:
        return ""
    stripped = name.strip()
    if re.fullmatch(r"\d+", stripped):
        return stripped

    _load()

    key = _norm(stripped)
    if not key:
        return stripped

    # 1. Exato
    if key in _norm_to_code:
        return _norm_to_code[key]

    # 2. Sem prefixo "banco/bco"
    short = key
    for prefix in _BANK_PREFIXES:
        if key.startswith(prefix):
            short = key[len(prefix):]
            break
    if short != key and short in _norm_to_code:
        return _norm_to_code[short]

    # 3. Input contido numa chave conhecida (mínimo 4 chars para evitar falsos positivos)
    if len(short) >= 4:
        for known_key, code in _norm_to_code.items():
            if short in known_key:
                return code

    # 4. Fuzzy
    matches = difflib.get_close_matches(key, _norm_to_code.keys(), n=1, cutoff=0.78)
    if matches:
        return _norm_to_code[matches[0]]

    return stripped
