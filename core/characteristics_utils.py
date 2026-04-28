from __future__ import annotations
import difflib
import json
import pathlib
import re
import threading
import unicodedata
from typing import Iterable

from core.caracteristicas import CARACTERISTICAS_COMBOBOX

_CANONICAL = list(CARACTERISTICAS_COMBOBOX.values())

# ---------------------------------------------------------------------------
# Custom user mappings — persisted in data/custom_caracteristicas.json
# Keys: _norm(source_text); Values: canonical name or None (ignore)
# ---------------------------------------------------------------------------
_CUSTOM_PATH = pathlib.Path(__file__).parent.parent / "data" / "custom_caracteristicas.json"
_custom_lock = threading.Lock()
_custom: dict[str, str | None] = {}


def _load_custom() -> None:
    global _custom
    if _CUSTOM_PATH.exists():
        raw: dict = json.loads(_CUSTOM_PATH.read_text("utf-8"))
        _custom = {_norm(k): v for k, v in raw.items()}
    else:
        _custom = {}


def save_custom_mapping(source: str, canonical: str | None) -> None:
    """Persiste uma decisão de mapeamento. canonical=None = ignorar sempre."""
    with _custom_lock:
        raw: dict = {}
        if _CUSTOM_PATH.exists():
            raw = json.loads(_CUSTOM_PATH.read_text("utf-8"))
        raw[source.upper()] = canonical
        _CUSTOM_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CUSTOM_PATH.write_text(json.dumps(raw, ensure_ascii=False, indent=2), "utf-8")
        _load_custom()


def get_custom_mappings() -> dict[str, str | None]:
    """Retorna cópia do mapeamento customizado (chave = _norm do source)."""
    return dict(_custom)


def _norm(s: str) -> str:
    s = " ".join(s.split())  # colapsa espaços múltiplos
    return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode().lower()


_CANONICAL_LOWER: dict[str, str] = {c.lower(): c for c in _CANONICAL}
_CANONICAL_NORM: dict[str, str] = {_norm(c): c for c in _CANONICAL}

