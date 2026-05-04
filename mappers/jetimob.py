from __future__ import annotations
import json
import re
import unicodedata
from typing import Any

from core.base_mapper import BaseMapper, ExtractionResult, PersonRecord, EmailRecord, PhoneRecord
from core.characteristics_utils import build_sim_nao, map_characteristics_to_fields
from core.phone_utils import processar_telefone, is_valid_email
from core.property_records import (
    PropertyExtractionResult, PropertyRecord, PropertyOwnerRecord,
    PropertyOwnerFavoredRecord, PropertyCaptivatorRecord, PropertyIptuRecord,
    normalize_address,
)


# ── Constants ─────────────────────────────────────────────────────────────────

_TIPO_SUBCAT: dict[str, str] = {
    "Apartamento": "1",
    "Apartamento Garden": "43",
    "Box": "15",
    "Campo": "18",
    "Casa": "7",
    "Casa Comercial": "0",
    "Casa de Condomínio": "10",
    "Chácara": "16",
    "Cobertura": "2",
    "Conjunto Comercial": "11",
    "Duplex": "5",
    "Flat": "3",
    "Fazenda": "17",
    "Galpão": "41",
    "Geminado": "66",
    "Kitnet": "4",
    "Loja": "25",
    "Ponto Comercial": "31",
    "Pousada": "38",
    "Prédio Comercial": "14",
    "Prédio Residencial": "1",
    "Sala Comercial": "11",
    "Salão comercial": "12",
    "Sobrado": "8",
    "Studio": "46",
    "Sítio": "19",
    "Área Rural": "28",
    "Terreno": "21",
    "Terreno Comercial": "27",
}

_COMODIDADES_MAP: dict[str, str] = {
    "Acessibilidade para PCD": "Acesso para deficientes",
    "Adega": "Adega",
    "Alarme": "Alarme",
    "Aquecimento solar": "Aquecedor solar",
    "Ar condicionado": "Ar-condicionado",
    "Armário cozinha": "Armários na Cozinha",
    "Armário embutido": "Armário embutido",
    "Cerca elétrica": "Cerca elétrica",
    "Churrasqueira": "Churrasqueira",
    "Circuito TV": "Circuito de televisão",
    "Cozinha grande": "Cozinha grande",
    "Edícula": "Edícula",
    "Elevador": "Elevadores",
    "Espaço gourmet": "Espaço Gourmet",
    "Home office": "Home office",
    "Interfone": "Interfone",
    "Jardim": "Jardim",
    "Móveis planejados": "Móveis Planejados",
    "Piscina": "Piscina",
    "Portão eletrônico": "Portão eletrônico",
    "Quintal": "Quintal",
    "Sacada": "Sacada",
    "Sala de estar": "Sala de estar",
    "Sala de jantar": "Sala de jantar",
    "Vídeo monitoramento": "Monitoramento por câmeras",
    "Área de serviço": "Área de serviço",
    "Varanda": "Varanda",
    "Acesso asfaltado": "Asfalto",
    "Estacionamento": "Estacionamento rotativo",
    "Canil": "Canil",
    "Cozinha gourmet": "Espaço Gourmet",
    "Varanda gourmet": "Varanda Gourmet",
    "Deck": "Deck",
    "Energia solar": "Aquecedor solar",
    "Fechadura digital": "Fechadura digital",
    "Portăo eletrônico": "Portão eletrônico",  # typo in source data
}


# ── Module-level helpers ───────────────────────────────────────────────────────

def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s) if s else ""


