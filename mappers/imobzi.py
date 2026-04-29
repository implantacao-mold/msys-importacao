from __future__ import annotations
import ast
import hashlib
import html as _html_mod
import re
from typing import Any

from core.base_mapper import BaseMapper, ExtractionResult, PersonRecord, EmailRecord, PhoneRecord
from core.phone_utils import processar_telefone, is_valid_email
from core.property_records import (
    PropertyExtractionResult,
    PropertyRecord,
    PropertyOwnerRecord,
    PropertyOwnerFavoredRecord,
    PropertyCaptivatorRecord,
    PropertyIptuRecord,
    normalize_address,
)
from core.cep_lookup import fill_city_state, is_valid_cep, lookup_cep_by_city
from core.characteristics_utils import build_sim_nao, map_characteristics_to_fields


def _ref_id(obj: Any) -> str:
    if isinstance(obj, dict):
        return str(obj.get("id", obj.get("urlsafe", "")))
    return str(obj) if obj else ""


def _collect(files: dict[str, Any], prefix: str) -> list[dict]:
    """Agrega arquivos paginados (person-0.json, person-1.json, …)."""
    all_items: list[dict] = []
    i = 0
    while True:
        data = files.get(f"{prefix}-{i}.json") or files.get(f"{prefix}{i}.json")
        if data is None:
            if i == 0:
                data = files.get(f"{prefix}.json")
            if data is None:
                break
        if isinstance(data, list):
            all_items.extend(data)
        elif isinstance(data, dict):
            items = data.get("items") or data.get("results") or []
            all_items.extend(items if isinstance(items, list) else [data])
        i += 1
    return all_items


