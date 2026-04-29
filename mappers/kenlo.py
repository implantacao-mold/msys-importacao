from __future__ import annotations
import re
from datetime import datetime, date
from typing import Any

from core.base_mapper import BaseMapper, ExtractionResult, PersonRecord, EmailRecord, PhoneRecord
from core.characteristics_utils import build_sim_nao, map_characteristics_to_fields
from core.phone_utils import processar_telefone, is_valid_email
from core.property_records import (
    PropertyExtractionResult, PropertyRecord, PropertyOwnerRecord,
    PropertyOwnerFavoredRecord, PropertyCaptivatorRecord, PropertyIptuRecord,
    normalize_address,
)
from core.subcategorias import get_custom_subcat


# ── Helpers ───────────────────────────────────────────────────────────────────

def _v(row: dict, *keys: str) -> str:
    for k in keys:
        v = row.get(k)
        if v is not None:
            s = str(v).strip()
            if s and s.lower() not in ("none", "nan"):
                return s
    return ""


def _flt(row: dict, *keys: str) -> float:
    v = _v(row, *keys)
    try:
        return float(v.replace(",", ".")) if v else 0.0
    except (ValueError, TypeError):
        return 0.0


def _fmt(v) -> str:
    """Numérico → '123.45', zero/vazio → ''."""
    try:
        f = float(str(v or "").strip().replace(",", "."))
        return f"{f:.2f}" if f else ""
    except (ValueError, TypeError):
        return ""


def _sim_nao_or_num(row: dict, key: str) -> str:
    """'Sim'→'1', 'Não'→'0', senão retorna o valor numérico como string."""
    v = _v(row, key)
    lo = v.lower()
    if lo == "sim":
        return "1"
    if lo in ("não", "nao"):
        return "0"
    return v


def _parse_phones(telefones_text: str) -> list[str]:
    """Extrai números de texto como 'Tel. Residencial: (16) 3987-1482 Celular: (16) 9937-41792'."""
    results = []
    for m in re.finditer(r"\((\d{2})\)\s*([\d\s\-]+)", telefones_text):
        ddd = m.group(1)
        num = re.sub(r"\D", "", m.group(2))
        if num:
            results.append(ddd + num)
    return results


def _parse_emails(emails_text: str) -> list[str]:
    return [e.strip() for e in re.split(r"[,;\s]+", emails_text) if is_valid_email(e.strip())]


# ── Subcategoria (CASE do SQL de migração) ────────────────────────────────────

_TIPO_SUBCAT: dict[str, str] = {
    "Apartamento":           "1",
    "Apartamento Duplex":    "5",
    "Apartamento Triplex":   "6",
    "Apartamento Garden":    "43",
    "Andar Corporativo":     "11",
    "Barracão":              "41",
    "Box/Garagem":           "15",
    "Casa":                  "7",
    "Chácara":               "16",
    "Cobertura":             "2",
    "Conjunto":              "11",
    "Edícula":               "9",
    "Fazenda":               "17",
    "Flat":                  "3",
    "Haras":                 "20",
    "Hotel":                 "14",
    "Loja":                  "25",
    "Loft":                  "33",
    "Kitnet":                "4",
    "Sala":                  "11",
    "Ponto":                 "31",
    "Pavilhão":              "41",
    "Sobrado":               "8",
    "Studio":                "15",
    "Terreno":               "21",
    "Resort":                "18",
    "Rancho":                "29",
    "Salão":                 "12",
    "Sítio":                 "19",
    "Galpão":                "41",
    "Área":                  "28",
    "Village":               "7",
    "Prédio":                "14",
    "Penthouse":             "2",
    "Laje":                  "7",
    "Pousada":               "38",
}

