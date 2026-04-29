from __future__ import annotations
import html as _html
import re
import unicodedata
import xml.etree.ElementTree as ET
from datetime import date

from core.base_mapper import BaseMapper, ExtractionResult, PersonRecord, EmailRecord, PhoneRecord
from core.characteristics_utils import build_sim_nao, map_characteristics_to_fields
from core.phone_utils import processar_telefone
from core.property_records import (
    PropertyRecord, PropertyOwnerRecord, PropertyOwnerFavoredRecord,
    PropertyCaptivatorRecord, PropertyIptuRecord,
    PropertyExtractionResult, normalize_address,
)
from core.subcategorias import get_custom_subcat


# ── Helpers ───────────────────────────────────────────────────────────────────

def _txt(el: ET.Element | None, tag: str) -> str:
    if el is None:
        return ""
    found = el.find(tag)
    return (found.text or "").strip() if found is not None else ""


def _fmt(v) -> str:
    """Numeric → '180000.00', empty/zero → ''."""
    try:
        f = float(str(v or "").strip())
        return f"{f:.2f}" if f else ""
    except (ValueError, TypeError):
        return ""


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def _strip_html(v: str) -> str:
    v = re.sub(r"<[^>]+>", " ", v or "")
    v = _html.unescape(v)
    return re.sub(r"\s+", " ", v).strip()


# ── Subcategoria mapping ───────────────────────────────────────────────────────

# CATEGORIA ID → subcategoria ID Msys
_CAT_SUBCAT: dict[str, str] = {
    "49":  "22",   # Terreno em condomínio
    "51":  "10",   # Casa Vila & Condomínio
    "58":  "41",   # Galpão / Barracão
    "66":  "2",    # Cobertura
    "68":  "4",    # Kitnet / Studio
    "71":  "11",   # Andar | Conjuntos | Salas
    "77":  "28",   # Área para Incorporação
    "90":  "3",    # Flat
    "91":  "21",   # Terreno
    "95":  "16",   # Chácara | Sítio | Fazenda
    "97":  "25",   # Loja
    "98":  "1",    # Apartamento
    "100": "7",    # Casas | Sobrados | Prédios
    "101": "7",    # Casas & Sobrados
}

# TIPOINTERNO ID → subcategoria ID (fallback quando CATEGORIA não mapeada)
_TIPO_SUBCAT: dict[str, str] = {
    "1": "1",    # Apartamento → Padrão
    "2": "7",    # Casa → Padrão
    "3": "11",   # Comercial → Sala
    "4": "16",   # Rural → Chácara
    "5": "21",   # Terreno → Padrão
}


def _resolve_subcat(cat_id: str, tipo_id: str) -> str:
    """Custom override → _CAT_SUBCAT → _TIPO_SUBCAT → '7' (Casa Padrão)."""
    custom = get_custom_subcat(cat_id, tipo_id)
    if custom is not None:
        return custom
    return _CAT_SUBCAT.get(cat_id, _TIPO_SUBCAT.get(tipo_id, "7"))


# ── Mapper ────────────────────────────────────────────────────────────────────