# ---------------------------------------------------------------------------
# Aliases de nomes de origem → nome canônico Msys
# Chaves: _norm(source_text);  Valores: nome canônico exato do CARACTERISTICAS_COMBOBOX
# Cobre variações do Imobzi e outros sistemas que diferem do canônico
# (espaço vs hífen, singular/plural, palavras distintas, abreviações, etc.)
# ---------------------------------------------------------------------------
_SOURCE_ALIASES: dict[str, str] = {
    # Espaços e lazer
    "play ground":                    "Playground",
    "area gourmet":                   "Espaço Gourmet",
    "espaco gourmet":                 "Espaço Gourmet",
    "salao gourmet":                  "Salão gourmet",
    "churrasqueira gourmet":          "Churrasqueiras",
    "espaco fitness":                 "Espaço Fitness",
    "fitness center":                 "Espaço Fitness",
    "salao de festas":                "Salão de Festas",
    "salao de jogos":                 "Salão de Jogos",
    "home theater":                   "Home theater",
    "home office":                    "Home office",
    "cinema particular":              "Cinema",
    "mini theater":                   "Cinema",
    # Mobília
    "mobiliado":                      "Mobília",
    "movel":                          "Mobília",
    "moveis":                         "Mobília",
    "semi mobiliado":                 "Semi mobiliado",
    # Ar-condicionado
    "ar condicionado":                "Ar-condicionado",
    "ar-condicionado central":        "Ar-condicionado",
    "ar condicionado central":        "Ar-condicionado",
    # Portaria / segurança
    "portaria 24hs":                  "Portaria 24 Hrs",
    "portaria 24h":                   "Portaria 24 Hrs",
    "portaria 24 horas":              "Portaria 24 Hrs",
    "portaria 24hrs":                 "Portaria 24 Hrs",
    "portaria social":                "Portaria Social",
    "portaria de servico":            "Portaria de Serviço",
    "cameras de seguranca":           "Monitoramento por câmeras",
    "camera de seguranca":            "Monitoramento por câmeras",
    "monitoramento":                  "Monitoramento por câmeras",
    "cftv":                           "Monitoramento por câmeras",
    "sistema de alarme":              "Alarme",
    "alarme monitorado":              "Alarme",
    "cerca eletrica":                 "Cerca elétrica",
    "portao eletronico":              "Portão eletrônico",
    "portao automatico":              "Portão eletrônico",
    # Piscinas
    "piscina adulto":                 "Piscina",
    "piscina aquecida":               "Piscina Aquecida",
    "piscina coberta":                "Piscina coberta",
    "piscina infantil":               "Piscina infantil",
    "piscina com raia":               "Piscina com raia",
    "hidromassagem":                  "Hidro",
    "banheira hidromassagem":         "Hidro",
    "ofuro":                          "Ofurô",
    # Elevadores
    "elevador":                       "Elevador Social",
    "elevador social":                "Elevador Social",
    "elevador de servico":            "Elevador de Serviço",
    # Vista
    "vista para o mar":               "Vista mar",
    "vista mar":                      "Vista mar",
    "vista para o lago":              "Vista para lago",
    "vista para montanha":            "Vista para a montanha",
    "vista para a montanha":          "Vista para a montanha",
    # Quadras
    "quadra poliesportiva":           "Quadra Poliesportiva",
    "quadra de tenis":                "Quadra de tênis",
    "quadra de beach tenis":          "Quadra de Beach Tênis",
    "quadra de futsal":               "Quadra de futsal",
    "quadra de squash":               "Quadra de squash",
    "quadra de volei de praia":       "Quadra de vôlei de praia",
    # Áreas externas
    "area de lazer":                  "Área de lazer",
    "area de servico":                "Área de serviço",
    "area privativa":                 "Área privativa",
    "varanda gourmet":                "Varanda Gourmet",
    "terraco":                        "Terraço",
    "terraco gourmet":                "Terraço gourmet",
    "deck molhado":                   "Deck Molhado",
    "deck de madeira":                "Deck de madeira",
    # Estacionamento / garagem
    "estacionamento coberto":         "Estacionamento coberto",
    "estacionamento externo":         "Estacionamento externo",
    "estacionamento para visitantes": "Estacionamento para visitante",
    "garagem coberta":                "Garagem",
    "garagem descoberta":             "Garagem descoberta",
    # Serviços / comodidades
    "bicicletario":                   "Bicicletário",
    "gas encanado":                   "Gás encanado",
    "energia solar":                  "Gerador de energia solar",
    "aquecedor solar":                "Aquecedor solar",
    "gerador":                        "Gerador elétrico",
    "poco artesiano":                 "Poço artesiano",
    "wi-fi":                          "Internet wireless",
    "wifi":                           "Internet wireless",
    "internet wireless":              "Internet wireless",
    "aceita animais":                 "Aceita pet",
    "aceita pets":                    "Aceita pet",
    "pet friendly":                   "Aceita pet",
    "coworking":                      "Coworking",
    "spa":                            "SPA",
    "espaco kids":                    "Espaço Kids",
    "brinquedoteca":                  "Brinquedoteca",
    "fraldario":                      "Fraldário",
    "pet place":                      "Pet Place",
    "car wash":                       "Car wash",
    "lavagem de carros":              "Car wash",
    # Outros comuns
    "lareira a gas":                  "Lareira à gás",
    "lareira ecologica":              "Lareira ecológica",
    "jardim de inverno":              "Jardim de inverno",
    "horta":                          "Horta",
    "redario":                        "Redário",
    "solarium":                       "Solarium",
    "sauna seca":                     "Sauna",
    "sauna a vapor":                  "Sauna úmida",
    "sauna umida":                    "Sauna úmida",
    "acesso para deficientes":        "Acesso para deficientes",
    "acesso sem degraus":             "Acesso sem degraus",
    "piso de madeira":                "Piso de madeira",
    "piso laminado":                  "Piso laminado",
    "armario embutido":               "Armário embutido",
    "armarios embutidos":             "Armário embutido",
    "fechadura digital":              "Fechadura digital",
    "condominio fechado":             "Condomínio fechado",
    "condominio sustentavel":         "Condomínio sustentável",
    "cabeamento estruturado":         "Cabeamento estruturado",
    "heliponto":                      "Heliponto",
    "mezanino":                       "Mezanino",
    "deposito privativo":             "Depósito privativo",
    "adega":                          "Adega",
    "sala de reuniao":                "Salas de reuniões",
    "sala de reunioes":               "Salas de reuniões",
    "pista de cooper":                "Pista de Cooper",
    "pista cooper":                   "Pista de Cooper",
    "pista de caminhada":             "Pista para caminhada",
    "paisagismo":                     "Paisagismo",
    "parque":                         "Parque",
    "lago de pesca":                  "Lago de pesca",
    "campo de golf":                  "Campo de Golf",
    "hipica":                         "Hípica",
    "praia artificial":               "Praia artificial",
}