def _ascii_lower(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()


def _v(row: dict, *keys: str) -> str:
    """Return first non-empty value matching any of the given keys."""
    for k in keys:
        v = row.get(k)
        if v is not None:
            s = str(v).strip()
            if s and s.lower() not in ("none", "nan"):
                return s
    return ""


def _fmt_brl(v: Any) -> str:
    """'R$  1.500,00' → '1500.00'; zero/None → ''."""
    s = re.sub(r"[R$\s]", "", str(v or "").strip())
    s = s.replace(".", "").replace(",", ".")
    try:
        f = float(s)
        return f"{f:.2f}" if f else ""
    except (ValueError, TypeError):
        return ""


def _fmt_val(v: Any) -> str:
    """Float/str numeric → '123.45'; zero/None → ''."""
    try:
        f = float(str(v or "").replace(",", "."))
        return f"{f:.2f}" if f else ""
    except (ValueError, TypeError):
        return ""


def _fmt_centavos(v: Any) -> str:
    """Value stored in centavos → '123.45'; zero/None → ''."""
    try:
        f = float(str(v or "").replace(",", "."))
        return f"{f / 100:.2f}" if f else ""
    except (ValueError, TypeError):
        return ""


def _parse_comodidades(v: Any) -> list[str]:
    """JSON string '["Piscina","Churrasqueira"]' → list of strings."""
    if not v or str(v).strip().lower() in ("none", "nan", ""):
        return []
    try:
        result = json.loads(str(v))
        if isinstance(result, list):
            return [str(x).strip() for x in result if x]
    except (json.JSONDecodeError, ValueError):
        pass
    return []


def _parse_ids(v: Any) -> list[str]:
    """'[id1,id2,id3]' → ['id1','id2','id3'] (any number of IDs)."""
    s = str(v or "").strip().strip("[]")
    if not s or s.lower() in ("none", "nan"):
        return []
    return [x.strip() for x in s.split(",") if x.strip()]


def _parse_json_list(v: Any, key: str) -> list[str]:
    """[{"telefone": "+55..."}, ...] → list of values for the given key."""
    if not v or str(v).strip().lower() in ("none", "nan", ""):
        return []
    try:
        items = json.loads(str(v))
        if isinstance(items, list):
            return [
                str(item[key]).strip()
                for item in items
                if isinstance(item, dict) and item.get(key)
            ]
    except (json.JSONDecodeError, ValueError, KeyError):
        pass
    return []


def _find_sheet(sheets: dict, *names: str) -> list[dict]:
    """Find a sheet by normalized name (no accents, case-insensitive).
    Falls back to partial match if exact not found.
    """
    target_names = {_ascii_lower(n) for n in names}
    for k in sheets:
        if _ascii_lower(k) in target_names:
            return sheets[k]
    # Partial match fallback
    for n in names:
        needle = _ascii_lower(n)
        for k in sheets:
            if needle in _ascii_lower(k):
                return sheets[k]
    return []


def _first_nonzero(*values: str) -> str:
    """Return first non-empty, non-zero formatted value."""
    for v in values:
        if not v:
            continue
        try:
            if float(v):
                return v
        except (ValueError, TypeError):
            if v:
                return v
    return ""


# ── Mapper ────────────────────────────────────────────────────────────────────

class JetImobMapper(BaseMapper):
    NAME = "JetImob"
    EXTENSIONS = [".xlsx"]
    DESCRIPTION = "JetImob (XLSX)"

    def extract(self, data: Any) -> ExtractionResult:
        result = ExtractionResult()

        if not isinstance(data, dict):
            return result

        sheets: dict[str, list[dict]] = data

        imoveis_rows = _find_sheet(sheets, "Imóveis", "Imoveis", "Imóvel", "Imovel")
        pessoas_rows = _find_sheet(sheets, "Pessoas", "Pessoa")
        contratos_rows = _find_sheet(sheets, "Contratos", "Contrato")
        beneficiarios_rows = _find_sheet(sheets, "Beneficiários", "Beneficiarios", "Beneficiario")

        self._extract_pessoas(imoveis_rows, pessoas_rows, result)
        result.property_result = self._extract_properties(
            imoveis_rows, pessoas_rows, contratos_rows, beneficiarios_rows
        )

        return result

    # ── Persons ───────────────────────────────────────────────────────────────

    def _extract_pessoas(
        self,
        imoveis_rows: list[dict],
        pessoas_rows: list[dict],
        result: ExtractionResult,
    ) -> None:
        # Build set of all owner person_ids referenced by any imóvel
        owner_ids: set[str] = set()
        for row in imoveis_rows:
            for oid in _parse_ids(_v(row, "id_proprietarios")):
                owner_ids.add(oid)

        seen: set[str] = set()

        for row in pessoas_rows:
            person_id = _v(row, "person_id")
            nome = _nfc(_v(row, "nome"))
            if not nome:
                continue

            tipo = "OW" if person_id in owner_ids else "BU"
            key = f"{person_id}|{tipo}"
            if key in seen:
                continue
            seen.add(key)

            # Documento — stored as integer (float) in XLSX
            doc_raw = _v(row, "documento")
            if doc_raw:
                try:
                    doc = re.sub(r"\D", "", str(int(float(doc_raw))))
                except (ValueError, TypeError):
                    doc = re.sub(r"\D", "", doc_raw)
            else:
                doc = ""

            cpf = doc if len(doc) == 11 else ""
            cnpj = doc if len(doc) == 14 else ""

            # Phones from JSON array: [{"telefone": "+5531..."}]
            phones_parsed: list[dict] = []
            for tel in _parse_json_list(_v(row, "telefones"), "telefone"):
                digits = re.sub(r"\D", "", tel)
                if digits.startswith("55") and len(digits) > 11:
                    digits = digits[2:]
                parsed = processar_telefone(digits)
                if parsed:
                    phones_parsed.append(parsed)

            # Emails from JSON array: [{"email": "x@y.z"}]
            email_values = _parse_json_list(_v(row, "emails"), "email")

            # Address from JSON array: [{"cep": "...", "rua": "...", ...}]
            p_cep = p_rua = p_numero = p_complemento = p_bairro = p_cidade = p_estado = ""
            end_raw = _v(row, "endereco")
            if end_raw:
                try:
                    end_items = json.loads(end_raw)
                    if isinstance(end_items, list) and end_items and isinstance(end_items[0], dict):
                        end = end_items[0]
                        cep_digits = re.sub(r"\D", "", str(end.get("cep", "") or ""))
                        p_cep = cep_digits.zfill(8) if cep_digits else ""
                        p_rua = _nfc(str(end.get("rua", "") or "").strip())
                        p_numero = str(end.get("numero", "") or "").strip()
                        p_complemento = _nfc(str(end.get("complemento", "") or "").strip())
                        p_bairro = _nfc(str(end.get("bairro", "") or "").strip())
                        p_cidade = _nfc(str(end.get("cidade", "") or "").strip())
                        p_estado = str(end.get("estado", "") or "").strip()
                except (json.JSONDecodeError, ValueError):
                    pass

            # Gênero: source values are 'M', 'F', None
            genero_raw = _v(row, "genero")
            if genero_raw.upper() == "F":
                sexo = "F"
            elif genero_raw:
                sexo = "M"
            else:
                sexo = ""

            p = PersonRecord()
            p.codigo = person_id
            p.tipo = tipo
            p.nome = nome
            p.nome_fantasia = nome
            p.cpf = cpf
            p.cnpj = cnpj
            p.rg = _v(row, "rg")
            p.data_nascimento = _v(row, "data_nascimento", "nascimento")
            p.sexo = sexo
            p.estado_civil = _nfc(_v(row, "estado_civil"))
            p.profissao = _nfc(_v(row, "profissao", "profissão"))
            p.nacionalidade = _nfc(_v(row, "nacionalidade"))
            p.observacao = _nfc(_v(row, "observacao", "observação"))
            p.imobiliaria = "1"
            p.cobrar_taxa_bco = "0"
            p.cep = p_cep
            p.bairro = p_bairro
            p.cidade = p_cidade
            p.estado = p_estado
            p.endereco = p_rua
            p.numero = p_numero
            p.complemento = p_complemento

            result.persons.append(p)

            for ph in phones_parsed:
                result.phones.append(PhoneRecord(
                    codigo_pessoa=person_id,
                    tipo_pessoa=tipo,
                    ddi=ph["ddi"],
                    ddd=ph["ddd"],
                    telefone=ph["numero"],
                    tipo_telefone=ph["tipo"],
                ))

            for email in email_values:
                if is_valid_email(email):
                    result.emails.append(EmailRecord(
                        codigo_pessoa=person_id,
                        tipo_pessoa=tipo,
                        email=email,
                        tipo_email="",
                    ))

    # ── Properties ────────────────────────────────────────────────────────────

    def _extract_properties(
        self,
        imoveis: list[dict],
        pessoas_rows: list[dict],
        contratos: list[dict],
        beneficiarios: list[dict],
    ) -> PropertyExtractionResult:
        prop_result = PropertyExtractionResult()

        imob_doc = re.sub(r"\D", "", self.context.get("imob_cpf_cnpj", ""))
        imob_nome = self.context.get("imob_nome", "")

        # Build pessoa lookup by person_id
        pessoa_by_id: dict[str, dict] = {}
        for row in pessoas_rows:
            pid = _v(row, "person_id")
            if pid:
                pessoa_by_id[pid] = row

        # Build set of imóvel codes that have contracts
        imoveis_com_contrato: set[str] = set()
        for row in contratos:
            cod = _v(row, "codigo_imovel", "imovel_codigo", "id_imovel", "imovel_id", "codigo")
            if cod:
                imoveis_com_contrato.add(cod)

        # Build beneficiário lookup by nome (for banking data)
        benef_by_nome: dict[str, dict] = {}
        for row in beneficiarios:
            nome = _v(row, "nome")
            if nome:
                benef_by_nome[nome] = row

        for row in imoveis:
            codigo = _v(row, "codigo")
            if not codigo:
                continue

            # Data registro — use first 10 chars of criado_em timestamp
            criado_em = _v(row, "criado_em")
            data_registro = str(criado_em)[:10] if criado_em else ""

            # Status — active when any of the status fields = "Disponível para negociação"
            sv = _v(row, "status_venda")
            sl = _v(row, "status_locacao")
            status = "1" if (
                sv == "Disponível para negociação" or sl == "Disponível para negociação"
            ) else "5"

            # Tipo S / L / SL
            is_venda = _v(row, "venda") == "Sim"
            is_locacao = _v(row, "locacao") == "Sim"
            has_contrato = codigo in imoveis_com_contrato
            if is_venda and is_locacao:
                tipo = "SL"
            elif is_venda and has_contrato:
                tipo = "SL"
            elif is_venda:
                tipo = "S"
            else:
                tipo = "L"

            # Subcategoria
            tipo_imovel = _v(row, "tipo")
            sub_categoria = _TIPO_SUBCAT.get(tipo_imovel, "7")

            # Valores monetários (BRL string format)
            valor_venda = _fmt_brl(_v(row, "valor_venda"))
            valor_locacao = _fmt_brl(_v(row, "valor_locacao"))

            # Ocupação / exclusividade
            ocupado = "1" if _v(row, "ocupacao") == "Ocupado" else "0"
            excl = _v(row, "exclusividade")
            venda_exclusiva = "1" if (excl == "Sim" and is_venda) else "0"
            locacao_exclusiva = "1" if (excl == "Sim" and is_locacao) else "0"

            # Observação
            obs_parts: list[str] = [f"Ref: {codigo}"]
            desc_interna = _v(row, "descricao_interna", "descricao", "observacao")
            if desc_interna:
                obs_parts.append(desc_interna)
            condicao = _v(row, "condicao", "condição")
            if condicao:
                obs_parts.append(f"Condição: {condicao}")
            ocupacao_obs = _v(row, "ocupacao")
            if ocupacao_obs:
                obs_parts.append(f"Ocupação: {ocupacao_obs}")
            portais = _v(row, "portais")
            if portais:
                obs_parts.append(f"Portais: {portais}")
            observacao = _nfc(" - ".join(obs_parts))

            # IPTU (stored in centavos)
            iptu_mes_raw = _v(row, "iptu_por_mes")
            iptu_ano_raw = _v(row, "iptu_por_ano")
            iptu_matricula = _v(row, "iptu_matricula")
            try:
                iptu_mes = float(iptu_mes_raw) / 100 if iptu_mes_raw else 0.0
            except (ValueError, TypeError):
                iptu_mes = 0.0
            try:
                iptu_ano = float(iptu_ano_raw) / 100 if iptu_ano_raw else 0.0
            except (ValueError, TypeError):
                iptu_ano = 0.0

            # Condomínio (stored in centavos)
            valor_condominio = _fmt_centavos(_v(row, "valor_condominio_centavos"))

            # Endereço — CEP stored as integer in XLSX (zero-pad to 8 digits)
            cep_digits = re.sub(r"\D", "", _v(row, "cep"))
            cep = cep_digits.zfill(8) if cep_digits else ""
            cidade = _nfc(_v(row, "cidade"))
            estado = _v(row, "estado")
            bairro, rua, numero, complemento = normalize_address(
                _nfc(_v(row, "bairro")),
                _nfc(_v(row, "rua", "logradouro")),
                _v(row, "numero"),
                _nfc(_v(row, "complemento")),
            )

            # Cômodos
            dormitorios = _v(row, "dormitorios")
            suites = _v(row, "suites")
            vagas = _v(row, "vagas")

            # Comodidades (JSON array)
            comodidades = _parse_comodidades(_v(row, "comodidades"))

            # Banheiros — add 1 if "Banheiro social" present in comodidades
            ban_raw = _v(row, "banheiros")
            try:
                ban_count = int(float(ban_raw)) if ban_raw else 0
            except (ValueError, TypeError):
                ban_count = 0
            if "Banheiro social" in comodidades:
                ban_count += 1
            banheiros = str(ban_count) if ban_count else ""

            # Medidas de terreno
            lado1 = _fmt_val(_v(row, "terreno_medida_frente"))
            lado2 = _fmt_val(_v(row, "terreno_medida_fundos"))
            lado3 = _fmt_val(_v(row, "terreno_medida_direita"))
            lado4 = _fmt_val(_v(row, "terreno_medida_esquerda"))

            # Áreas (priority chain matches SQL IF/IFNULL logic)
            au = _fmt_val(_v(row, "area_util"))
            atc = _fmt_val(_v(row, "area_total_construida"))
            ap = _fmt_val(_v(row, "area_privada"))
            at = _fmt_val(_v(row, "area_terreno"))

            area_util       = _first_nonzero(au, atc, ap, at)
            area_total      = _first_nonzero(at, atc, ap, au)
            area_construida = _first_nonzero(atc, au, ap, at)

            # Finalidade
            grupo = _v(row, "grupo").lower()
            if "comercial" in grupo:
                finalidade = "Comercial"
            elif "residencial" in grupo or "rural" in grupo:
                finalidade = "Residencial"
            else:
                finalidade = "Não Residencial"

            # Geo-coordinates
            latitude = _v(row, "latitude")
            longitude = _v(row, "longitude")

            # % Administração (honorários) — strip % sign
            hon_loc = re.sub(r"[%\s]", "", _v(row, "honorarios_locacao"))
            try:
                perc_admin = f"{float(hon_loc):.2f}" if hon_loc and float(hon_loc) > 0 else ""
            except (ValueError, TypeError):
                perc_admin = ""

            # Estado de conservação
            em_construcao = _v(row, "em_construcao")
            if em_construcao in ("Novo", "Na planta", "Em construção"):
                estado_conservacao = "Novo"
            else:
                estado_conservacao = "Bem conservado"

            # Features for características
            feature_names: list[str] = [_COMODIDADES_MAP[c] for c in comodidades if c in _COMODIDADES_MAP]
            if _v(row, "financiavel") == "Sim":
                feature_names.append("Aceita financiamento")
            permuta = _v(row, "permuta").upper()
            if permuta in ("SIM", "VERDADEIRO", "TRUE", "1"):
                feature_names.append("Aceita Permuta")
            if _v(row, "mobiliado") == "Sim":
                feature_names.append("Mobília")

            # Build PropertyRecord
            pr = PropertyRecord()
            pr.codigo = str(codigo)
            pr.data_registro = data_registro
            pr.imobiliaria = "1"
            pr.status = status
            pr.tipo = tipo
            pr.sub_categoria = sub_categoria
            pr.valor_venda = valor_venda
            pr.valor_locacao = valor_locacao
            pr.ocupado = ocupado
            pr.mostrar_site = "1"
            pr.street_view = "1"
            pr.mapa_site = "1"
            pr.venda_exclusiva = venda_exclusiva
            pr.locacao_exclusiva = locacao_exclusiva
            pr.observacao = observacao
            pr.matricula = _v(row, "matricula")
            pr.num_iptu = iptu_matricula
            pr.valor_mensal_iptu = f"{iptu_mes:.2f}" if iptu_mes else ""
            pr.valor_anual_iptu = f"{iptu_ano:.2f}" if iptu_ano else ""
            pr.perc_iptu = "100" if (iptu_mes or iptu_ano or iptu_matricula) else ""
            pr.agua_esgoto = _v(row, "matricula_agua")
            pr.energia_uc = _v(row, "matricula_energia")
            pr.finalidade = finalidade
            pr.cep = cep
            pr.cidade = cidade
            pr.estado = estado
            pr.bairro = bairro
            pr.rua = rua
            pr.numero_end = numero
            pr.complemento = complemento
            pr.dormitorios = dormitorios
            pr.banheiros = banheiros
            pr.suites = suites
            pr.garagem = vagas
            pr.lado1 = lado1
            pr.lado2 = lado2
            pr.lado3 = lado3
            pr.lado4 = lado4
            pr.area_util = area_util
            pr.area_total = area_total
            pr.area_construida = area_construida
            pr.valor_condominio = valor_condominio
            pr.titulo_site = _nfc(_v(row, "titulo"))
            pr.obs_site = _nfc(_v(row, "descricao"))
            pr.ponto_referencia = _nfc(_v(row, "ponto_referencia"))
            pr.latitude = latitude
            pr.longitude = longitude
            pr.perc_administracao = perc_admin
            pr.estado_conservacao = estado_conservacao

            # Comodidades → structured room fields (from SQL JSON_CONTAINS checks)
            if "Closet" in comodidades:
                pr.closets = "1"
            if "Cozinha" in comodidades:
                pr.cozinhas = "1"
            if "Despensa" in comodidades:
                pr.despensas = "1"
            if "Lavanderia" in comodidades:
                pr.lavanderias = "1"
            if "Lavabo" in comodidades:
                pr.lavabos = "1"
            if "Escritório" in comodidades:
                pr.escritorio = "1"

            # Características combobox + fields
            pr.caracteristicas_sim_nao = build_sim_nao(feature_names)
            for fld, qty in map_characteristics_to_fields(feature_names).items():
                if not getattr(pr, fld, ""):
                    setattr(pr, fld, qty)

            prop_result.properties.append(pr)

            # ── IPTU record ───────────────────────────────────────────────────
            if iptu_mes or iptu_ano or iptu_matricula:
                prop_result.iptu.append(PropertyIptuRecord(
                    codigo_imovel=str(codigo),
                    tipo_iptu="IPTU Principal",
                    inscricao_iptu=iptu_matricula,
                    valor_mensal_iptu=f"{iptu_mes:.2f}" if iptu_mes else "0",
                    valor_anual_iptu=f"{iptu_ano:.2f}" if iptu_ano else "0",
                    parcelas_iptu="0",
                    perc_iptu="100",
                    obs_iptu="",
                ))

            # ── Owners (all IDs from id_proprietarios) ────────────────────────
            prop_owner_ids = _parse_ids(_v(row, "id_proprietarios"))
            if prop_owner_ids:
                for ow_id in prop_owner_ids:
                    pessoa = pessoa_by_id.get(ow_id, {})
                    if pessoa:
                        doc_raw = _v(pessoa, "documento")
                        try:
                            ow_doc = re.sub(r"\D", "", str(int(float(doc_raw)))) if doc_raw else ""
                        except (ValueError, TypeError):
                            ow_doc = re.sub(r"\D", "", doc_raw)
                        ow_cpf = ow_doc if len(ow_doc) == 11 else ""
                        ow_cnpj = ow_doc if len(ow_doc) == 14 else ""
                        ow_nome = _nfc(_v(pessoa, "nome"))
                        ow_codigo = ow_id
                    else:
                        ow_cpf = ""
                        ow_cnpj = imob_doc
                        ow_nome = imob_nome
                        ow_codigo = ""

                    # Banking data from Beneficiários sheet (matched by name)
                    benef = benef_by_nome.get(ow_nome, {})
                    tipo_pag = "A" if _v(benef, "tipo_conta") == "Conta Corrente" else "M"
                    banco = _v(benef, "banco")
                    agencia = _v(benef, "agencia")
                    conta = _v(benef, "conta")

                    prop_result.owners.append(PropertyOwnerRecord(
                        codigo_imovel=str(codigo),
                        cpf=ow_cpf,
                        cnpj=ow_cnpj,
                        codigo_pessoa=ow_codigo,
                        percentual="100",
                    ))
                    prop_result.owners_favored.append(PropertyOwnerFavoredRecord(
                        codigo_imovel=str(codigo),
                        cpf=ow_cpf,
                        cnpj=ow_cnpj,
                        codigo_pessoa=ow_codigo,
                        tipo_pagamento=tipo_pag,
                        percentual="100",
                        cpf_favorecido=ow_cpf,
                        cnpj_favorecido=ow_cnpj,
                        id_favorecido=ow_codigo,
                        favorecido=ow_nome,
                        banco=banco,
                        agencia=agencia,
                        digito_agencia="",
                        conta=conta,
                        digito_conta="",
                        poupanca="0",
                    ))
            else:
                # No owner ID → fallback to imobiliária
                prop_result.owners.append(PropertyOwnerRecord(
                    codigo_imovel=str(codigo),
                    cpf="",
                    cnpj=imob_doc,
                    codigo_pessoa="",
                    percentual="100",
                ))
                prop_result.owners_favored.append(PropertyOwnerFavoredRecord(
                    codigo_imovel=str(codigo),
                    cpf="",
                    cnpj=imob_doc,
                    codigo_pessoa="",
                    tipo_pagamento="M",
                    percentual="100",
                    cpf_favorecido="",
                    cnpj_favorecido=imob_doc,
                    id_favorecido="",
                    favorecido=imob_nome,
                    banco="",
                    agencia="",
                    digito_agencia="",
                    conta="",
                    digito_conta="",
                    poupanca="0",
                ))

            # ── Captivators — always imob_doc ─────────────────────────────────
            if imob_doc:
                # S captivator when property is for sale
                if is_venda:
                    prop_result.captivators.append(PropertyCaptivatorRecord(
                        codigo_imovel=str(codigo),
                        cpf_cnpj=imob_doc,
                        departamento="S",
                        data_captacao=data_registro,
                    ))
                # L captivator when for rent, has contract, or neither sale nor rent
                if is_locacao or has_contrato or (not is_venda and not is_locacao):
                    prop_result.captivators.append(PropertyCaptivatorRecord(
                        codigo_imovel=str(codigo),
                        cpf_cnpj=imob_doc,
                        departamento="L",
                        data_captacao=data_registro,
                    ))

        return prop_result