class Code49Mapper(BaseMapper):
    NAME = "Code49"
    EXTENSIONS = [".xml"]
    DESCRIPTION = "Code49 (XML)"

    def can_handle(self, filename: str) -> bool:
        return filename.lower().endswith(".xml")

    def extract(self, root: ET.Element) -> ExtractionResult:
        result = ExtractionResult()

        # ── Lookup tables ─────────────────────────────────────────────────────

        cidades: dict[str, tuple[str, str]] = {}   # id → (nome, sigla)
        for c in root.findall(".//CIDADES/CIDADE"):
            cid = _txt(c, "ID") or _txt(c, "IDCIDADE")
            nome = _txt(c, "CIDADE")
            sigla = _txt(c, "SIGLA")
            if cid:
                cidades[cid] = (nome, sigla)

        bairros: dict[str, str] = {}               # id → nome
        for b in root.findall(".//BAIRROS/BAIRRO"):
            bid = _txt(b, "ID")
            nome = _txt(b, "BAIRRO")
            if bid:
                bairros[bid] = nome

        # cliente id → (cpf, cnpj, nome)
        clientes_info: dict[str, tuple[str, str, str]] = {}
        for cli in root.findall(".//CLIENTES/CLIENTE"):
            cid = _txt(cli, "ID")
            if cid:
                clientes_info[cid] = (
                    re.sub(r"\D", "", _txt(cli, "CPF")),
                    re.sub(r"\D", "", _txt(cli, "CNPJ")),
                    _txt(cli, "NOME"),
                )

        # Características: id → termo
        char_by_id: dict[str, str] = {}
        for c in root.findall(".//CARACTERISTICAS/DESCRICAO"):
            cid = _txt(c, "ID")
            termo = _txt(c, "TERMO")
            if cid and termo:
                char_by_id[cid] = termo

        # CARAC_IMOVEL: imovel_id → [termo, ...]
        imovel_chars: dict[str, list[str]] = {}
        for ic in root.findall(".//CARAC_IMOVEL/DESCRICAO"):
            imovel_id = _txt(ic, "ID_IMOVEL")
            char_id   = _txt(ic, "ID_CARACTERISTICA")
            if imovel_id and char_id and char_id in char_by_id:
                imovel_chars.setdefault(imovel_id, []).append(char_by_id[char_id])

        # Captadores: imovel_id → primeiro captador_id
        captivators_by_imovel: dict[str, str] = {}
        for cap in root.findall(".//CAPTADORESIMOVEL/DESCRICAO"):
            imovel_id   = _txt(cap, "IMOVEL")
            captador_id = _txt(cap, "CAPTADORES")
            if imovel_id and captador_id and imovel_id not in captivators_by_imovel:
                captivators_by_imovel[imovel_id] = captador_id

        # Proprietários de imóveis (para classificar tipo OW)
        imoveis_prop: set[str] = set()
        for im in root.findall(".//IMOVEIS/IMOVEL"):
            prop_id = _txt(im, "PROPRIETARIO")
            if prop_id:
                imoveis_prop.add(prop_id)

        # Emails e telefones por cliente
        emails_by_cli: dict[str, list[str]] = {}
        for em in root.findall(".//EMAILCLIENTE/EMAIL") or root.findall(".//EMAILCLIENTE"):
            cli_id = _txt(em, "IDCLIENTE") or _txt(em, "CLIENTE")
            email  = _txt(em, "EMAIL")     or _txt(em, "ENDERECO")
            if cli_id and email:
                emails_by_cli.setdefault(cli_id, []).append(email)

        fones_by_cli: dict[str, list[str]] = {}
        for tel in root.findall(".//TELEFONECLIENTE/TELEFONE") or root.findall(".//TELEFONECLIENTE"):
            cli_id = _txt(tel, "IDCLIENTE") or _txt(tel, "CLIENTE")
            numero = _txt(tel, "NUMERO")    or _txt(tel, "TELEFONE")
            if cli_id and numero:
                fones_by_cli.setdefault(cli_id, []).append(numero)

        # ── Pessoas ───────────────────────────────────────────────────────────

        seen: set[str] = set()
        for cli in root.findall(".//CLIENTES/CLIENTE"):
            cli_id = _txt(cli, "ID")
            if not cli_id:
                continue

            tipo = "OW" if cli_id in imoveis_prop else "BU"
            key  = f"{cli_id}|{tipo}"
            if key in seen:
                continue
            seen.add(key)

            cidade_id   = _txt(cli, "CIDADE")
            cidade_nome, cidade_uf = cidades.get(cidade_id, ("", ""))

            p = PersonRecord()
            p.codigo          = cli_id
            p.tipo            = tipo
            p.nome            = _txt(cli, "NOME")
            p.cpf             = re.sub(r"\D", "", _txt(cli, "CPF"))
            p.cnpj            = re.sub(r"\D", "", _txt(cli, "CNPJ"))
            p.rg              = _txt(cli, "RG")
            p.data_nascimento = _txt(cli, "DATANASCIMENTO") or _txt(cli, "NASCIMENTO")
            p.cep             = re.sub(r"\D", "", _txt(cli, "CEP"))
            p.cidade          = cidade_nome or _txt(cli, "NOMECIDADE")
            p.estado          = cidade_uf   or _txt(cli, "UF")
            p.bairro          = _txt(cli, "BAIRRO")
            p.endereco        = _txt(cli, "ENDERECO") or _txt(cli, "LOGRADOURO")
            p.numero          = _txt(cli, "NUMERO")
            p.complemento     = _txt(cli, "COMPLEMENTO")
            p.observacao      = _txt(cli, "OBSERVACAO") or _txt(cli, "OBS")
            result.persons.append(p)

            for raw in fones_by_cli.get(cli_id, []):
                parsed = processar_telefone(raw)
                if parsed:
                    result.phones.append(PhoneRecord(
                        codigo_pessoa=cli_id,
                        tipo_pessoa=tipo,
                        ddi=parsed["ddi"],
                        ddd=parsed["ddd"],
                        telefone=parsed["numero"],
                        tipo_telefone=parsed["tipo"],
                    ))

            for email in emails_by_cli.get(cli_id, []):
                result.emails.append(EmailRecord(
                    codigo_pessoa=cli_id,
                    tipo_pessoa=tipo,
                    email=email,
                    tipo_email="",
                ))

        result.property_result = self._extract_properties(
            root, cidades, bairros, clientes_info, imovel_chars, captivators_by_imovel,
        )
        return result

    # ── Scan hooks ────────────────────────────────────────────────────────────

    def scan_characteristics(self, data: ET.Element) -> set[str]:
        char_by_id: dict[str, str] = {}
        for c in data.findall(".//CARACTERISTICAS/DESCRICAO"):
            cid   = _txt(c, "ID")
            termo = _txt(c, "TERMO")
            if cid and termo:
                char_by_id[cid] = termo
        features: set[str] = set()
        for ic in data.findall(".//CARAC_IMOVEL/DESCRICAO"):
            char_id = _txt(ic, "ID_CARACTERISTICA")
            if char_id in char_by_id:
                features.add(char_by_id[char_id])
        return features

    def scan_subcategories(self, data: ET.Element) -> set[str]:
        """Retorna pares 'cat_id|tipo_id' sem mapeamento configurado."""
        pairs: set[str] = set()
        for im in data.findall(".//IMOVEIS/IMOVEL"):
            cat_id  = _txt(im, "CATEGORIA")
            tipo_id = _txt(im, "TIPOINTERNO")
            if _resolve_subcat(cat_id, tipo_id) == "":
                pairs.add(f"{cat_id}|{tipo_id}")
        return pairs

    # ── Property extraction ───────────────────────────────────────────────────

    def _extract_properties(
        self,
        root: ET.Element,
        cidades: dict[str, tuple[str, str]],
        bairros: dict[str, str],
        clientes_info: dict[str, tuple[str, str, str]],
        imovel_chars: dict[str, list[str]],
        captivators_by_imovel: dict[str, str],
    ) -> PropertyExtractionResult:
        prop_result = PropertyExtractionResult()

        imob_doc  = re.sub(r"\D", "", self.context.get("imob_cpf_cnpj", ""))
        imob_cpf  = imob_doc if len(imob_doc) == 11 else ""
        imob_cnpj = imob_doc if len(imob_doc) == 14 else ""
        imob_nome = self.context.get("imob_nome", "")

        for im in root.findall(".//IMOVEIS/IMOVEL"):
            imovel_id = _txt(im, "ID")
            if not imovel_id:
                continue

            # ── Status ───────────────────────────────────────────────────────
            status = "1" if _txt(im, "SITUACAO") == "1" else "5"

            # ── Tipo (departamento: S / L / SL) ──────────────────────────────
            transacoes = {
                (t.text or "").strip().upper()
                for t in im.findall("TRANSACOES/TRANSACAO")
            }
            sv_raw = _txt(im, "VALOR_VENDA")
            rv_raw = _txt(im, "VALOR_LOCACAO")
            try:
                sv = float(sv_raw) if sv_raw else 0.0
            except ValueError:
                sv = 0.0
            try:
                rv = float(rv_raw) if rv_raw else 0.0
            except ValueError:
                rv = 0.0
            has_venda = "VENDA"   in transacoes or sv > 0
            has_loc   = "LOCACAO" in transacoes or rv > 0
            tipo = "SL" if has_venda and has_loc else ("L" if has_loc else "S")

            # ── Subcategoria ─────────────────────────────────────────────────
            cat_id  = _txt(im, "CATEGORIA")
            tipo_id = _txt(im, "TIPOINTERNO")
            sub_cat = _resolve_subcat(cat_id, tipo_id)

            # ── Datas ────────────────────────────────────────────────────────
            data_raw = _txt(im, "DATA")
            data_registro = data_raw[:10] if data_raw else date.today().isoformat()

            # ── Finalidade ───────────────────────────────────────────────────
            finalidades = {
                (f.text or "").strip().upper()
                for f in im.findall("FINALIDADES/FINALIDADE")
            }
            if "RESIDENCIAL" in finalidades:
                finalidade = "Residencial"
            elif "INDUSTRIAL" in finalidades:
                finalidade = "Industrial"
            elif "COMERCIAL" in finalidades:
                finalidade = "Comercial"
            else:
                finalidade = ""

            # ── Endereço ─────────────────────────────────────────────────────
            cidade_id  = _txt(im, "IDCIDADE")
            bairro_id  = _txt(im, "IDBAIRRO")
            cidade_nome, cidade_sigla = cidades.get(cidade_id, ("", ""))
            bairro_nome = bairros.get(bairro_id, "")
            cep_raw = re.sub(r"\D", "", _txt(im, "CEP"))

            bairro_n, rua, numero_end, complemento = normalize_address(
                bairro_nome,
                _txt(im, "ENDERECO"),
                _txt(im, "NUMERO"),
                "",
            )

            # ── Áreas ────────────────────────────────────────────────────────
            au = _fmt(_txt(im, "AREAUTIL"))
            at = _fmt(_txt(im, "AREA"))
            ac = _fmt(_txt(im, "AREACONSTRUIDA"))

            # ── Garagem ──────────────────────────────────────────────────────
            garagem_total   = _txt(im, "GARAGEM")
            garagem_coberta = _txt(im, "GARAGEMCOBERTA")

            # ── Características ───────────────────────────────────────────────
            features = imovel_chars.get(imovel_id, [])

            # ── PropertyRecord ────────────────────────────────────────────────
            pr = PropertyRecord()
            pr.codigo         = imovel_id
            pr.imobiliaria    = "1"
            pr.status         = status
            pr.tipo           = tipo
            pr.sub_categoria  = sub_cat
            pr.data_registro  = data_registro
            pr.finalidade     = finalidade

            pr.valor_venda    = _fmt(sv_raw) if sv else ""
            pr.valor_locacao  = _fmt(rv_raw) if rv else ""
            pr.valor_condominio = _fmt(_txt(im, "VALOR_CONDOMINIO"))

            pr.titulo_site  = _nfc(_txt(im, "TITULO"))
            pr.obs_site     = _nfc(_strip_html(_txt(im, "CORPO")))
            pr.mostrar_site = "1" if _txt(im, "EXIBIRIMOVELSITE") == "1" else "0"
            pr.destaque     = "1" if _txt(im, "DESTAQUE") == "1" else "0"
            pr.street_view  = "1"
            pr.mapa_site    = "1"

            pr.cep        = cep_raw
            pr.cidade     = _nfc(cidade_nome)
            pr.estado     = cidade_sigla
            pr.bairro     = _nfc(bairro_n)
            pr.rua        = _nfc(rua)
            pr.numero_end = numero_end
            pr.complemento = _nfc(complemento)

            pr.dormitorios     = _txt(im, "DORMITORIO")
            pr.suites          = _txt(im, "SUITE")
            pr.banheiros       = _txt(im, "BANHEIRO")
            pr.lavabos         = "1" if _txt(im, "LAVABO") == "1" else ""
            pr.salas           = _txt(im, "SALAS")
            pr.garagem         = garagem_total or garagem_coberta
            pr.garagem_coberta = garagem_coberta
            pr.num_piso        = _txt(im, "NUMEROANDAR")
            pr.ano_construcao  = _txt(im, "ANO_CONSTRUCAO")
            pr.latitude        = _txt(im, "LATITUDE")
            pr.longitude       = _txt(im, "LONGITUDE")

            pr.area_util      = au or at
            pr.area_total     = at or au
            pr.area_construida = ac or au or at

            pr.caracteristicas_sim_nao = build_sim_nao(features)
            for fld, qty in map_characteristics_to_fields(features).items():
                if not getattr(pr, fld, ""):
                    setattr(pr, fld, qty)

            prop_result.properties.append(pr)

            # ── IPTU ─────────────────────────────────────────────────────────
            iptu_val = _fmt(_txt(im, "VALOR_IPTU"))
            if iptu_val:
                prop_result.iptu.append(PropertyIptuRecord(
                    codigo_imovel=imovel_id,
                    tipo_iptu="IPTU Principal",
                    inscricao_iptu="",
                    valor_mensal_iptu=iptu_val,
                    valor_anual_iptu="0",
                    parcelas_iptu="0",
                    perc_iptu="100",
                    obs_iptu="",
                ))

            # ── Proprietário ─────────────────────────────────────────────────
            prop_cli_id = _txt(im, "PROPRIETARIO")
            ow_cpf, ow_cnpj, ow_nome = clientes_info.get(prop_cli_id, ("", "", ""))
            if not ow_cpf and not ow_cnpj:
                ow_cpf  = imob_cpf
                ow_cnpj = imob_cnpj
                ow_nome = imob_nome

            prop_result.owners.append(PropertyOwnerRecord(
                codigo_imovel=imovel_id,
                cpf=ow_cpf,
                cnpj=ow_cnpj,
                codigo_pessoa=prop_cli_id or "",
                percentual="100",
            ))

            prop_result.owners_favored.append(PropertyOwnerFavoredRecord(
                codigo_imovel=imovel_id,
                cpf=ow_cpf,
                cnpj=ow_cnpj,
                codigo_pessoa=prop_cli_id or "",
                tipo_pagamento="M",
                percentual="100",
                cpf_favorecido=ow_cpf,
                cnpj_favorecido=ow_cnpj,
                id_favorecido=prop_cli_id or "",
                favorecido=ow_nome,
                banco="",
                agencia="",
                digito_agencia="",
                conta="",
                digito_conta="",
                poupanca="0",
            ))

            # ── Captivador — fallback imobiliária (USUARIOS sem CPF) ──────────
            if imob_doc:
                prop_result.captivators.append(PropertyCaptivatorRecord(
                    codigo_imovel=imovel_id,
                    cpf_cnpj=imob_doc,
                    departamento=tipo,
                    data_captacao="",
                ))

        return prop_result