_load_custom()  # runs after _norm is defined above

# ---------------------------------------------------------------------------
# Mapeamento autoritativo: ID Msys → campo do PropertyRecord
# Usado por sistemas que fornecem IDs diretamente e como referência canônica.
# ---------------------------------------------------------------------------
_ID_TO_FIELD: dict[int, str] = {
    5:   "dormitorios",
    7:   "banheiros",
    95:  "area_util",
    2:   "area_total",
    1:   "area_construida",
    133: "nome_propriedade",
    3:   "lado1",
    4:   "lado2",
    164: "lado3",
    165: "lado4",
    107: "area_total_rural",
    106: "unidade_medida",
    6:   "suites",
    8:   "closets",
    92:  "salas",
    9:   "copas",
    16:  "cozinhas",
    91:  "despensas",
    10:  "lavanderias",
    11:  "lavabos",
    93:  "halls",
    18:  "sala_jogos",
    21:  "dorm_funcionario",
    22:  "banheiro_funcionario",
    166: "escritorio",
    167: "despejo",
    104: "depositos",
    102: "recepcoes",
    103: "pe_direito",
    142: "topografia",
    12:  "garagem",
    13:  "garagem_coberta",
    159: "tipo_garagem",
    160: "obs_garagem",
    30:  "tipo_acabamento",
    179: "tipo_piso",
    629: "tipo_forro",
    99:  "est_conservacao",
    25:  "estado_conservacao",
    211: "obs_permuta",
    40:  "inst_financiamento",
    51:  "meses_restantes",
    50:  "valor_prestacao",
    49:  "saldo_devedor",
    123: "dist_asfalto",
    172: "medida_dist_asfalto",
    124: "dist_terra",
    173: "medida_dist_terra",
    141: "tipo_terra",
    122: "como_chegar",
    108: "agua",
    113: "caixa_agua",
    130: "lago",
    131: "lagoa",
    137: "poco_artesiano",
    138: "poco_cacimba",
    140: "represa",
    110: "baia",
    116: "canil",
    117: "capela",
    118: "casa_empregado",
    119: "casa_sede",
    125: "estabulo",
    127: "galpao",
    128: "granja",
    240: "mangueiro",
    136: "pocilga",
    111: "benfeitorias",
    134: "plantacao",
    135: "plantacao_outros",
    139: "pomar",
    143: "pomar_outros",
    24:  "padrao_acabamento",
    28:  "idade_imovel",
    34:  "isolamento",
    101: "isolamento_outros",
}

