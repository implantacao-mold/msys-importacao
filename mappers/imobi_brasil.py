from __future__ import annotations
import datetime
import hashlib
import re
import xml.etree.ElementTree as ET
from typing import Any

from core.base_mapper import BaseMapper, ExtractionResult, PersonRecord, EmailRecord, PhoneRecord
from core.phone_utils import processar_telefone, is_valid_email
from core.cep_lookup import fill_city_state, is_valid_cep, lookup_cep_by_city
from core.characteristics_utils import build_sim_nao, map_characteristics_to_fields
from core.property_records import (
    PropertyExtractionResult,
    PropertyRecord,
    PropertyOwnerRecord,
    PropertyOwnerFavoredRecord,
    PropertyCaptivatorRecord,
    PropertyIptuRecord,
    normalize_address,
)


def _txt(el: ET.Element | None, tag: str) -> str:
    if el is None:
        return ""
    found = el.find(tag)
    return (found.text or "").strip() if found is not None else ""


def _md5(s: str) -> str:
    return hashlib.md5(s.encode("utf-8")).hexdigest()[:16].upper()


_SUBCATEGORIA: dict[str, str] = {
    # Apartamentos
    "Apartamento": "1",
    "Apartamento 1 Quarto": "1",
    "Apartamento 1 dormitório": "1",
    "Apartamento 2 dormitórios": "1",
    "Apartamento 3 dormitórios": "1",
    "Apartamento 4 ou + dormitórios": "1",
    "Apartamento com Área Privativa": "54",
    "APARTAMENTO NA PLANTA": "1",
    "Apartamento Garden": "43",
    "Apartamento Duplex": "5",
    "Apartamento Triplex": "6",
    "Apartamento Studio": "46",
    "Cobertura Duplex": "65",
    "Cobertura Penthouse": "2",
    "Cobertura": "2",
    "Duplex": "5",
    "Triplex": "6",
    "Studio": "46",
    "Flat": "3",
    "Kitnet": "4",
    "Loft": "33",
    # Casas
    "Casa": "7",
    "Casa 1 dormitório": "7",
    "Casa 2 dormitórios": "7",
    "Casa 3 dormitórios": "7",
    "Casa 4 ou + dormitórios": "7",
    "Casa Rural": "7",
    "Casa Geminada": "66",
    "Casa / Sobrado": "8",
    "Casa em Condomínio": "10",
    "Casa Comercial": "0",
    "Casas de Vila": "7",
    "Residencial e Comercial": "7",
    "Temporada": "7",
    "Imóveis Vendidos": "7",
    "Pré-Lançamento": "7",
    "Sobrado": "8",
    "Sobrado Geminado": "8",
    "Sobrado em Condomínio": "40",
    "Sobrado Condomínio": "40",
    "Village": "10",
    "Townhouse": "36",
    "Pousada": "38",
    "Chalé": "47",
    "EDÍCULA": "9",
    "Edícula": "9",
    # Comercial
    "Imóvel Comercial": "0",
    "Comércios": "31",
    "Comercial": "31",
    "Ponto Comercial": "31",
    "Sala Comercial": "11",
    "Sala Comercial/Usada": "11",
    "Escritório": "11",
    "Salão Comercial": "12",
    "Prédio Comercial": "14",
    "Loja": "25",
    "Galpão": "41",
    "Galpão / Barracão": "41",
    "Barracão": "41",
    "Pavilhão": "62",
    # Rural
    "Área Rural": "18",
    "Chácara": "16",
    "Sítio": "19",
    "Sítio / Chácara": "19",
    "Fazenda": "17",
    "Rancho": "29",
    # Terreno
    "Terreno": "21",
    "Terreno Residencial": "26",
    "Terreno em Condomínio": "22",
    "Lote": "23",
    "Área": "28",
    # Industrial
    "Área Industrial": "45",
}