# Mapeamento campo XLSX → nome canônico de característica
_FEATURE_MAP: list[tuple[str, str]] = [
    ("aceita financiamento", "Aceita financiamento"),
    ("agua",                    "Água"),
    ("esgoto",                  "Esgoto"),
    ("energia",                 "Energia elétrica"),
    ("piscina",                 "Piscina"),
    ("churrasqueira",           "Churrasqueira"),
    ("area serviço",            "Área de serviço"),
    ("caseiro",                 "Caseiro"),
    ("zelador",                 "Zelador"),
    ("adega",                   "Adega"),
    ("quadra poliesportiva",    "Quadra Poliesportiva"),
    ("sauna",                   "Sauna"),
    ("vestiario",               "Vestiários"),
    ("campo futebol",           "Campo de futebol"),
    ("varanda",                 "Varanda"),
    ("sacada",                  "Sacada"),
    ("hidro",                   "Hidro"),
    ("armario cozinha",         "Armários na Cozinha"),
    ("armario closet",          "Armário no closet"),
    ("armario banheiro",        "Armários nos Banheiros"),
    ("telefone",                "Telefone"),
    ("tv cabo",                 "Televisão a cabo"),
    ("quintal",                 "Quintal"),
    ("alarme",                  "Alarme"),
    ("portao",                  "Portão eletrônico"),
    ("terraco",                 "Terraço"),
    ("jardim inverno",          "Jardim de inverno"),
    ("lareira",                 "Lareira"),
    ("mobiliado",               "Mobília"),
    ("ofuro",                   "Ofurô"),
    ("doca",                    "Doca"),
    ("aquecimento solar",       "Aquecedor solar"),
    ("guarita",                 "Guarita"),
    ("gerador",                 "Gerador elétrico"),
    ("mezanino",                "Mezanino"),
    ("vista mar",               "Vista mar"),
    ("armario dormitorio",      "Armários no Quarto"),
    ("ar",                      "Ar-condicionado"),
    ("elevador",                "Elevadores"),
    ("carpete",                 "Carpete"),
    ("Piso frio",               "Piso frio"),
    ("piso elevado",            "Piso elevado"),
    ("cerca",                   "Cerca"),
    ("varanda gourmet",         "Varanda Gourmet"),
    ("solarium",                "Solarium"),
    ("armario escritorio",      "Armário no escritório"),
    ("armario sala",            "Armário na sala"),
    ("armario area de servico", "Armário na área de serviço"),
    ("edicula",                 "Edícula"),
    ("piso laminado",           "Piso laminado"),
    ("piso porcelanato",        "Porcelanato"),
]

_FACE_MAP: dict[str, str] = {
    "Oeste": "Frente oeste",
    "Norte": "Frente norte",
    "Leste": "Frente leste",
    "Sul":   "Frente sul",
}


# ── Mapper ────────────────────────────────────────────────────────────────────