# Valores do sistema de origem que NÃO são características físicas do imóvel e devem ser
# ignorados antes do fuzzy matching.
#
# Categoria 1 — Proximidades/localização: indicam que o imóvel fica perto de algo,
#   não que o imóvel possui aquilo. Ex: "Bares e Restaurantes" → NÃO é "Restaurante".
#   "Próximo ao mar" bate em "Próximo ao metrô" (score 0.87) após remoção de acentos.
#
# Categoria 2 — Cômodos: nomes de aposentos do imóvel; tratados em campos próprios
#   (pr.cozinhas, pr.banheiros, etc.) e não devem ir para a coluna de características.
#   Exemplos de falsos positivos confirmados:
#     "Banheiro" → "Banheira" (0.88), "Quarto" → "Quadra" (0.67),
#     "Cozinha" → "Cortina" (0.71), "Copa" → "Coifa" (0.67),
#     "Sala" → "Sauna" (0.67), "Lavanderia" → "Academia" (0.67),
#     "Escritorio" → "Escritório virtual" (0.71)
#
# NÃO bloquear: "Sacada", "Varanda", "Sala de Estar", "Sala de Jantar", "Garagem" —
#   são características canônicas do Msys e o match é correto.
_SOURCE_BLOCKLIST: frozenset[str] = frozenset({
    # Proximidades / localização
    "bares e restaurantes",
    "restaurantes",
    "bares",
    "escola",
    "escolas",
    "farmacia",
    "farmacias",
    "supermercado",
    "supermercados",
    "banco",
    "bancos",
    "hospital",
    "hospitais",
    "padaria",
    "padarias",
    "posto de gasolina",
    "comercio",
    "shopping",
    "shopping center",
    "imovel central",
    "proximo ao mar",
    "proximo a praia",
    "beira-mar",
    "beira mar",
    "excelente localizacao",
    "regiao de moradores",
    # Cômodos (falsos positivos confirmados via fuzzy)
    "banheiro",
    "banheiros",
    "quarto",
    "quartos",
    "dormitorio",
    "dormitorios",
    "cozinha",
    "copa",
    "sala",
    "lavanderia",
    "escritorio",
    # Voltagem (dado técnico da instalação elétrica, não característica Msys)
    "voltagem 220v",
    "voltagem 110v 220v",
    "voltagem 110v / 220v",
    "voltagem 110v",
    "voltagem",
})

# Dicionário explícito inglês → português (para sistemas com nomes em inglês, ex: Imobzi)
_EN_PT: dict[str, str] = {
    "pool": "Piscina",
    "swimming pool": "Piscina",
    "fireplace": "Lareira",
    "gym": "Academia",
    "fitness": "Espaço Fitness",
    "elevator": "Elevador Social",
    "lift": "Elevador Social",
    "balcony": "Sacada",
    "terrace": "Varanda",
    "garden": "Jardim",
    "garage": "Garagem",
    "sauna": "Sauna",
    "barbecue": "Churrasqueiras",
    "grill": "Churrasqueiras",
    "playground": "Playground",
    "party room": "Salão de Festas",
    "party hall": "Salão de Festas",
    "sports court": "Quadra Poliesportiva",
    "tennis court": "Quadra de tênis",
    "squash court": "Quadra Poliesportiva",
    "24h security": "Portaria 24 Hrs",
    "security": "Portaria 24 Hrs",
    "intercom": "Interfone",
    "alarm": "Alarme",
    "generator": "Gerador",
    "jacuzzi": "Hidro",
    "hot tub": "Hidro",
    "furnished": "Mobília",
    "semi furnished": "Semi mobiliado",
    "semi-furnished": "Semi mobiliado",
    "closet": "Closet",
    "laundry": "Área de serviço",
    "storage": "Depósito",
    "bicycle": "Bicicletário",
    "bike rack": "Bicicletário",
    "electric gate": "Portão eletrônico",
    "gourmet balcony": "Varanda Gourmet",
    "sea view": "Vista mar",
    "ocean view": "Vista mar",
    "lake view": "Vista para o lago",
    "mountain view": "Vista para montanha",
    "cinema": "Cinema",
    "home theater": "Home theater",
    "wifi": "Wi-Fi",
    "internet": "Wi-Fi",
    "natural light": "Iluminação natural",
    "solar heating": "Aquecedor solar",
    "heating": "Aquecedor solar",
    "gated community": "Condomínio fechado",
    "concierge": "Portaria 24 Hrs",
    "electric fence": "Cerca elétrica",
    "cctv": "Monitoramento por câmeras",
    "camera": "Monitoramento por câmeras",
    "patio": "Quintal",
    "yard": "Quintal",
    "office": "Escritório",
    "pantry": "Despensa",
    "cellar": "Depósito",
}