# Regras de inferência por palavras-chave (ordem importa: mais específico primeiro)
_SUBCATEGORIA_KEYWORDS: list[tuple[str, str]] = [
    ("COBERTURA DUPLEX",  "65"),
    ("COBERTURA",         "2"),
    ("APARTAMENTO",       "1"),
    ("APTO",              "1"),
    ("KITNET",            "4"),
    ("KIT NET",           "4"),
    ("DUPLEX",            "5"),
    ("TRIPLEX",           "6"),
    ("STUDIO",            "46"),
    ("LOFT",              "33"),
    ("FLAT",              "3"),
    ("SOBRADO CONDOMÍNIO","40"),
    ("SOBRADO CONDOMINIO","40"),
    ("SOBRADO",           "8"),
    ("EDÍCULA",           "9"),
    ("EDICULA",           "9"),
    ("CONDOMÍNIO",        "10"),
    ("CONDOMINIO",        "10"),
    ("GEMINADA",          "66"),
    ("PAVILHÃO",          "62"),
    ("PAVILHAO",          "62"),
    ("PRÉDIO",            "14"),
    ("PREDIO",            "14"),
    ("SALÃO",             "12"),
    ("SALAO",             "12"),
    ("SALA",              "11"),
    ("ESCRITÓRIO",        "11"),
    ("ESCRITORIO",        "11"),
    ("LOJA",              "25"),
    ("GALPÃO",            "41"),
    ("GALPAO",            "41"),
    ("BARRACÃO",          "41"),
    ("BARRACAO",          "41"),
    ("POUSADA",           "38"),
    ("TOWNHOUSE",         "36"),
    ("CHALÉ",             "47"),
    ("CHALE",             "47"),
    ("CHÁCARA",           "16"),
    ("CHACARA",           "16"),
    ("FAZENDA",           "17"),
    ("SÍTIO",             "19"),
    ("SITIO",             "19"),
    ("RANCHO",            "29"),
    ("ÁREA RURAL",        "18"),
    ("AREA RURAL",        "18"),
    ("RURAL",             "7"),
    ("TERRENO",           "21"),
    ("LOTE",              "23"),
    ("ÁREA",              "28"),
    ("AREA",              "28"),
    ("COMERCIAL",         "11"),
    ("CASA",              "7"),
]


def _subcategoria(subtipo: str, tipoimovel: str = "") -> str:
    # 1. Match exato
    result = _SUBCATEGORIA.get(subtipo)
    if result is not None:
        return result
    # 2. Inferência por palavra-chave no subtipo
    upper = subtipo.upper()
    for keyword, code in _SUBCATEGORIA_KEYWORDS:
        if keyword in upper:
            return code
    # 3. Fallback para tipoimovel
    result = _SUBCATEGORIA.get(tipoimovel)
    if result is not None:
        return result
    upper_tipo = tipoimovel.upper()
    for keyword, code in _SUBCATEGORIA_KEYWORDS:
        if keyword in upper_tipo:
            return code
    return "7"


def _parse_date(s: str) -> str:
    """Converte data para dd/mm/yyyy, usando data atual se vazia."""
    if not s:
        return datetime.date.today().strftime("%d/%m/%Y")
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y"):
        try:
            return datetime.datetime.strptime(s, fmt).strftime("%d/%m/%Y")
        except ValueError:
            continue
    return datetime.date.today().strftime("%d/%m/%Y")


def _fmt_area(s: str) -> str:
    """Normaliza número de área (substitui vírgula, formata 2 casas)."""
    s = s.replace(",", ".")
    try:
        return f"{float(s):.2f}" if s else ""
    except ValueError:
        return s


def _fmt_valor(s: str) -> str:
    """Arredonda valor monetário para 2 casas."""
    s = s.replace(",", ".")
    try:
        return f"{round(float(s), 2):.2f}" if s else ""
    except ValueError:
        return s


_BOOL_CARACS: dict[str, str] = {
    "mobiliado":           "Mobiliado",
    "em_condominio":       "Condomínio fechado",
    "aceitafinanciamento": "Aceita financiamento",
}


def _caracs(imovel: ET.Element) -> set[str]:
    """Retorna conjunto de características (texto em maiúsculas, sem aspas simples do CDATA)."""
    result: set[str] = set()
    caracs_el = imovel.find("caracteristicas")
    if caracs_el is not None:
        for child in caracs_el:
            txt = (child.text or "").strip().strip("'").strip().upper()
            if txt:
                result.add(txt)
    for tag, nome in _BOOL_CARACS.items():
        if _txt(imovel, tag).strip().upper() in ("SIM", "S", "1", "YES", "TRUE"):
            result.add(nome.upper())
    return result


