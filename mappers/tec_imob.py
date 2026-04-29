from __future__ import annotations
import hashlib
import html
import re
import unicodedata
from typing import Any

from core.base_mapper import BaseMapper, ExtractionResult, PersonRecord, EmailRecord, PhoneRecord
from core.cep_lookup import fill_city_state, is_valid_cep, lookup_cep_by_city
from core.characteristics_utils import build_sim_nao, map_characteristics_to_fields
from core.phone_utils import processar_telefone, is_valid_email
from core.property_records import (
    PropertyRecord, PropertyOwnerRecord, PropertyOwnerFavoredRecord,
    PropertyCaptivatorRecord, PropertyIptuRecord,
    PropertyExtractionResult, normalize_address,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _md5(s: str) -> str:
    return hashlib.md5(s.encode("utf-8")).hexdigest()[:16].upper()


def _v(row: dict, *keys: str) -> str:
    """Return first non-empty value matching any of the given keys."""
    for k in keys:
        v = row.get(k)
        if v is not None:
            s = str(v).strip()
            if s and s.lower() not in ("none", "nan"):
                return s
    return ""


def _ascii_lower(s: str) -> str:
    """Strip accents and lowercase — used for dict lookups."""
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def _sim_nao(v: str) -> str:
    v = (v or "").strip().lower()
    if v == "sim":
        return "Sim"
    if v in ("não", "nao"):
        return "Não"
    return ""


def _bin(v: str) -> str:
    """Return '1' if value is 'Sim', '0' otherwise. Used for boolean CSV columns."""
    return "1" if (v or "").strip().lower() == "sim" else "0"


def _fmt_price(v: Any) -> str:
    """Parse 'R$180.000,00' → '180000.00'. Returns '' for zero/invalid."""
    v = re.sub(r"[R$\s]", "", str(v or "").strip())
    # Brazilian format: remove thousands dots, replace decimal comma
    v = v.replace(".", "").replace(",", ".")
    try:
        f = float(v)
        return f"{f:.2f}" if f else ""
    except (ValueError, TypeError):
        return ""


def _parse_medidas(v: str) -> dict[str, str]:
    """Parse 'Área Total: 60,00 m². Área Privativa: 60,00 m².' → {'total': '60.00', ...}"""
    result: dict[str, str] = {}
    for m in re.finditer(r"[Áa]rea\s+([\w\s]+?):\s*([\d.,]+)\s*m", v or "", re.IGNORECASE):
        label = _ascii_lower(m.group(1).strip())
        val = m.group(2).replace(".", "").replace(",", ".")
        try:
            result[label] = f"{float(val):.2f}"
        except ValueError:
            pass
    return result


def _parse_date(v: Any) -> str:
    """DD/MM/YYYY → YYYY-MM-DD"""
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", str(v or ""))
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else str(v or "")


def _strip_html(v: str) -> str:
    v = re.sub(r"<[^>]+>", " ", v or "")
    v = html.unescape(v)
    return re.sub(r"\s+", " ", v).strip()


# ── Lookup tables ─────────────────────────────────────────────────────────────

_TIPO_PESSOA_MAP = {
    "proprietário": "OW",
    "proprietario": "OW",
    "comprador": "BU",
    "locatário": "OC",
    "locatario": "OC",
}

_TRANSACAO_MAP = {
    "VENDA": "S",
    "ALUGUEL": "L",
    "LOCAÇÃO": "L",
    "LOCACAO": "L",
    "VENDA/LOCAÇÃO": "SL",
    "VENDA E LOCAÇÃO": "SL",
}

# Tec Imob Tipo + Subtipo (ascii-lower) → SUBCATEGORIAS ID
_TIPO_SUBTIPO_SUB: dict[tuple[str, str], int] = {
    # Apartamentos
    ("apartamento", "padrao"):           1,
    ("apartamento", "linear"):           1,
    ("apartamento", "em edificio"):      1,
    ("apartamento", "vila"):             1,
    ("apartamento", "comercial"):        1,
    ("apartamento", "cobertura"):        2,
    ("apartamento", "cobertura linear"): 2,
    ("apartamento", "penthouse"):        2,
    ("apartamento", "flat"):             3,
    ("apartamento", "duplex"):           5,
    ("apartamento", "triplex"):          6,
    ("apartamento", "loft"):             33,
    ("apartamento", "garden"):           43,
    ("apartamento", "studio"):           46,
    ("apartamento", "cobertura duplex"): 65,
    ("apartamento", "alto padrao"):      72,
    # Casas
    ("casa", "padrao"):                  7,
    ("casa", "linear"):                  7,
    ("casa", "com area externa"):        7,
    ("casa", "vila"):                    7,
    ("casa", "em condominio"):           10,
    ("casa", "chale"):                   47,
    ("casa", "alto padrao"):             69,
    # Comercial
    ("sala", "padrao"):                  11,
    ("sala", "salao comercial"):         12,
    ("sala comercial", "padrao"):        11,
    ("salao comercial", "padrao"):       12,
    ("ponto comercial", "padrao"):       31,
    ("ponto comercial", "comercio"):     31,
    ("predio", "padrao"):                14,
    ("predio", "comercial"):             14,
    # Terreno
    ("terreno", "padrao"):               21,
    ("terreno", "lote"):                 23,
    ("terreno", "terreno"):              21,
    ("terreno", "comercial"):            27,
    ("terreno", "comercio"):             27,
}

_TIPO_SUB_DEFAULT: dict[str, int] = {
    "apartamento":     1,
    "casa":            7,
    "sala":            11,
    "sala comercial":  11,
    "salao comercial": 12,
    "ponto comercial": 31,
    "predio":          14,
    "terreno":         21,
}


def _sub_categoria(tipo: str, subtipo: str) -> str:
    t = _ascii_lower(tipo)
    s = _ascii_lower(subtipo)
    v = _TIPO_SUBTIPO_SUB.get((t, s)) or _TIPO_SUB_DEFAULT.get(t, 7)
    return str(v)


# ── Mapper ────────────────────────────────────────────────────────────────────

class TecImobMapper(BaseMapper):
    NAME = "Tec Imob"
    EXTENSIONS = [".xlsx"]
    DESCRIPTION = "Tec Imob (XLSX multi-aba)"

    def can_handle(self, filename: str) -> bool:
        return filename.lower().endswith(".xlsx")

    def extract(self, data: Any) -> ExtractionResult:
        result = ExtractionResult()
        seen: set[str] = set()

        sheets: dict[str, list[dict]] = data if isinstance(data, dict) else {"": data}

        # Índices para correlacionar Proprietário do imóvel com Clientes
        person_by_hash: dict[str, PersonRecord] = {}   # MD5(nome-first_phone) → pessoa
        person_by_name: dict[str, PersonRecord] = {}   # nome → pessoa (fallback)

        # ── Clientes ──────────────────────────────────────────────────────────
        clientes_rows: list[dict] = []
        for k in sheets:
            if _ascii_lower(k) == "clientes":
                clientes_rows = sheets[k]
                break
        if not clientes_rows:
            for k in sheets:
                if "cliente" in _ascii_lower(k):
                    clientes_rows = sheets[k]
                    break
        if not clientes_rows:
            clientes_rows = next(iter(sheets.values()), [])

        for row in clientes_rows:
            nome = _v(row, "Nome", "NOME", "nome")
            if not nome:
                continue

            # codigo = MD5(Nome + '-' + Telefones) — hex 32 chars, igual ao SQL
            telefones_raw = _v(row, "Telefones")
            codigo = hashlib.md5(f"{nome}-{telefones_raw}".encode("utf-8")).hexdigest()

            # tipo via LIKE (correspondência parcial no campo Categorias)
            cat = _ascii_lower(_v(row, "Categorias", "Categoria", "categoria", "CATEGORIA"))
            if "proprietario" in cat:
                tipo = "OW"
            elif "comprador" in cat:
                tipo = "BU"
            elif "locatario" in cat:
                tipo = "OC"
            else:
                tipo = "BU"

            key = f"{codigo}|{tipo}"
            if key in seen:
                continue
            seen.add(key)

            # Telefones — campo "Telefones" principal; Celular e Telefone 2 como extras
            tels_raw = [
                telefones_raw,
                _v(row, "Celular", "CEL", "CELULAR"),
                _v(row, "Telefone 2", "Tel2", "TELEFONE2"),
            ]
            phones_parsed: list[dict] = []
            for raw in tels_raw:
                if not raw:
                    continue
                digits = re.sub(r"\D", "", raw)
                if digits.startswith("55") and len(digits) > 11:
                    digits = digits[2:]
                parsed = processar_telefone(digits)
                if parsed:
                    phones_parsed.append(parsed)

            cpf_cnpj_raw = re.sub(r"\D", "", _v(row, "CPF/CNPJ", "CPF", "cpf"))
            cpf_val = cpf_cnpj_raw if len(cpf_cnpj_raw) == 11 else ""
            cnpj_val = cpf_cnpj_raw if len(cpf_cnpj_raw) == 14 else re.sub(r"\D", "", _v(row, "CNPJ", "cnpj"))

            sal_raw = _v(row, "Renda total", "Renda", "salario", "Salario")

            p = PersonRecord()
            p.codigo = codigo
            p.tipo = tipo
            p.nome = nome
            p.nome_fantasia = nome          # razao_social = Nome
            p.cpf = cpf_val
            p.cnpj = cnpj_val
            p.rg = _v(row, "RG", "rg")
            p.data_nascimento = _v(row, "Nascimento", "Data Nascimento", "DtNascimento")
            p.sexo = ""                     # sempre vazio conforme mapeamento
            p.estado_civil = _v(row, "Estado Civil", "EstadoCivil")
            p.profissao = _v(row, "Profissão", "Profissao", "profissao")
            p.salario = sal_raw.replace(",", ".") if sal_raw else ""
            p.observacao = ""               # sempre vazio conforme mapeamento
            p.como_chegou = _v(row, "Origem", "origem")
            p.imobiliaria = "1"
            p.cobrar_taxa_bco = "0"
            p.cep = re.sub(r"\D", "", _v(row, "CEP", "Cep", "cep"))
            p.cidade = _v(row, "Cidade", "cidade")
            p.bairro = _v(row, "Bairro", "bairro")
            p.estado = _v(row, "Estado", "UF", "estado")
            p.endereco = _v(row, "Logradouro", "Endereco", "Endereço", "endereco")
            p.numero = _v(row, "Número", "Numero", "numero")
            p.complemento = _v(row, "Complemento", "complemento")

            result.persons.append(p)

            # Indexa pelo MD5(nome-primeiro_telefone) para match com Proprietário do imóvel
            telefones_raw = _v(row, "Telefones")
            first_tel = telefones_raw.split(",")[0].strip() if telefones_raw else ""
            ph_hash = hashlib.md5(f"{nome}-{first_tel}".encode("utf-8")).hexdigest()
            if ph_hash not in person_by_hash:
                person_by_hash[ph_hash] = p
            if nome and nome not in person_by_name:
                person_by_name[nome] = p

            for ph in phones_parsed:
                result.phones.append(PhoneRecord(
                    codigo_pessoa=codigo,
                    tipo_pessoa=tipo,
                    ddi=ph["ddi"],
                    ddd=ph["ddd"],
                    telefone=ph["numero"],
                    tipo_telefone=ph["tipo"],
                ))

            email = _v(row, "E-mail", "Email", "email")
            if is_valid_email(email):
                result.emails.append(EmailRecord(
                    codigo_pessoa=codigo,
                    tipo_pessoa=tipo,
                    email=email,
                    tipo_email="",
                ))

        # ── Imóveis ───────────────────────────────────────────────────────────
        imoveis_rows: list[dict] = []
        for k in sheets:
            ak = _ascii_lower(k)
            if ak in ("imoveis", "imovel"):
                imoveis_rows = sheets[k]
                break
        if not imoveis_rows:
            for k in sheets:
                ak = _ascii_lower(k)
                if "im" in ak and ("vel" in ak or "veis" in ak):
                    imoveis_rows = sheets[k]
                    break

        if imoveis_rows:
            result.property_result = self._extract_imoveis(
                imoveis_rows, person_by_hash, person_by_name
            )

        return result

    # ── Property extraction ───────────────────────────────────────────────────

    def _extract_imoveis(
        self,
        rows: list[dict],
        person_by_hash: dict[str, PersonRecord],
        person_by_name: dict[str, PersonRecord],
    ) -> PropertyExtractionResult:
        prop_result = PropertyExtractionResult()
        imob_doc = re.sub(r"\D", "", self.context.get("imob_cpf_cnpj", ""))

        for row in rows:
            # Skip deleted / inactive properties
            status_raw = _v(row, "Status")
            if _ascii_lower(status_raw) in ("excluido", "excluído"):
                continue

            codigo = _v(row, "Referencia", "ID", "id")
            if not codigo:
                continue

            # Tipo: VENDA→S, qualquer outro (ALUGUEL etc.)→L
            transacao = _ascii_lower(_v(row, "Transação", "Transacao"))
            tipo = "S" if transacao == "venda" else "L"

            tipo_imovel = _v(row, "Tipo")
            subtipo = _v(row, "Subtipo")
            sub_cat = _sub_categoria(tipo_imovel, subtipo)

            preco = _fmt_price(_v(row, "Preço", "Preco", "Preço"))

            pr = PropertyRecord()
            pr.codigo = str(codigo)
            pr.imobiliaria = "1"
            # Status: 1=Ativo/Disponível, 5=outros
            pr.status = "1" if _ascii_lower(status_raw) in ("disponivel", "ativos", "ativo") else "5"
            pr.tipo = tipo
            pr.sub_categoria = sub_cat

            if tipo == "S":
                pr.valor_venda = preco
            else:
                pr.valor_locacao = preco

            pr.data_registro = _parse_date(_v(row, "Data de Cadastro"))
            pr.titulo_site = _nfc(_v(row, "Título", "Titulo"))
            pr.matricula = _v(row, "Matrícula", "Matricula")

            # obs_site = Descrição (HTML stripped)
            pr.obs_site = _nfc(_strip_html(_v(row, "Descrição", "Descricao", "Descrição")))

            # observacao = concat rico com metadados do imóvel
            _obs: list[str] = [f"Ref: {codigo}"]
            def _oa(label: str, *keys: str) -> None:
                v = _v(row, *keys)
                if v:
                    _obs.append(f"{label}: {v}")
            def _oa_sim(label: str, *keys: str) -> None:
                if _sim_nao(_v(row, *keys)) == "Sim":
                    _obs.append(f"{label}: Sim")

            _oa("Data de Atualização",   "Data de Atualização", "Data de Atualizacao")
            _oa("Corretor",              "Corretor")
            _oa("Agenciador",            "Agenciador")
            _oa("Obs Privada",           "Observação Privada", "Observacao Privada")
            _oa("Cond",                  "Descrição Condomínio", "Descricao Condominio")
            _oa("Tipo do imóvel aceito", "Tipo de imóvel aceito", "Tipo de imovel aceito")
            _oa_sim("Minha casa minha vida", "Minha casa minha vida", "MCMV")
            _oa_sim("Averbado",          "Averbado")
            _oa_sim("Chave disponível",  "Chave Disponível", "Chave Disponivel")
            _oa_sim("Com placa",         "Com placa")
            _oa_sim("Escriturada",       "Escriturado")
            _oa("Proximidades",          "Proximidades")
            _oa("Valor máximo da permuta","Valor máximo da permuta", "Valor maximo da permuta")
            _oa("Permuta",               "Descrição Permuta", "Descricao Permuta")
            _oa("Taxas",                 "Total das Taxas", "Total das taxas")
            _oa("Descrição Taxas",       "Descrição das Taxas", "Descricao das Taxas")
            _oa("Negociação",            "Observação da Negociação", "Observacao da Negociacao")
            anot = _strip_html(_v(row, "Anotações", "Anotacoes"))
            if anot:
                _obs.append(f"Anotações: {anot}")
            _oa("Descrição do lote",     "Descrição do Lote", "Descricao do Lote")
            pr.observacao = _nfc(" - ".join(_obs))

            ano = _v(row, "Ano de Construção", "Ano de Contrução", "Ano de Construcao")
            pr.ano_construcao = str(ano).strip() if ano else ""

            # Visibility / flags — 1 ou 0
            pr.mostrar_site = _bin(_v(row, "Mostra no Site"))
            pr.destaque     = _bin(_v(row, "Página Inicial", "Pagina Inicial"))
            pr.street_view  = _bin(_v(row, "Mostra StreetView", "Mostra Streetview"))
            pr.mapa_site    = _bin(_v(row, "Mostra Mapa"))

            # Exclusividade: condicional por tipo de transação
            excl_sim = _ascii_lower(_v(row, "Exclusividade")) == "sim"
            pr.venda_exclusiva   = "1" if excl_sim and tipo == "S" else "0"
            pr.locacao_exclusiva = "1" if excl_sim and tipo == "L" else "0"

            ocup = _v(row, "Ocupação", "Ocupacao")
            pr.ocupado = "1" if ocup else "0"

            # IPTU
            iptu_val = _fmt_price(_v(row, "Preço do IPTU", "Preco do IPTU"))
            if iptu_val:
                periodo = _ascii_lower(_v(row, "Período IPTU", "Periodo IPTU"))
                if "mensal" in periodo:
                    pr.valor_mensal_iptu = iptu_val
                else:
                    pr.valor_anual_iptu = iptu_val

            pr.valor_condominio = _fmt_price(
                _v(row, "Preço do Condomínio", "Preco do Condominio", "Preço do Condomínio")
            )

            # Address
            cep = re.sub(r"\D", "", _v(row, "Cep", "CEP", "cep"))
            cidade = _v(row, "Cidade")
            estado = _v(row, "Estado")
            apto_raw = _v(row, "N. Apartamento/Sala")
            andar_raw = str(_v(row, "Andar") or "")
            cond_nome = _v(row, "Nome Condomínio", "Nome Condominio")

            # Complemento: Complemento original + Cond. + Nº apto./sala + Andar
            bairro, rua, numero, comp_base = normalize_address(
                _v(row, "Bairro"),
                _v(row, "Logradouro"),
                str(_v(row, "Número", "Numero") or ""),
                _v(row, "Complemento"),
            )
            complemento = comp_base
            if cond_nome:
                complemento += f" Cond. {cond_nome}"
            if apto_raw:
                complemento += f" Nº apto./sala: {apto_raw}"
            if andar_raw:
                complemento += f" Andar: {andar_raw}"

            filled = fill_city_state(cep, cidade, estado)
            if filled:
                cidade, estado = filled

            # Fallback: CEP ausente ou 00000000 → busca o CEP geral da cidade/UF (sufixo 000)
            if not is_valid_cep(cep) and cidade and estado:
                cep = lookup_cep_by_city(cidade, estado) or ""

            pr.cep = cep
            pr.cidade = _nfc(cidade)
            pr.estado = estado
            pr.bairro = _nfc(bairro)
            pr.rua = _nfc(rua)
            pr.numero_end = numero
            pr.complemento = _nfc(complemento.strip())

            # Condo/floor dedicated fields
            pr.num_apto = apto_raw
            pr.num_piso = andar_raw

            # Rooms
            pr.dormitorios = str(_v(row, "Dormitórios", "Dormitorios") or "")
            pr.suites = str(_v(row, "Suítes", "Suites") or "")
            pr.garagem = str(_v(row, "Garagens") or "")
            pr.garagem_coberta = _bin(_v(row, "Garagem coberta"))
            pr.banheiros = str(_v(row, "Banheiros") or "")
            pr.lavabos = str(_v(row, "Lavabo") or "")
            pr.lavanderias = str(_v(row, "Área de serviço", "Area de servico") or "")
            pr.cozinhas = str(_v(row, "Cozinha") or "")
            pr.closets = str(_v(row, "Closet") or "")
            pr.escritorio = str(_v(row, "Escritório", "Escritorio") or "")
            pr.dorm_funcionario = str(_v(row, "Dependência de serviço", "Dependencia de servico") or "")
            pr.copas = str(_v(row, "Copa") or "")

            # Sum all sala variants into a single count
            sala_total = 0
            for sk in ("Sala de TV", "Sala de Jantar", "Sala de estar"):
                sv = _v(row, sk)
                if sv:
                    try:
                        sala_total += int(float(sv))
                    except (ValueError, TypeError):
                        pass
            if sala_total:
                pr.salas = str(sala_total)

            # Areas — priority chains from "Medidas" free-text field:
            #   area_util:      Privativa → Construída → Total
            #   area_total:     Total     → Privativa  → Construída
            #   area_construida:Construída→ Privativa  → Total
            medidas = _parse_medidas(_v(row, "Medidas"))
            privativa  = medidas.get("privativa", "")
            total      = medidas.get("total", "")
            construida = next((medidas[k] for k in medidas if "constru" in k), "")
            pr.area_util      = privativa  or construida or total
            pr.area_total     = total      or privativa  or construida
            pr.area_construida= construida or privativa  or total

            # Geo-coordinates
            lat = _v(row, "Latitude")
            lon = _v(row, "Longitude")
            pr.latitude = str(lat) if lat else ""
            pr.longitude = str(lon) if lon else ""

            # Characteristics (property + condo combined)
            all_chars: list[str] = []
            for char_col in (
                "Características", "Caracteristicas",
                "Características do condomínio", "Caracteristicas do condominio",
            ):
                cs = _v(row, char_col)
                if cs:
                    all_chars.extend(c.strip() for c in cs.split("|") if c.strip())

            pr.caracteristicas_sim_nao = build_sim_nao(all_chars)
            for field, qty in map_characteristics_to_fields(all_chars).items():
                if not getattr(pr, field, ""):
                    setattr(pr, field, qty)

            prop_result.properties.append(pr)

            # ── IPTU ──────────────────────────────────────────────────────────
            # Emite registro apenas quando há valor de IPTU > 0.
            # Valor vai sempre para valor_mensal_iptu; anual = 0.
            iptu_rec_val = _fmt_price(_v(row, "Preço do IPTU", "Preco do IPTU"))
            if iptu_rec_val and float(iptu_rec_val) > 0:
                prop_result.iptu.append(PropertyIptuRecord(
                    codigo_imovel=str(codigo),
                    tipo_iptu="IPTU Principal",
                    inscricao_iptu="",
                    valor_mensal_iptu=iptu_rec_val,
                    valor_anual_iptu="0",
                    parcelas_iptu="0",
                    perc_iptu="100",
                    obs_iptu="",
                ))

            # ── Owner lookup ──────────────────────────────────────────────────
            # Tenta casar Proprietário + Celular do Proprietário com a aba Clientes
            # via MD5(nome-primeiro_telefone), com fallback por nome exato.
            prop_nome = _v(row, "Proprietário", "Proprietario")
            prop_cel  = re.sub(r"[ \-)(]", "", _v(row, "Celular do Proprietário", "Celular do Proprietario"))
            owner_key = hashlib.md5(f"{prop_nome}-{prop_cel}".encode("utf-8")).hexdigest()

            person = person_by_hash.get(owner_key) or person_by_name.get(prop_nome)

            if person:
                ow_cpf    = person.cpf
                ow_cnpj   = "" if person.cpf else person.cnpj
                ow_codigo = person.codigo
                ow_nome   = person.nome
            else:
                ow_cpf    = ""
                ow_cnpj   = imob_doc
                ow_codigo = ""
                ow_nome   = prop_nome

            prop_result.owners.append(PropertyOwnerRecord(
                codigo_imovel=str(codigo),
                cpf=ow_cpf,
                cnpj=ow_cnpj,
                codigo_pessoa=ow_codigo,
                percentual="100",
            ))

            # ── Owner favored ─────────────────────────────────────────────────
            prop_result.owners_favored.append(PropertyOwnerFavoredRecord(
                codigo_imovel=str(codigo),
                cpf=ow_cpf,
                cnpj=ow_cnpj,
                codigo_pessoa=ow_codigo,
                tipo_pagamento="M",
                percentual="100",
                cpf_favorecido=ow_cpf,
                cnpj_favorecido=ow_cnpj,
                id_favorecido=ow_codigo,
                favorecido=ow_nome,
                banco="",
                agencia="",
                digito_agencia="",
                conta="",
                digito_conta="",
                poupanca="0",
            ))

            # ── Captivador ────────────────────────────────────────────────────
            # Emite apenas quando Corretor ou Agenciador estiver preenchido e
            # diferente de 'Sem agenciador' (replica o UNION DISTINCT do SQL).
            corretor_val   = _v(row, "Corretor")
            agenciador_val = _v(row, "Agenciador")
            has_captivator = (
                corretor_val   and _ascii_lower(corretor_val)   != "sem agenciador"
            ) or (
                agenciador_val and _ascii_lower(agenciador_val) != "sem agenciador"
            )
            if imob_doc and has_captivator:
                prop_result.captivators.append(PropertyCaptivatorRecord(
                    codigo_imovel=str(codigo),
                    cpf_cnpj=imob_doc,
                    departamento=tipo,
                    data_captacao=pr.data_registro,
                ))

        return prop_result