def match_feature(name: str) -> str | None:
    """Retorna o nome canônico Msys correspondente ou None se não encontrado."""
    lower = name.lower().strip()
    norm_name = _norm(name)

    # 0. Mapeamento customizado do usuário (prioridade máxima)
    if norm_name in _custom:
        return _custom[norm_name]  # pode ser None (ignorar explicitamente)

    # 0b. Aliases de origem (variações conhecidas — Imobzi, etc.)
    if norm_name in _SOURCE_ALIASES:
        return _SOURCE_ALIASES[norm_name]

    # Rejeita valores de proximidade/localização antes de qualquer tentativa de match
    if norm_name in _SOURCE_BLOCKLIST:
        return None

    # 1. Exato case-insensitive
    if lower in _CANONICAL_LOWER:
        return _CANONICAL_LOWER[lower]

    # 2. Dicionário inglês→português
    pt = _EN_PT.get(lower)
    if pt and pt.lower() in _CANONICAL_LOWER:
        return _CANONICAL_LOWER[pt.lower()]

    # Correspondências aproximadas (fuzzy) NÃO são incluídas automaticamente.
    # Vão para o painel de revisão via scan_feature(), onde o usuário decide.
    return None


def scan_feature(name: str) -> dict:
    """Classifica como uma característica será tratada, sem aplicar mapeamento.

    Status possíveis:
      "custom"    — mapeamento salvo pelo usuário (canonical = str ou None)
      "ignored"   — na blocklist de proximidades/cômodos
      "field"     — campo de quantidade (flg_load_in_combobox=0)
      "matched"   — correspondência exata ou EN→PT
      "uncertain" — fuzzy match com score < 1.0 (suggested + score)
      "unmatched" — sem correspondência
    """
    lower = name.lower().strip()
    norm = _norm(name)

    if norm in _custom:
        return {"status": "custom", "canonical": _custom[norm]}

    # Aliases de origem (reconhecidos como "matched" — sem necessidade de revisão)
    if norm in _SOURCE_ALIASES:
        return {"status": "matched", "canonical": _SOURCE_ALIASES[norm]}

    if norm in _FIELD_MAP:
        return {"status": "field", "field": _FIELD_MAP[norm]}

    if norm in _SOURCE_BLOCKLIST:
        return {"status": "ignored"}

    if lower in _CANONICAL_LOWER:
        return {"status": "matched", "canonical": _CANONICAL_LOWER[lower]}

    pt = _EN_PT.get(lower)
    if pt and pt.lower() in _CANONICAL_LOWER:
        return {"status": "matched", "canonical": _CANONICAL_LOWER[pt.lower()]}

    m = difflib.get_close_matches(norm, _CANONICAL_NORM.keys(), n=1, cutoff=0.65)
    if m:
        score = difflib.SequenceMatcher(None, norm, m[0]).ratio()
        return {"status": "uncertain", "suggested": _CANONICAL_NORM[m[0]], "score": round(score, 2)}

    m2 = difflib.get_close_matches(lower, _CANONICAL_LOWER.keys(), n=1, cutoff=0.65)
    if m2:
        score = difflib.SequenceMatcher(None, lower, m2[0]).ratio()
        return {"status": "uncertain", "suggested": _CANONICAL_LOWER[m2[0]], "score": round(score, 2)}

    return {"status": "unmatched"}


def build_sim_nao(feature_names: list[str]) -> str:
    """Converte lista de nomes de features → string separada por vírgula para coluna DQ.

    Apenas características encontradas na lista canônica são incluídas.
    """
    if not feature_names:
        return ""
    seen: set[str] = set()
    result: list[str] = []
    for name in feature_names:
        canonical = match_feature(name)
        if canonical is not None and canonical not in seen:
            seen.add(canonical)
            result.append(canonical)
    return ",".join(result)