def _parse_person(
    node: ET.Element,
    tipo: str,
    result: ExtractionResult,
    seen: set[str],
) -> tuple[str, str] | None:
    """Extrai pessoa de <proprietario> ou <corretor>. Retorna (codigo, cpf) ou None."""
    nome = _txt(node, "nome")
    if not nome:
        return None

    tels_raw = [_txt(node, "telefone1"), _txt(node, "telefone2"), _txt(node, "telefone3")]
    phones_parsed: list[dict] = []
    first_digits = ""
    for raw in tels_raw:
        if not raw:
            continue
        parsed = processar_telefone(raw)
        if parsed:
            phones_parsed.append(parsed)
            if not first_digits:
                first_digits = parsed["ddd"] + parsed["numero"]

    codigo = _md5(nome.upper() + first_digits)
    key = f"{codigo}|{tipo}"
    if key in seen:
        return (codigo, re.sub(r"\D", "", _txt(node, "cpf")), nome)
    seen.add(key)

    cpf = re.sub(r"\D", "", _txt(node, "cpf"))
    if tipo == "EM" and not cpf:
        return None
    p = PersonRecord()
    p.codigo = codigo
    p.tipo = tipo
    p.nome = nome
    p.cpf = cpf
    result.persons.append(p)

    for ph in phones_parsed:
        result.phones.append(PhoneRecord(
            codigo_pessoa=codigo,
            tipo_pessoa=tipo,
            ddi=ph["ddi"],
            ddd=ph["ddd"],
            telefone=ph["numero"],
            tipo_telefone=ph["tipo"],
        ))

    email = _txt(node, "email")
    if is_valid_email(email):
        result.emails.append(EmailRecord(
            codigo_pessoa=codigo,
            tipo_pessoa=tipo,
            email=email,
            tipo_email="",
        ))

    return (codigo, cpf, nome)


def _extract_property(
    imovel: ET.Element,
    owner_codigo: str,
    owner_nome: str,
    prop_result: PropertyExtractionResult,
    imob_cpf_cnpj: str = "",
    imob_nome: str = "",
) -> None:
    ref = _txt(imovel, "ref")
    if not ref:
        return
    try:
        codigo = str(int(ref))
    except ValueError:
        codigo = ref

    transacao = _txt(imovel, "transacao")
    status_raw = _txt(imovel, "imovel_status").upper()
    valor_raw = _fmt_valor(_txt(imovel, "valor"))

    comp_parts = [_txt(imovel, "endereco_complemento")]
    emp = _txt(imovel, "empreendimento_nome")
    if emp:
        comp_parts.append(f"Empreendimento: {emp}")
    cond_nome = _txt(imovel, "endereco_nome_condominio")
    if cond_nome:
        comp_parts.append(f"Cond.: {cond_nome}")
    complemento = " ".join(p for p in comp_parts if p)

    area_constr_raw = _txt(imovel, "area_construida")
    area_total_raw = _txt(imovel, "area_total") or _txt(imovel, "area_terreno")

    iptu_raw = _fmt_valor(_txt(imovel, "valor_iptu"))

    caracs = _caracs(imovel)

    pr = PropertyRecord()
    pr.codigo = codigo
    pr.data_registro = _parse_date(_txt(imovel, "data_cadastro"))
    pr.imobiliaria = "1"
    pr.status = "5" if status_raw == "INATIVO" else "1"
    pr.tipo = "S" if transacao == "Venda" else "L"
    pr.sub_categoria = _subcategoria(_txt(imovel, "subtipoimovel"), _txt(imovel, "tipoimovel"))
    pr.valor_venda = valor_raw if transacao == "Venda" else ""
    pr.valor_locacao = valor_raw if transacao != "Venda" else ""
    pr.mostrar_site = "1"
    pr.destaque = "1" if _txt(imovel, "destacado").upper() == "SIM" else "0"
    pr.street_view = "1"
    pr.mapa_site = "1"
    pr.url_video = _txt(imovel, "video")
    pr.valor_anual_iptu = iptu_raw
    pr.valor_mensal_iptu = iptu_raw
    pr.perc_iptu = "100"
    pr.cep = re.sub(r"\D", "", _txt(imovel, "endereco_cep"))
    pr.cidade = _txt(imovel, "endereco_cidade")
    pr.estado = _txt(imovel, "endereco_estado")
    pr.cidade, pr.estado = fill_city_state(pr.cep, pr.cidade, pr.estado)
    if not is_valid_cep(pr.cep) and pr.cidade and pr.estado:
        pr.cep = lookup_cep_by_city(pr.cidade, pr.estado) or ""
    pr.bairro, pr.rua, pr.numero_end, complemento = normalize_address(
        _txt(imovel, "endereco_bairro"),
        _txt(imovel, "endereco_logradouro"),
        _txt(imovel, "endereco_numero"),
        complemento,
    )
    pr.complemento = complemento
    pr.lado1 = "0"
    pr.lado2 = "0"
    pr.lado3 = "0"
    pr.lado4 = "0"
    pr.dormitorios = _txt(imovel, "dormitorios")
    pr.banheiros = _txt(imovel, "banheiro")
    pr.area_util = _fmt_area(area_constr_raw)
    pr.area_total = _fmt_area(area_total_raw)
    pr.area_construida = _fmt_area(area_constr_raw)
    pr.suites = _txt(imovel, "suites")
    pr.garagem = _txt(imovel, "vagas")

    # Aplica campos de quantidade vindos das características (flg_load_in_combobox=0).
    # Campos já preenchidos por tags XML dedicadas não são sobrescritos.
    for field, qty in map_characteristics_to_fields(caracs).items():
        if not getattr(pr, field, ""):
            setattr(pr, field, qty)
    pr.caracteristicas_sim_nao = build_sim_nao(list(caracs))
    pr.ponto_referencia = _txt(imovel, "endereco_pontoreferencia")
    pr.valor_condominio = _fmt_valor(_txt(imovel, "valor_condominio"))
    pr.titulo_site = _txt(imovel, "titulo")
    pr.ano_construcao = _txt(imovel, "ano_construcao")

    obs_parts = [f"Ref: {codigo}"]
    if pr.valor_condominio:
        obs_parts.append(f"Valor cond.: {pr.valor_condominio}")
    pr.observacao = " ".join(obs_parts)
    pr.obs_site = _txt(imovel, "descricao")

    tipo_prop = pr.tipo

    prop_result.properties.append(pr)

    imob_doc = re.sub(r"\D", "", imob_cpf_cnpj)
    if owner_codigo:
        ow_cpf  = ""
        ow_cnpj = ""
    else:
        ow_cpf  = ""
        ow_cnpj = imob_doc
    ow_nome = imob_nome if not owner_codigo else owner_nome

    prop_result.captivators.append(PropertyCaptivatorRecord(
        codigo_imovel=codigo,
        cpf_cnpj=imob_doc,
        departamento=tipo_prop,
        data_captacao=datetime.date.today().strftime("%d/%m/%Y"),
    ))

    prop_result.owners.append(PropertyOwnerRecord(
        codigo_imovel=codigo,
        cpf=ow_cpf,
        cnpj=ow_cnpj,
        codigo_pessoa=owner_codigo,
        percentual="100",
    ))

    prop_result.owners_favored.append(PropertyOwnerFavoredRecord(
        codigo_imovel=codigo,
        cpf=ow_cpf,
        cnpj=ow_cnpj,
        codigo_pessoa=owner_codigo,
        tipo_pagamento="M",
        percentual="100",
        cpf_favorecido=ow_cpf,
        cnpj_favorecido=ow_cnpj,
        id_favorecido=owner_codigo,
        favorecido=ow_nome,
    ))

    if iptu_raw:
        prop_result.iptu.append(PropertyIptuRecord(
            codigo_imovel=codigo,
            tipo_iptu="IPTU Principal",
            inscricao_iptu="",
            valor_anual_iptu=iptu_raw,
            valor_mensal_iptu=iptu_raw,
            parcelas_iptu="",
            perc_iptu="100",
            obs_iptu="",
        ))


