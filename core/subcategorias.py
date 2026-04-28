from __future__ import annotations
import json
import pathlib
import threading

# Lista completa de subcategorias do Msys Imob.
# Chave: idt_property_sub_category (int)
# Valor: (categoria, subcategoria)
SUBCATEGORIAS: dict[int, tuple[str, str]] = {
    0:  ("Casas",        "Comercial"),
    1:  ("Apartamentos", "Padrão"),
    2:  ("Apartamentos", "Cobertura"),
    3:  ("Apartamentos", "Flat"),
    4:  ("Apartamentos", "Kitnet"),
    5:  ("Apartamentos", "Duplex"),
    6:  ("Apartamentos", "Triplex"),
    7:  ("Casas",        "Padrão"),
    8:  ("Casas",        "Sobrado"),
    9:  ("Casas",        "Edícula"),
    10: ("Casas",        "Condomínio"),
    11: ("Comercial",    "Sala"),
    12: ("Comercial",    "Salão"),
    14: ("Comercial",    "Prédio"),
    15: ("Comercial",    "Box"),
    16: ("Rural",        "Chácara"),
    17: ("Rural",        "Fazenda"),
    18: ("Rural",        "Área"),
    19: ("Rural",        "Sítio"),
    20: ("Rural",        "Haras"),
    21: ("Terreno",      "Padrão"),
    22: ("Terreno",      "Condomínio"),
    23: ("Terreno",      "Lote"),
    24: ("Apartamentos", "Garagem"),
    25: ("Comercial",    "Loja"),
    26: ("Terreno",      "Residencial"),
    27: ("Terreno",      "Comercial"),
    28: ("Terreno",      "Área"),
    29: ("Rural",        "Rancho"),
    30: ("Rural",        "Ponto"),
    31: ("Comercial",    "Ponto Comercial"),
    32: ("Terreno",      "Industrial"),
    33: ("Apartamentos", "Loft"),
    34: ("Casas",        "Área de Lazer"),
    35: ("Rural",        "Pesqueiro"),
    36: ("Casas",        "Townhouse"),
    37: ("Comercial",    "Townhouse"),
    38: ("Casas",        "Pousada"),
    39: ("Casas",        "Kitnet"),
    40: ("Casas",        "Sobrado Condomínio"),
    41: ("Comercial",    "Barracão/Galpão"),
    42: ("Comercial",    "Terreno"),
    43: ("Apartamentos", "Garden"),
    44: ("Industrial",   "Galpão"),
    45: ("Industrial",   "Terreno"),
    46: ("Apartamentos", "Studio"),
    47: ("Casas",        "Chalé"),
    48: ("Casas",        "Fundos"),
    49: ("Rural",        "Chalé"),
    50: ("Rural",        "Chácara em condomínio"),
    51: ("Rural",        "Edícula"),
    52: ("Casas",        "Edícula em condomínio"),
    53: ("Industrial",   "Prédio"),
    54: ("Apartamentos", "Privativo"),
    55: ("Comercial",    "Garagem"),
    56: ("Casas",        "Chácara"),
    57: ("Comercial",    "Sobrado"),
    58: ("Casas",        "Sobreposta"),
    59: ("Comercial",    "Hotel"),
    60: ("Casas",        "Loteamento Fechado"),
    61: ("Comercial",    "Armazém"),
    62: ("Comercial",    "Pavilhão"),
    63: ("Casas",        "Mansão"),
    64: ("Apartamentos", "Térreo"),
    65: ("Apartamentos", "Cobertura Duplex"),
    66: ("Casas",        "Geminada"),
    67: ("Casas",        "Rancho"),
    68: ("Comercial",    "Conjunto Comercial"),
    69: ("Casas",        "Alto Padrão"),
    70: ("Comercial",    "Casa"),
    71: ("Terreno",      "Misto"),
    72: ("Apartamentos", "Alto Padrão"),
}

# ── Custom subcategory mappings (persisted to disk) ───────────────────────────

_CUSTOM_PATH = pathlib.Path(__file__).parent.parent / "data" / "custom_subcategorias.json"
_custom_subs: dict[str, str] = {}
_custom_lock = threading.Lock()


def _load_custom_subs() -> None:
    global _custom_subs
    if _CUSTOM_PATH.exists():
        try:
            _custom_subs = json.loads(_CUSTOM_PATH.read_text("utf-8"))
        except Exception:
            _custom_subs = {}


def get_custom_subcat(tipo: str, subtipo: str) -> str | None:
    """Returns the saved subcategory ID for a (tipo, subtipo) pair, or None."""
    key = f"{tipo}|{subtipo}"
    with _custom_lock:
        return _custom_subs.get(key)


def save_custom_subcat(tipo: str, subtipo: str, id_str: str | None) -> None:
    """Persists a (tipo, subtipo) → id mapping. Pass id_str=None to remove."""
    key = f"{tipo}|{subtipo}"
    with _custom_lock:
        if id_str:
            _custom_subs[key] = id_str
        else:
            _custom_subs.pop(key, None)
        try:
            _CUSTOM_PATH.parent.mkdir(parents=True, exist_ok=True)
            _CUSTOM_PATH.write_text(
                json.dumps(_custom_subs, ensure_ascii=False, indent=2), "utf-8"
            )
        except Exception:
            pass


def get_subcategoria_options() -> list[dict]:
    """Sorted list of {value, label} for all SUBCATEGORIAS — used in UI dropdowns."""
    return [
        {"value": str(k), "label": f"{v[0]} / {v[1]}"}
        for k, v in sorted(SUBCATEGORIAS.items())
    ]


_load_custom_subs()