class KenloMapper(BaseMapper):
    NAME = "Kenlo"
    EXTENSIONS = [".zip"]
    DESCRIPTION = "Kenlo (ZIP com XLSX)"

    def can_handle(self, filename: str) -> bool:
        return filename.lower().endswith(".zip")

    def extract_zip(self, files: dict[str, Any]) -> ExtractionResult:
        result = ExtractionResult()
        seen: set[str] = set()

        clientes_data   = self._find(files, "clientes")
        imoveis_data    = self._find(files, "imoveis")
        usuarios_data   = self._find(files, "usuarios")
        iu_data         = self._find(files, "imoveisusuarios")

        # OW = clientes cujo 'id cliente' aparece em Imoveis como dono
        prop_cli_ids: set[str] = set()
        if imoveis_data:
            for row in imoveis_data:
                cli_id = _v(row, "id cliente")
                if cli_id:
                    prop_cli_ids.add(cli_id)

        if clientes_data:
            for row in clientes_data:
                cli_id = _v(row, "id cliente")
                nome = _v(row, "nome")
                if not nome:
                    continue
                tipo = "OW" if cli_id in prop_cli_ids else "BU"
                self._process_cliente(row, cli_id or nome, tipo, result, seen)

        if usuarios_data:
            for row in usuarios_data:
                usr_id = _v(row, "id")
                nome = _v(row, "nome")
                if not nome:
                    continue
                codigo = "U" + usr_id if usr_id else "U" + re.sub(r"\D", "", _v(row, "cpf"))
                if not codigo or codigo == "U":
                    continue
                self._process_usuario(row, codigo, result, seen)

        result.property_result = self._extract_properties(
            imoveis_data or [],
            iu_data or [],
            usuarios_data or [],
            clientes_data or [],
        )
        return result

    def _find(self, files: dict, prefix: str) -> list[dict] | None:
        def _extract(data):
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                for v in data.values():
                    if isinstance(v, list):
                        return v
            return None

        # Exact stem match first
        for name, data in files.items():
            stem = name.rsplit(".", 1)[0].lower()
            if stem == prefix.lower():
                r = _extract(data)
                if r is not None:
                    return r
        # Fall back to contains match
        for name, data in files.items():
            if prefix.lower() in name.lower():
                r = _extract(data)
                if r is not None:
                    return r
        return None

    # ── Pessoas ───────────────────────────────────────────────────────────────

    def _process_cliente(
        self,
        row: dict,
        codigo: str,
        tipo: str,
        result: ExtractionResult,
        seen: set[str],
    ) -> None:
        key = f"{codigo}|{tipo}"
        if key in seen:
            return
        seen.add(key)

        p = PersonRecord()
        p.codigo = codigo
        p.tipo = tipo
        p.nome = _v(row, "nome")
        p.cpf = re.sub(r"\D", "", _v(row, "cpf"))
        p.cnpj = re.sub(r"\D", "", _v(row, "cnpj"))
        p.rg = _v(row, "rg")
        p.data_nascimento = _v(row, "data nascimento")
        p.sexo = _v(row, "sexo")
        p.estado_civil = _v(row, "estado civil")
        p.profissao = _v(row, "profissão", "profissao")
        p.nacionalidade = _v(row, "nacionalidade")
        p.cep = re.sub(r"\D", "", _v(row, "cep"))
        p.cidade = _v(row, "cidade")
        p.bairro = _v(row, "bairro")
        p.estado = _v(row, "uf")
        p.endereco = _v(row, "logradouro")
        p.numero = _v(row, "número", "numero")
        p.complemento = _v(row, "complemento")
        p.observacao = _v(row, "observações", "observacoes")
        result.persons.append(p)

        for digits in _parse_phones(_v(row, "telefones")):
            parsed = processar_telefone(digits)
            if parsed:
                result.phones.append(PhoneRecord(
                    codigo_pessoa=codigo, tipo_pessoa=tipo,
                    ddi=parsed["ddi"], ddd=parsed["ddd"],
                    telefone=parsed["numero"], tipo_telefone=parsed["tipo"],
                ))

        for email in _parse_emails(_v(row, "emails")):
            result.emails.append(EmailRecord(
                codigo_pessoa=codigo, tipo_pessoa=tipo,
                email=email, tipo_email="",
            ))

    def _process_usuario(
        self,
        row: dict,
        codigo: str,
        result: ExtractionResult,
        seen: set[str],
    ) -> None:
        key = f"{codigo}|EM"
        if key in seen:
            return
        seen.add(key)

        p = PersonRecord()
        p.codigo = codigo
        p.tipo = "EM"
        p.nome = _v(row, "nome", "nome completo")
        p.cpf = re.sub(r"\D", "", _v(row, "cpf"))
        if not p.cpf:
            return
        p.rg = _v(row, "rg")
        p.sexo = _v(row, "sexo")
        p.creci = _v(row, "creci")
        p.cep = re.sub(r"\D", "", _v(row, "cep"))
        p.cidade = _v(row, "cidade")
        p.bairro = _v(row, "bairro")
        p.estado = _v(row, "uf")
        p.endereco = _v(row, "logradouro")
        p.numero = _v(row, "número", "numero")
        p.complemento = _v(row, "complemento")
        result.persons.append(p)

        for field in ("telefone", "celular"):
            raw = _v(row, field)
            if not raw:
                continue
            parsed = processar_telefone(raw)
            if parsed:
                result.phones.append(PhoneRecord(
                    codigo_pessoa=codigo, tipo_pessoa="EM",
                    ddi=parsed["ddi"], ddd=parsed["ddd"],
                    telefone=parsed["numero"], tipo_telefone=parsed["tipo"],
                ))

        email = _v(row, "e-mail", "email")
        if is_valid_email(email):
            result.emails.append(EmailRecord(
                codigo_pessoa=codigo, tipo_pessoa="EM",
                email=email, tipo_email="",
            ))

    # ── Imóveis ───────────────────────────────────────────────────────────────

    def _extract_properties(
        self,
        imoveis_rows: list[dict],
        iu_rows: list[dict],
        usuarios_rows: list[dict],
        clientes_rows: list[dict],
    ) -> PropertyExtractionResult:
        prop_result = PropertyExtractionResult()

        imob_doc  = re.sub(r"\D", "", self.context.get("imob_cpf_cnpj", ""))
        imob_nome = self.context.get("imob_nome", "")

        # id usuario → cpf (fallback imob_doc)
        cpf_by_usuario: dict[str, str] = {}
        nome_by_usuario: dict[str, str] = {}
        for u in usuarios_rows:
            uid  = _v(u, "id")
            cpf  = re.sub(r"\D", "", _v(u, "cpf"))
            nome = _v(u, "nome", "nome completo")
            if uid:
                cpf_by_usuario[uid]  = cpf or imob_doc
                nome_by_usuario[uid] = nome

        # id imovel → lista de imoveisusuarios
        iu_by_imovel: dict[str, list[dict]] = {}
        for iu in iu_rows:
            iid = _v(iu, "id imovel")
            if iid:
                iu_by_imovel.setdefault(iid, []).append(iu)

        # id cliente → (doc, nome)  doc = cpf se Fisica, cnpj se Juridica
        cli_by_id: dict[str, tuple[str, str]] = {}
        for c in clientes_rows:
            cid = _v(c, "id cliente")
            if not cid:
                continue
            tipo_p = _v(c, "tipo de pessoa")
            raw_doc = _v(c, "cpf") if tipo_p == "Fisica" else _v(c, "cnpj")
            doc = re.sub(r"\D", "", raw_doc)
            cli_by_id[cid] = (doc, _v(c, "nome"))

        for row in imoveis_rows:
            referencia = _v(row, "referencia")
            if not referencia:
                continue

            imovel_id = _v(row, "id imovel")

            # Status
            status = "1" if _v(row, "status") == "Ativo" else "5"

            # Valores
            sv = _flt(row, "valor venda")
            rv = _flt(row, "valor locacao")

            # Tipo S/L/SL (conforme SQL)
            if sv > 0 and rv > 0:
                tipo = "SL"
            elif rv > 0:
                tipo = "L"
            elif sv > 0:
                tipo = "S"
            else:
                tipo = "L"

            # Subcategoria
            tipo_imovel = _v(row, "tipo")
            finalidade  = _v(row, "finalidade")
            if tipo_imovel == "Casa" and finalidade == "Comercial":
                sub_cat = "0"
            else:
                sub_cat = get_custom_subcat(tipo_imovel, "") or _TIPO_SUBCAT.get(tipo_imovel, "")

            # Data de registro (formato M/D/YYYY do Kenlo)
            data_raw = _v(row, "data cadastro")
            try:
                data_registro = datetime.strptime(data_raw, "%m/%d/%Y").date().isoformat()
            except (ValueError, TypeError):
                data_registro = date.today().isoformat()

            # Endereço
            rua_raw = f"{_v(row, 'tipo logradouro')} {_v(row, 'logradouro')}".strip()
            bairro, rua, numero_end, complemento = normalize_address(
                _v(row, "bairro"),
                rua_raw,
                _v(row, "numero"),
                _v(row, "complemento"),
            )
            cep = re.sub(r"\D", "", _v(row, "cep"))

            # Dormitórios / suítes / banheiros
            dormitorios = _sim_nao_or_num(row, "dormitorios")
            suites      = _sim_nao_or_num(row, "suites")
            b_raw = _v(row, "banheiros")
            if b_raw.lower() in ("não", "nao"):
                banheiros = "0"
            else:
                try:
                    b = float(b_raw or "0")
                    s = float(suites or "0")
                    banheiros = str(int(b - s)) if b > s else str(int(b))
                except (ValueError, TypeError):
                    banheiros = b_raw

            # Garagem
            try:
                g_cob = _flt(row, "garagens cobertas")
                g_des = _flt(row, "garagens descobertas")
                garagem        = str(int(round(g_cob + g_des))) if (g_cob + g_des) else ""
                garagem_coberta = str(int(g_cob)) if g_cob else ""
            except (ValueError, TypeError):
                garagem = garagem_coberta = ""

            # Obs (CONCAT do SQL)
            obs_parts: list[str] = [f"Código: {referencia}"]
            dg = _v(row, "descricao geral")
            if dg:
                obs_parts.append(dg)
            obs = " - ".join(obs_parts)

            def _ap(label: str, val: str) -> str:
                return f" - {label}: {val}" if val and val not in ("0", "0.0", "0.00") else ""

            obs += _ap("Med. Terreno", _v(row, "dimensao terreno"))
            obs += _ap("Usou FGTS (3 ultimos anos)", _v(row, "fgts"))
            obs += _ap("Motivo Venda", _v(row, "motivo venda"))
            obs += _ap("Doc", _v(row, "documentacao"))
            cc = _v(row, "condicao comercial")
            if cc and cc != "0":
                obs += f" - Cond. Comercial: {cc}"
            obs += _ap("Sinal", _v(row, "sinal"))
            obs += _ap("Saldo Devedor", _v(row, "saldo devedor"))
            obs += _ap("Obs Sinal", _v(row, "observacao sinal"))
            uid_cad = _v(row, "usuario cadastro")
            nome_cad = nome_by_usuario.get(uid_cad, "")
            if nome_cad:
                obs += f" - Cadastrado por: {nome_cad}"

            # Características
            feature_names: list[str] = []
            for col, name in _FEATURE_MAP:
                if _v(row, col) == "Sim":
                    feature_names.append(name)
            face = _v(row, "face")
            if face in _FACE_MAP:
                feature_names.append(_FACE_MAP[face])

            # ── PropertyRecord ────────────────────────────────────────────────
            pr = PropertyRecord()
            pr.codigo         = referencia
            pr.imobiliaria    = "1"
            pr.status         = status
            pr.tipo           = tipo
            pr.sub_categoria  = sub_cat
            pr.data_registro  = data_registro
            pr.finalidade     = finalidade

            pr.valor_venda    = _fmt(sv) if sv else ""
            pr.valor_locacao  = _fmt(rv) if rv else ""
            pr.valor_condominio = _fmt(_flt(row, "valor condominio"))

            pr.ocupado           = "1" if _v(row, "ocupacao") == "Ocupado" else "0"
            pr.mostrar_site      = "1" if _v(row, "site") == "Sim" else "0"
            pr.destaque          = "1" if _v(row, "destaque") == "Sim" else "0"
            pr.locacao_exclusiva = "1" if rv > 0 and _v(row, "exclusividade") == "Sim" else "0"
            pr.venda_exclusiva   = "1" if sv > 0 and _v(row, "exclusividade") == "Sim" else "0"
            pr.street_view       = "1"
            pr.mapa_site         = "1"

            pr.observacao        = obs
            pr.obs_site          = _v(row, "descricao site")
            pr.url_video         = _v(row, "youtube")
            pr.matricula         = _v(row, "cartorio")
            pr.agua_esgoto       = _v(row, "saneamento")
            pr.energia_uc        = _v(row, "eletricidade")

            pr.cep           = cep
            pr.cidade        = _v(row, "cidade")
            pr.bairro        = bairro
            pr.estado        = _v(row, "estado")
            pr.rua           = rua
            pr.numero_end    = numero_end
            pr.complemento   = complemento

            pr.dormitorios   = dormitorios
            pr.banheiros     = banheiros
            pr.suites        = suites
            pr.closets       = "1" if _v(row, "armario closet") == "Sim" else ""
            pr.salas         = _sim_nao_or_num(row, "salas")
            pr.copas         = "1" if _v(row, "copa") == "Sim" else ""
            pr.cozinhas      = "1" if _v(row, "cozinha") == "Sim" else ""
            pr.despensas     = "1" if _v(row, "despensa") == "Sim" else ""
            pr.lavanderias   = "1" if _v(row, "lavanderia") == "Sim" else ""
            pr.lavabos       = "1" if _v(row, "lavabo") == "Sim" else ""
            pr.dorm_funcionario    = "1" if _v(row, "dormitorio empregada") == "Sim" else ""
            pr.banheiro_funcionario = "1" if _v(row, "banheiro empregada") == "Sim" else ""
            pr.escritorio    = "1" if _v(row, "escritorio") == "Sim" else ""
            pr.depositos     = "1" if _v(row, "deposito") == "Sim" else ""
            pr.recepcoes     = "1" if _v(row, "recepcao") == "Sim" else ""
            pr.garagem       = garagem
            pr.garagem_coberta = garagem_coberta

            pr.area_util     = _fmt(_flt(row, "area util construida"))
            pr.area_total    = _fmt(_flt(row, "area total"))
            pr.area_construida = pr.area_util

            pr.lado1 = "0"
            pr.lado2 = "0"
            pr.lado3 = "0"
            pr.lado4 = "0"

            pr.agua      = "1" if _v(row, "agua") == "Sim" else ""
            pr.lago      = "1" if _v(row, "lago") == "Sim" else ""
            pr.estabulo  = "1" if _v(row, "estabulo") == "Sim" else ""
            pr.granja    = _v(row, "granja")
            pr.mangueiro = "1" if _v(row, "mangueiro") == "Sim" else ""

            pr.latitude          = _v(row, "dl_latitude")
            pr.longitude         = _v(row, "dl_longitude")
            pr.ponto_referencia  = _v(row, "ponto referencia")
            pr.titulo_site       = _v(row, "titulo")
            pr.ano_construcao    = _v(row, "ano construcao")

            # Características
            pr.caracteristicas_sim_nao = build_sim_nao(feature_names)
            for fld, qty in map_characteristics_to_fields(feature_names).items():
                if not getattr(pr, fld, ""):
                    setattr(pr, fld, qty)

            prop_result.properties.append(pr)

            # ── IPTU ──────────────────────────────────────────────────────────
            prefeitura = _v(row, "prefeitura")
            cond_iptu  = _v(row, "condição iptu", "condicao iptu")
            val_iptu   = _flt(row, "valor iptu")
            try:
                pref_ok = float(prefeitura) > 0 if prefeitura else False
            except (ValueError, TypeError):
                pref_ok = bool(prefeitura)
            if pref_ok or cond_iptu or val_iptu:
                prop_result.iptu.append(PropertyIptuRecord(
                    codigo_imovel=referencia,
                    tipo_iptu="IPTU Principal",
                    inscricao_iptu=prefeitura,
                    valor_mensal_iptu=_fmt(val_iptu) if cond_iptu == "Mensal" else "0",
                    valor_anual_iptu=_fmt(val_iptu)  if cond_iptu == "Anual"  else "0",
                    parcelas_iptu="0",
                    perc_iptu="100",
                    obs_iptu="",
                ))

            # ── Proprietário ──────────────────────────────────────────────────
            cli_id = _v(row, "id cliente")
            if cli_id:
                doc, cli_nome = cli_by_id.get(cli_id, ("", imob_nome))
                owner_cpf  = doc if len(doc) == 11 else ""
                owner_cnpj = doc if len(doc) == 14 else ""
            else:
                owner_cpf  = ""
                owner_cnpj = imob_doc
                cli_nome   = imob_nome

            prop_result.owners.append(PropertyOwnerRecord(
                codigo_imovel=referencia,
                cpf=owner_cpf,
                cnpj=owner_cnpj,
                codigo_pessoa=cli_id,
                percentual="100",
            ))
            prop_result.owners_favored.append(PropertyOwnerFavoredRecord(
                codigo_imovel=referencia,
                cpf=owner_cpf,
                cnpj=owner_cnpj,
                codigo_pessoa=cli_id,
                tipo_pagamento="M",
                percentual="100",
                cpf_favorecido=owner_cpf,
                cnpj_favorecido=owner_cnpj,
                id_favorecido=cli_id,
                favorecido=cli_nome,
                banco="", agencia="", digito_agencia="",
                conta="", digito_conta="", poupanca="",
            ))

            # ── Captivadores ──────────────────────────────────────────────────
            iu_list = iu_by_imovel.get(imovel_id, [])
            emitted: set[str] = set()

            # L: rv > 0 OU (sv == 0 AND rv == 0)
            if rv > 0 or (sv == 0 and rv == 0):
                l_caps = [
                    iu for iu in iu_list
                    if _v(iu, "tipo comissao") == "Captador" and _v(iu, "locacao") == "Sim"
                ]
                if l_caps:
                    for iu in l_caps:
                        cap_cpf = cpf_by_usuario.get(_v(iu, "id usuario"), imob_doc)
                        k = f"{cap_cpf}|L"
                        if k not in emitted:
                            emitted.add(k)
                            prop_result.captivators.append(PropertyCaptivatorRecord(
                                codigo_imovel=referencia,
                                cpf_cnpj=cap_cpf,
                                departamento="L",
                                data_captacao="",
                            ))
                elif imob_doc:
                    k = f"{imob_doc}|L"
                    if k not in emitted:
                        emitted.add(k)
                        prop_result.captivators.append(PropertyCaptivatorRecord(
                            codigo_imovel=referencia,
                            cpf_cnpj=imob_doc,
                            departamento="L",
                            data_captacao="",
                        ))

            # S: sv > 0
            if sv > 0:
                s_caps = [
                    iu for iu in iu_list
                    if _v(iu, "tipo comissao") == "Captador" and _v(iu, "venda") == "Sim"
                ]
                if s_caps:
                    for iu in s_caps:
                        cap_cpf = cpf_by_usuario.get(_v(iu, "id usuario"), imob_doc)
                        k = f"{cap_cpf}|S"
                        if k not in emitted:
                            emitted.add(k)
                            prop_result.captivators.append(PropertyCaptivatorRecord(
                                codigo_imovel=referencia,
                                cpf_cnpj=cap_cpf,
                                departamento="S",
                                data_captacao="",
                            ))
                elif imob_doc:
                    k = f"{imob_doc}|S"
                    if k not in emitted:
                        emitted.add(k)
                        prop_result.captivators.append(PropertyCaptivatorRecord(
                            codigo_imovel=referencia,
                            cpf_cnpj=imob_doc,
                            departamento="S",
                            data_captacao="",
                        ))

        return prop_result