class ImobiBrasilMapper(BaseMapper):
    NAME = "Imobi Brasil"
    EXTENSIONS = [".xml"]
    DESCRIPTION = "Imobi Brasil (XML)"

    def can_handle(self, filename: str) -> bool:
        return filename.lower().endswith(".xml")

    def extract(self, root: ET.Element) -> ExtractionResult:
        result = ExtractionResult()
        result.property_result = PropertyExtractionResult()
        seen: set[str] = set()
        imob_cpf_cnpj = self.context.get("imob_cpf_cnpj", "")
        imob_nome = self.context.get("imob_nome", "")

        for imovel in root.findall(".//imovel"):
            owner_codigo = ""
            owner_nome = ""

            prop_node = imovel.find("proprietario")
            if prop_node is not None:
                info = _parse_person(prop_node, "OW", result, seen)
                if info:
                    owner_codigo, _, owner_nome = info

            corretor_node = imovel.find("corretor")
            if corretor_node is not None:
                _parse_person(corretor_node, "EM", result, seen)

            _extract_property(imovel, owner_codigo, owner_nome, result.property_result,
                               imob_cpf_cnpj, imob_nome)

        return result

    def scan_characteristics(self, data: ET.Element) -> set[str]:
        result: set[str] = set()
        for imovel in data.iter("imovel"):
            result.update(_caracs(imovel))
        return result