# ---------------------------------------------------------------------------
# Mapeamento de características (flg_load_in_combobox = 0) para campos do
# PropertyRecord. Chaves normalizadas (sem acento, minúsculo).
# ---------------------------------------------------------------------------
_FIELD_MAP: dict[str, str] = {
    # Dormitórios / quartos
    "dormitorio": "dormitorios",
    "dormitorios": "dormitorios",
    "quarto": "dormitorios",
    "quartos": "dormitorios",
    # Suítes
    "suite": "suites",
    "suites": "suites",
    "sendo dormitorios suites": "suites",
    # Banheiros
    "banheiro": "banheiros",
    "banheiros": "banheiros",
    # Closets
    "closet": "closets",
    "closets": "closets",
    # Copas
    "copa": "copas",
    "copas": "copas",
    # Cozinhas
    "cozinha": "cozinhas",
    "cozinhas": "cozinhas",
    # Despensas
    "despensa": "despensas",
    "despensas": "despensas",
    # Lavanderias
    "lavanderia": "lavanderias",
    "lavanderias": "lavanderias",
    # Lavabos
    "lavabo": "lavabos",
    "lavabos": "lavabos",
    # Halls
    "hall": "halls",
    "halls": "halls",
    # Sala de jogos / salão de jogos
    "sala de jogos": "sala_jogos",
    "salao de jogos": "sala_jogos",
    # Dormitório / banheiro de funcionário
    "dormitorio funcionario": "dorm_funcionario",
    "quarto de servico": "dorm_funcionario",
    "dep. empregada": "dorm_funcionario",
    "banheiro funcionario": "banheiro_funcionario",
    "w.c. de empregada": "banheiro_funcionario",
    # Escritório
    "escritorio": "escritorio",
    # Salas
    "sala": "salas",
    "salas": "salas",
    "sala de estar": "salas",
    # Despejo
    "despejo": "despejo",
    # Depósitos
    "deposito": "depositos",
    "depositos": "depositos",
    # Recepções
    "recepcao": "recepcoes",
    "recepcoes": "recepcoes",
}

_QTY_PREFIX = re.compile(r'^(\d+)\s*[xX]?\s+(.+)$')
_QTY_SUFFIX = re.compile(r'^(.+?)\s+(\d+)$')
_QTY_COLON  = re.compile(r'^(.+?):\s*(\d+)$')


def _extract_qty(text: str) -> tuple[str, int]:
    """Extrai (texto_sem_quantidade, quantidade) de strings como '3 Cozinhas' ou 'Cozinha'.

    Retorna quantidade=1 quando não há número explícito.
    """
    t = text.strip()
    m = _QTY_PREFIX.match(t)
    if m:
        return m.group(2).strip(), int(m.group(1))
    m = _QTY_COLON.match(t)
    if m:
        return m.group(1).strip(), int(m.group(2))
    m = _QTY_SUFFIX.match(t)
    if m:
        return m.group(1).strip(), int(m.group(2))
    return t, 1


def map_characteristics_to_fields(names: Iterable[str]) -> dict[str, str]:
    """Mapeia nomes de características (flg_load_in_combobox=0) para campos do PropertyRecord.

    Retorna dict {nome_campo: quantidade_str}. Para cada campo, a primeira ocorrência
    encontrada na lista prevalece. Quantidade padrão é "1" quando não há número no texto.
    """
    result: dict[str, str] = {}
    for raw in names:
        text, qty = _extract_qty(raw)
        lower = text.lower().strip()
        # Tenta tradução inglês→português antes de normalizar
        pt = _EN_PT.get(lower)
        key = _norm(pt if pt else text)
        field = _FIELD_MAP.get(key)
        if field and field not in result:
            result[field] = str(qty)
    return result


def map_characteristics_by_id(
    id_qty_pairs: Iterable[tuple[int, int | str]],
) -> dict[str, str]:
    """Mapeia pares (id_msys, quantidade) para campos do PropertyRecord.

    Para sistemas que fornecem IDs numéricos do Msys diretamente.
    Retorna dict {nome_campo: quantidade_str}.
    """
    result: dict[str, str] = {}
    for char_id, qty in id_qty_pairs:
        field = _ID_TO_FIELD.get(char_id)
        if field and field not in result:
            result[field] = str(qty)
    return result