def _s(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip()


def _parse_flat_list(v: Any) -> list:
    """Converte valor que pode ser lista Python ou repr de lista."""
    if isinstance(v, list):
        return v
    if v is None:
        return []
    s = str(v).strip()
    if not s or s in ("[]", "None"):
        return []
    try:
        result = ast.literal_eval(s)
        return result if isinstance(result, list) else [result]
    except Exception:
        return [s]


def _fmt_val(v: Any) -> str:
    """Formata valor numérico com 2 casas decimais; retorna '' se zero ou nulo."""
    if v is None or v == "" or v is False or v is True:
        return ""
    try:
        f = float(str(v).replace(",", "."))
        return f"{f:.2f}" if f else ""
    except (ValueError, TypeError):
        return ""


_HTML_TAG_RE = re.compile(r"<[^>]+>", re.IGNORECASE | re.DOTALL)


def _strip_html(text: str) -> str:
    """Remove tags HTML e decodifica entidades básicas."""
    text = _HTML_TAG_RE.sub(" ", text)
    text = _html_mod.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _md5_code(nome: str, phone: str) -> str:
    return hashlib.md5((nome.upper() + phone).encode("utf-8")).hexdigest()[:16].upper()


_TYPE_MAP: dict[str, str] = {
    # Apartamentos
    "andar comercial": "11",
    "apto": "1",
    "apartment": "1",
    "apartamento": "1",
    "apartamento padrão": "1",
    "apartamento 01 dorm.": "1",
    "apartamento 02 dorm.": "1",
    "apartamento 03 dorm.": "1",
    "apartamento 04 dorm.": "1",
    "apartamento flat / studio": "3",
    "apartamento cobertura": "2",
    "apartamento cobertura duplex": "5",
    "apartamento cobertura triplex": "6",
    "apartamento duplex": "5",
    "duplex": "5",
    "apartamento garden": "43",
    "apartamento kitchenette/studio": "4",
    "kitnet": "4",
    "kitnet / conjugado": "4",
    "apartamento kitnet": "4",
    "apartamento loft": "33",
    "loft": "33",
    "apartamento studio": "46",
    "studio": "46",
    "flat": "3",
    "penthouse": "2",
    "cobertura": "2",
    "cobertura duplex": "5",
    "cobertura penthouse": "2",
    "triplex": "6",
    # Casas
    "house": "7",
    "casa": "7",
    "casa padrão": "7",
    "casa sala": "7",
    "casa 02 dorm.": "7",
    "casa 03 dorm.": "7",
    "casa 04 dorm.": "7",
    "casa geminada": "7",
    "casa térrea": "7",
    "casa triplex": "7",
    "casa village": "7",
    "sobrado": "8",
    "casa sobrado": "8",
    "casa condomínio": "10",
    "casa de condominio": "10",
    "casa em condominio": "10",
    "casa em condominio triplex": "10",
    "condominio": "10",
    "townhouse": "10",
    "casa sobrado de condominio": "40",
    "sobrado de condominio": "40",
    "casa edícula": "9",
    "casa área de lazer": "34",
    "casa chácara": "16",
    # Comercial
    "commercial_room": "11",
    "sala comercial": "11",
    "sala": "11",
    "conjunto / sala": "11",
    "office": "11",
    "escritorio": "11",
    "escritório": "11",
    "salao": "12",
    "salão": "12",
    "salão / loja": "12",
    "building": "14",
    "predio": "14",
    "prédio": "14",
    "prédio comercial": "14",
    "predio inteiro": "14",
    "commercial_building": "14",
    "store": "25",
    "loja": "25",
    "loja / salão": "25",
    "loja/salão": "25",
    "ponto comercial": "31",
    "warehouse": "41",
    "galpao": "41",
    "galpão": "41",
    "galpão / depósito / armazém": "41",
    "barracão": "41",
    "galp/dep": "41",
    "depósito / armazém": "61",
    "box / garagem": "55",
    # Terreno
    "land": "21",
    "terreno": "21",
    "terreno residencial": "26",
    "terreno comercial": "27",
    "terreno em condomínio": "22",
    "lote": "23",
    "lote / terreno": "23",
    # Industrial
    "industrial_shed": "44",
    # Rural
    "farm": "17",
    "fazenda": "17",
    "rural": "17",
    "chacara": "16",
    "chácara": "16",
    "sitio": "19",
    "sítio": "19",
    "rancho": "29",
}


class ImobziMapper(BaseMapper):
    NAME = "Imobzi"
    EXTENSIONS = [".zip"]
    DESCRIPTION = "Imobzi (ZIP com JSONs)"

    def can_handle(self, filename: str) -> bool:
        return filename.lower().endswith(".zip")

    def extract_zip(self, files: dict[str, Any]) -> ExtractionResult:
        result = ExtractionResult()
        seen: set[str] = set()

        persons_list = _collect(files, "person")
        orgs_list = _collect(files, "organization")
        props_list = _collect(files, "property")
        features_list = _collect(files, "propertyfeaturevalue")
        bankdata_list = _collect(files, "bankdata")
        users_list_raw = files.get("user.json") or []
        if isinstance(users_list_raw, dict):
            users_list_raw = [users_list_raw]

        params_list = _collect(files, "parameters")
        params = params_list[0] if params_list else {}

        # Índices por _id
        persons_by_id: dict[str, dict] = {}
        for p in persons_list:
            pid = _s(p.get("_id") or p.get("db_id"))
            if pid:
                persons_by_id[pid] = p

        orgs_by_id: dict[str, dict] = {}
        for o in orgs_list:
            oid = _s(o.get("_id") or o.get("db_id"))
            if oid:
                orgs_by_id[oid] = o

        # OW: pessoas marcadas como 'owner' no contactmanager
        cm_list = _collect(files, "contactmanager")
        owner_ids: set[str] = set()
        for cm in cm_list:
            if _s(cm.get("type")) == "owner":
                ref = cm.get("person_id")
                pid = _ref_id(ref) if isinstance(ref, dict) else _s(ref)
                if pid:
                    owner_ids.add(pid)

        bankdata_by_person: dict[str, list[dict]] = {}
        for bd in bankdata_list:
            ref = bd.get("person_id") or bd.get("_parent")
            if isinstance(ref, dict):
                pid = _ref_id(ref)
            else:
                pid = _s(ref)
            if pid:
                bankdata_by_person.setdefault(pid, []).append(bd)

        # Features por property _id
        features_by_prop: dict[str, list[str]] = {}
        for feat in features_list:
            _parent = feat.get("_parent")
            if isinstance(_parent, dict):
                prop_id = _ref_id(_parent)
            else:
                prop_id = _s(feat.get("_parent._id") or feat.get("_parent.id"))
            name = _s(feat.get("name") or feat.get("feature_name"))
            if prop_id and name:
                features_by_prop.setdefault(prop_id, []).append(name)

        # CNPJ captador via parameters → organization
        captador_cnpj = ""
        company_name = _s(params.get("company_name") or params.get("name"))
        if company_name:
            for org in orgs_list:
                if _s(org.get("name")).lower() == company_name.lower():
                    captador_cnpj = re.sub(r"\D", "", _s(org.get("cnpj")))
                    break

        prop_result = PropertyExtractionResult()

        for prop in props_list:
            prop_id = _s(prop.get("_id") or prop.get("db_id"))
            prop_code = _s(prop.get("code") or prop.get("codigo") or prop_id)

            data_registro = _s(prop.get("created_at") or "")[:10]

            # Status: active=True AND status=available → 1
            active = prop.get("active")
            status_raw = _s(prop.get("status") or prop.get("situation") or prop.get("property_situation"))
            status = "1" if (active is not False and status_raw == "available") else "5"

            # Tipo transação S / L / SL
            try:
                sv = float(str(prop.get("sale_value") or 0))
            except (ValueError, TypeError):
                sv = 0.0
            try:
                rv = float(str(prop.get("rental_value") or 0))
            except (ValueError, TypeError):
                rv = 0.0
            tipo_transacao = "SL" if sv and rv else ("S" if sv else "L")

            # Subcategoria
            type_raw = _s(prop.get("property_type") or prop.get("type", "")).lower()
            sub_cat = _TYPE_MAP.get(type_raw, "7")

            # Finalidade
            purpose_raw = _s(prop.get("finality") or prop.get("usage") or prop.get("purpose", ""))
            if purpose_raw == "residential":
                finalidade = "Residencial"
            elif purpose_raw == "commercial":
                finalidade = "Comercial"
            else:
                finalidade = purpose_raw.capitalize() if purpose_raw else ""

            # Endereço
            cep = re.sub(r"\D", "", _s(prop.get("zipcode") or prop.get("zip_code") or prop.get("cep")))
            cidade = _s(prop.get("city") or prop.get("cidade"))
            bairro = _s(prop.get("neighborhood") or prop.get("bairro"))
            estado = _s(prop.get("state") or prop.get("uf") or prop.get("estado"))
            rua = _s(prop.get("address") or prop.get("rua") or prop.get("logradouro"))
            complemento = _s(prop.get("address_complement") or prop.get("complemento"))
            numero_end = ""

            m = re.search(r",\s*(\d+)", rua)
            if m:
                numero_end = m.group(1)
                rua = rua[:m.start()].strip()

            bairro, rua, numero_end, complemento = normalize_address(bairro, rua, numero_end, complemento)
            cidade, estado = fill_city_state(cep, cidade, estado)
            if not is_valid_cep(cep) and cidade and estado:
                cep = lookup_cep_by_city(cidade, estado) or ""

            building_name = _s(prop.get("building_name") or prop.get("nome_condominio"))
            if building_name and building_name not in complemento:
                complemento = " - ".join(p for p in [complemento, building_name] if p)

            geo = prop.get("geo_location") or {}
            if not isinstance(geo, dict):
                try:
                    import ast as _ast
                    geo = _ast.literal_eval(_s(geo)) if geo else {}
                except Exception:
                    geo = {}
            lat = _s(geo.get("lat") or prop.get("lat") or prop.get("latitude"))
            lon = _s(geo.get("lon") or geo.get("lng") or prop.get("lng") or prop.get("longitude"))

            features = features_by_prop.get(prop_id, [])
            caract = build_sim_nao(features)

            # Observações com HTML removido
            obs_desc = _strip_html(_s(prop.get("description") or prop.get("observacao")))
            obs_site = _strip_html(_s(prop.get("site_description") or prop.get("obs_site")))
            observacao = f"Ref: {prop_code} - {obs_desc}" if obs_desc else f"Ref: {prop_code}"

            # Mostrar no site
            site_pub = prop.get("site_publish")
            mostrar_site = "1" if site_pub is True or _s(site_pub).lower() in ("true", "1", "yes") else "0"

            # IPTU
            iptu_raw = prop.get("iptu") or prop.get("iptu_value")
            iptu_val = _fmt_val(iptu_raw)
            iptu_parcelas = _s(prop.get("iptu_installments") or "")
            iptu_mensal = ""
            if iptu_val and iptu_parcelas:
                try:
                    iptu_mensal = f"{float(str(iptu_raw)) / max(int(iptu_parcelas), 1):.2f}"
                except (ValueError, ZeroDivisionError):
                    iptu_mensal = iptu_val

            # Ano de construção (built = número, não boolean)
            built_raw = prop.get("built")
            ano_construcao = ""
            if built_raw is not None and not isinstance(built_raw, bool):
                try:
                    ano_construcao = str(int(float(str(built_raw))))
                except (ValueError, TypeError):
                    ano_construcao = _s(built_raw)

            pr = PropertyRecord(
                codigo=prop_code,
                data_registro=data_registro,
                imobiliaria="1",
                status=status,
                finalidade=finalidade,
                tipo=tipo_transacao,
                sub_categoria=sub_cat,
                valor_venda=_fmt_val(sv),
                valor_locacao=_fmt_val(rv),
                mostrar_site=mostrar_site,
                street_view="1",
                mapa_site="1",
                observacao=observacao,
                obs_site=obs_site,
                cep=cep,
                cidade=cidade,
                bairro=bairro,
                estado=estado,
                rua=rua,
                numero_end=numero_end,
                complemento=complemento,
                num_apto=_s(prop.get("unit") or prop.get("num_apto") or prop.get("apartment_number")),
                num_bloco=_s(prop.get("block") or prop.get("num_bloco")),
                dormitorios=_s(prop.get("bedroom") or prop.get("bedrooms") or prop.get("dormitorios")),
                suites=_s(prop.get("suite") or prop.get("suites")),
                banheiros=_s(prop.get("bathroom") or prop.get("bathrooms") or prop.get("banheiros")),
                garagem=_s(prop.get("garage") or prop.get("garage_spaces") or prop.get("garagem")),
                area_util=_fmt_val(prop.get("useful_area") or prop.get("area_util")),
                area_total=_fmt_val(prop.get("lot_area") or prop.get("total_area") or prop.get("area_total")),
                area_construida=_fmt_val(prop.get("area") or prop.get("built_area") or prop.get("area_construida")),
                lado1=_fmt_val(prop.get("lot_measure_front")),
                lado2=_fmt_val(prop.get("lot_measure_behind")),
                lado3=_fmt_val(prop.get("lot_measure_right")),
                lado4=_fmt_val(prop.get("lot_measure_left")),
                nome_propriedade="",
                titulo_site=_s(prop.get("site_title") or prop.get("title") or prop.get("titulo")),
                valor_condominio=_fmt_val(prop.get("condominium") or prop.get("condominium_fee") or prop.get("valor_condominio")),
                latitude=lat,
                longitude=lon,
                num_iptu=_s(prop.get("iptu_number") or prop.get("num_iptu")),
                valor_anual_iptu=iptu_val,
                valor_mensal_iptu=iptu_mensal,
                parcelas_iptu=iptu_parcelas,
                perc_iptu="100" if iptu_val else "",
                caracteristicas_sim_nao=caract,
                perc_administracao=_fmt_val(prop.get("service_fee") or prop.get("perc_administracao")),
                ano_construcao=ano_construcao,
            )

            for field, qty in map_characteristics_to_fields(features).items():
                if not getattr(pr, field, ""):
                    setattr(pr, field, qty)

            if iptu_val:
                prop_result.iptu.append(PropertyIptuRecord(
                    codigo_imovel=prop_code,
                    tipo_iptu="IPTU Principal",
                    inscricao_iptu="",
                    valor_anual_iptu=iptu_val,
                    valor_mensal_iptu=iptu_mensal,
                    parcelas_iptu=iptu_parcelas,
                    perc_iptu="100",
                ))

            prop_result.properties.append(pr)

            # Proprietários via owners.person_id / owners.organization_id
            op_raw = _parse_flat_list(prop.get("owners.person_id"))
            oo_raw = _parse_flat_list(prop.get("owners.organization_id"))
            opct_raw = _parse_flat_list(prop.get("owners.percentage"))

            n_owners = max(len(op_raw), len(oo_raw))
            # Se todos os percentuais forem zero, distribui igualmente
            try:
                pcts = [float(str(opct_raw[i])) if i < len(opct_raw) and opct_raw[i] is not None else 0.0 for i in range(n_owners)]
            except (ValueError, TypeError):
                pcts = [0.0] * n_owners
            if n_owners and not any(pcts):
                pcts = [round(100.0 / n_owners, 2)] * n_owners

            owner_added = 0
            for idx in range(n_owners):
                pid_ref = op_raw[idx] if idx < len(op_raw) else None
                oid_ref = oo_raw[idx] if idx < len(oo_raw) else None
                pid = _ref_id(pid_ref) if pid_ref else ""
                oid = _ref_id(oid_ref) if oid_ref else ""
                percentual = f"{pcts[idx]:.2f}" if pcts[idx] else "100"

                owner_cpf = ""
                owner_cnpj = ""
                owner_codigo = ""
                owner_nome = ""

                if pid and pid in persons_by_id:
                    person = persons_by_id[pid]
                    owner_codigo = pid
                    owner_cpf = re.sub(r"\D", "", _s(person.get("cpf") or person.get("tax_id")))
                    fname = _s(person.get("firstname"))
                    lname = _s(person.get("lastname"))
                    if lname.lower() in ("n/d", "n/a", "-"):
                        lname = ""
                    owner_nome = _s(person.get("fullname")) or f"{fname} {lname}".strip()
                elif oid and oid in orgs_by_id:
                    org = orgs_by_id[oid]
                    owner_codigo = oid
                    owner_cnpj = re.sub(r"\D", "", _s(org.get("cnpj") or org.get("tax_id")))
                    owner_nome = _s(org.get("name") or org.get("nome"))

                if not owner_codigo:
                    continue

                prop_result.owners.append(PropertyOwnerRecord(
                    codigo_imovel=prop_code,
                    cpf=owner_cpf,
                    cnpj=owner_cnpj,
                    codigo_pessoa=owner_codigo,
                    percentual=percentual,
                ))

                bd_list = bankdata_by_person.get(pid, []) if pid else []
                bd = bd_list[0] if bd_list else None
                prop_result.owners_favored.append(PropertyOwnerFavoredRecord(
                    codigo_imovel=prop_code,
                    cpf=owner_cpf,
                    cnpj=owner_cnpj,
                    codigo_pessoa=owner_codigo,
                    tipo_pagamento="M",
                    percentual=percentual,
                    cpf_favorecido=owner_cpf,
                    cnpj_favorecido=owner_cnpj,
                    id_favorecido=owner_codigo,
                    favorecido=owner_nome,
                    banco=_s(bd.get("bank_name") or bd.get("bank")) if bd else "",
                    agencia=_s(bd.get("agency")) if bd else "",
                    conta=_s(bd.get("account")) if bd else "",
                    poupanca="1" if bd and _s(bd.get("account_type")) == "savings_account" else "0",
                ))
                owner_added += 1

            # Se não achou proprietário via links, usa imobiliária do contexto
            if owner_added == 0:
                imob_cnpj = re.sub(r"\D", "", self.context.get("imob_cpf_cnpj", ""))
                prop_result.owners.append(PropertyOwnerRecord(
                    codigo_imovel=prop_code,
                    cpf="",
                    cnpj=imob_cnpj,
                    codigo_pessoa="",
                    percentual="100",
                ))
                prop_result.owners_favored.append(PropertyOwnerFavoredRecord(
                    codigo_imovel=prop_code,
                    cpf="",
                    cnpj=imob_cnpj,
                    codigo_pessoa="",
                    tipo_pagamento="M",
                    percentual="100",
                    cpf_favorecido="",
                    cnpj_favorecido=imob_cnpj,
                ))

            # Captador: um registro por tipo de transação
            cap_cpf_cnpj = captador_cnpj or re.sub(r"\D", "", self.context.get("imob_cpf_cnpj", ""))
            if sv:
                prop_result.captivators.append(PropertyCaptivatorRecord(
                    codigo_imovel=prop_code,
                    cpf_cnpj=cap_cpf_cnpj,
                    departamento="S",
                    data_captacao=data_registro,
                ))
            if rv:
                prop_result.captivators.append(PropertyCaptivatorRecord(
                    codigo_imovel=prop_code,
                    cpf_cnpj=cap_cpf_cnpj,
                    departamento="L",
                    data_captacao=data_registro,
                ))

        # Pessoas — OW via contactmanager; proprietários também recebem BU
        # Emails e telefones são adicionados apenas na primeira ocorrência do código.
        contacts_added: set[str] = set()

        for person in persons_list:
            pid = _s(person.get("_id") or person.get("db_id"))
            if not pid:
                continue
            tipos = ["OW", "BU"] if pid in owner_ids else ["BU"]
            for tipo in tipos:
                key = f"{pid}|{tipo}"
                if key in seen:
                    continue
                seen.add(key)
                self._add_person(person, pid, tipo, result, add_contacts=(pid not in contacts_added))
                contacts_added.add(pid)

        for org in orgs_list:
            oid = _s(org.get("_id") or org.get("db_id"))
            if not oid:
                continue
            tipos = ["OW", "BU"] if oid in owner_ids else ["BU"]
            for tipo in tipos:
                key = f"{oid}|{tipo}"
                if key in seen:
                    continue
                seen.add(key)
                self._add_org(org, oid, tipo, result, add_contacts=(oid not in contacts_added))
                contacts_added.add(oid)

        # Usuários = EM (somente com CPF/CNPJ)
        for user in users_list_raw:
            uid = _s(user.get("_id") or user.get("db_id"))
            if not uid:
                continue
            key = f"{uid}|EM"
            if key in seen:
                continue
            seen.add(key)

            cpf = re.sub(r"\D", "", _s(user.get("cpf") or user.get("document") or user.get("cnpj")))
            if not cpf:
                continue
            p = PersonRecord()
            p.codigo = uid
            p.tipo = "EM"
            fname = _s(user.get("firstname"))
            lname = _s(user.get("lastname"))
            p.nome = _s(user.get("fullname")) or f"{fname} {lname}".strip()
            p.cpf = cpf
            p.creci = _s(user.get("license") or user.get("creci"))
            p.observacao = _s(user.get("function"))
            result.persons.append(p)

            phones_raw = _parse_flat_list(user.get("phones"))
            for ph_obj in phones_raw:
                if isinstance(ph_obj, dict):
                    raw = _s(ph_obj.get("number") or ph_obj.get("phone"))
                else:
                    raw = _s(ph_obj)
                digits = re.sub(r"\D", "", raw)
                if digits.startswith("55") and len(digits) > 11:
                    digits = digits[2:]
                parsed = processar_telefone(digits)
                if parsed:
                    result.phones.append(PhoneRecord(
                        codigo_pessoa=uid, tipo_pessoa="EM",
                        ddi=parsed["ddi"], ddd=parsed["ddd"],
                        telefone=parsed["numero"], tipo_telefone=parsed["tipo"],
                    ))

            email = _s(user.get("email"))
            if is_valid_email(email):
                result.emails.append(EmailRecord(
                    codigo_pessoa=uid, tipo_pessoa="EM",
                    email=email, tipo_email="",
                ))

        result.property_result = prop_result
        return result

    def scan_characteristics(self, data: dict) -> set[str]:
        result: set[str] = set()
        for feat in _collect(data, "propertyfeaturevalue"):
            name = _s(feat.get("name") or feat.get("feature_name"))
            if name:
                result.add(name)
        return result

    def _add_person(self, person: dict, codigo: str, tipo: str, result: ExtractionResult, add_contacts: bool = True) -> None:
        fname = _s(person.get("firstname"))
        lname = _s(person.get("lastname"))
        if lname.lower() in ("n/d", "n/a", "-"):
            lname = ""

        nome = _s(person.get("fullname")) or f"{fname} {lname}".strip() or fname

        gender_raw = _s(person.get("gender") or person.get("sexo"))
        sexo = "F" if gender_raw.lower() in ("feminino", "female", "f") else ("M" if gender_raw else "")

        address_raw = _s(person.get("address") or person.get("endereco"))
        if "," in address_raw:
            endereco = address_raw.split(",", 1)[0].strip()
            numero = address_raw.rsplit(",", 1)[-1].strip()
        else:
            endereco = address_raw
            numero = ""

        cidade = _s(person.get("city") or person.get("cidade"))
        if cidade.lower() == "não informado":
            cidade = ""
        cep = re.sub(r"\D", "", _s(person.get("zipcode") or person.get("cep")))
        estado = _s(person.get("state") or person.get("uf") or person.get("estado"))
        cidade, estado = fill_city_state(cep, cidade, estado)
        if not is_valid_cep(cep) and cidade and estado:
            cep = lookup_cep_by_city(cidade, estado) or ""

        p = PersonRecord()
        p.codigo = codigo
        p.tipo = tipo
        p.nome = nome
        p.cpf = re.sub(r"\D", "", _s(person.get("cpf") or person.get("tax_id")))
        p.rg = _s(person.get("rg"))
        p.data_nascimento = _s(person.get("birthday") or person.get("birth_date"))
        p.sexo = sexo
        p.profissao = _s(person.get("profession") or person.get("profissao"))
        p.nacionalidade = _s(person.get("nationality") or person.get("nacionalidade"))
        p.cep = cep
        p.cidade = cidade
        p.bairro = _s(person.get("neighborhood") or person.get("bairro"))
        p.estado = estado
        p.endereco = endereco
        p.numero = numero
        p.observacao = _s(person.get("notes") or person.get("observacao"))
        p.imobiliaria = "1"
        result.persons.append(p)

        if not add_contacts:
            return

        numbers = _parse_flat_list(person.get("phone.number"))
        types = _parse_flat_list(person.get("phone.type"))
        for i, num in enumerate(numbers):
            raw = _s(num)
            if not raw:
                continue
            digits = re.sub(r"\D", "", raw)
            if digits.startswith("55") and len(digits) > 11:
                digits = digits[2:]
            parsed = processar_telefone(digits)
            if parsed:
                ph_type = _s(types[i] if i < len(types) else "")
                if ph_type.lower() in ("mobile", "cell", "celular"):
                    parsed["tipo"] = "M"
                elif ph_type.lower() in ("home", "residential", "residencial"):
                    parsed["tipo"] = "R"
                elif ph_type.lower() in ("work", "commercial", "comercial"):
                    parsed["tipo"] = "C"
                result.phones.append(PhoneRecord(
                    codigo_pessoa=codigo, tipo_pessoa=tipo,
                    ddi=parsed["ddi"], ddd=parsed["ddd"],
                    telefone=parsed["numero"], tipo_telefone=parsed["tipo"],
                ))

        emails = _parse_flat_list(person.get("email") or person.get("emails"))
        for em_obj in emails:
            if isinstance(em_obj, dict):
                email = _s(em_obj.get("address") or em_obj.get("email"))
            else:
                email = _s(em_obj)
            if is_valid_email(email):
                result.emails.append(EmailRecord(
                    codigo_pessoa=codigo, tipo_pessoa=tipo,
                    email=email, tipo_email="",
                ))

    def _add_org(self, org: dict, codigo: str, tipo: str, result: ExtractionResult, add_contacts: bool = True) -> None:
        address_raw = _s(org.get("address") or org.get("endereco"))
        if "," in address_raw:
            endereco = address_raw.split(",", 1)[0].strip()
            numero = address_raw.rsplit(",", 1)[-1].strip()
        else:
            endereco = address_raw
            numero = ""

        cidade = _s(org.get("city") or org.get("cidade"))
        if cidade.lower() == "não informado":
            cidade = ""
        cep = re.sub(r"\D", "", _s(org.get("zipcode") or org.get("cep")))
        estado = _s(org.get("state") or org.get("uf") or org.get("estado"))
        cidade, estado = fill_city_state(cep, cidade, estado)
        if not is_valid_cep(cep) and cidade and estado:
            cep = lookup_cep_by_city(cidade, estado) or ""

        p = PersonRecord()
        p.codigo = codigo
        p.tipo = tipo
        p.nome = _s(org.get("name") or org.get("nome"))
        p.cnpj = re.sub(r"\D", "", _s(org.get("cnpj") or org.get("tax_id")))
        p.cep = cep
        p.cidade = cidade
        p.bairro = _s(org.get("neighborhood") or org.get("bairro"))
        p.estado = estado
        p.endereco = endereco
        p.numero = numero
        p.observacao = _s(org.get("notes") or org.get("observacao"))
        p.imobiliaria = "1"
        result.persons.append(p)

        if not add_contacts:
            return

        numbers = _parse_flat_list(org.get("phone.number"))
        types = _parse_flat_list(org.get("phone.type"))
        for i, num in enumerate(numbers):
            digits = re.sub(r"\D", "", _s(num))
            if digits.startswith("55") and len(digits) > 11:
                digits = digits[2:]
            parsed = processar_telefone(digits)
            if parsed:
                result.phones.append(PhoneRecord(
                    codigo_pessoa=codigo, tipo_pessoa=tipo,
                    ddi=parsed["ddi"], ddd=parsed["ddd"],
                    telefone=parsed["numero"], tipo_telefone=parsed["tipo"],
                ))

        emails = _parse_flat_list(org.get("email") or org.get("emails"))
        for em_obj in emails:
            email = _s(em_obj.get("address") if isinstance(em_obj, dict) else em_obj)
            if is_valid_email(email):
                result.emails.append(EmailRecord(
                    codigo_pessoa=codigo, tipo_pessoa=tipo,
                    email=email, tipo_email="",
                ))
