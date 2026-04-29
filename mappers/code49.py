from __future__ import annotations
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


# ── Subcategoria — mapeamento por DESCRICAO da categoria ──────────────────────

# Categoria DESCRICAO → subcategoria ID Msys (idêntico ao SQL de migração)
_CAT_DESC_SUBCAT: dict[str, str] = {
    "Andar Comercial":           "11",
    "Andar |Conjuntos |Salas":   "11",
    "Terreno em condomínio":     "22",
    "Casa Vila & Condomínio":    "10",
    "Cobertura":                 "2",
    "Kitnet / Studio":           "4",
    "Área para Incorporação":    "23",
    "Flat":                      "3",
    "Chácara | Sitio | Fazenda": "56",
    "Loja":                      "25",
    "Casas |Sobrados |Prédios":  "8",
    "Casas & Sobrados":          "8",
    "Área":                      "28",
    "Apartamento":               "1",
    "Bangalô":                   "7",
    "Barracão":                  "41",
    "Casa":                      "7",
    "Casa em condomínio":        "10",
    "Chácara":                   "16",
    "Fazenda":                   "17",
    "Galpão":                    "41",
    "Sobrado":                   "57",
    "Sala":                      "11",
    "Salão Comercial":           "12",
    "Terreno":                   "21",
    "Villagio":                  "12",
}

# TIPOINTERNO DESCRICAO → subcategoria ID (fallback)
_TIPO_DESC_SUBCAT: dict[str, str] = {
    "Apartamento": "1",
    "Casa":        "7",
    "Comercial":   "11",
    "Rural":       "16",
    "Terreno":     "21",
}


def _resolve_subcat(cat_desc: str, tipo_desc: str) -> str:
    """Custom override → cat dict → tipo dict → '7' (Casa Padrão)."""
    custom = get_custom_subcat(cat_desc, tipo_desc)
    if custom is not None:
        return custom
    return _CAT_DESC_SUBCAT.get(cat_desc, _TIPO_DESC_SUBCAT.get(tipo_desc, "7"))


# ── Características: ID de característica → nome Msys para CARACTSIMNAO ──────
# (IDs extraídos do SQL de migração Code49)

_SIMNAO_CHAR_IDS: list[tuple[str, set[int]]] = [
    ("Alarme",                      {87, 143, 241}),
    ("Adega",                       {313, 402, 494, 551}),
    ("Aquecedor solar",             {91, 240}),
    ("Ar-condicionado",             {25, 81, 138, 141, 260}),
    ("Campo de futebol",            {182, 324, 385, 477, 534, 572}),
    ("Carpete",                     {39, 42, 108, 111, 146, 149, 268}),
    ("Casa para caseiro",           {164}),
    ("Cerca",                       {166, 198}),
    ("Cerca elétrica",              {356, 375, 425, 467, 524}),
    ("Churrasqueira",               {15, 95, 162, 179, 281, 325, 387, 479, 536, 573}),
    ("Edícula",                     {68, 114, 208}),
    ("Elevadores",                  {357}),
    ("Espaço Gourmet",              {327}),
    ("Home office",                 {600}),
    ("Guarita",                     {302, 363, 367, 374, 424, 429, 459, 466, 516, 523}),
    ("Hidro",                       {27, 77, 251}),
    ("Jardim",                      {99, 158, 186, 277, 574}),
    ("Lareira",                     {14, 53, 223}),
    ("Mezanino",                    {62, 117, 214}),
    ("Mobília",                     {115}),
    ("Piscina",                     {98, 159, 185, 278, 322, 378, 470, 527, 577, 590}),
    ("Piscina Aquecida",            {194, 333, 386, 478, 535, 578}),
    ("Piscina infantil",            {183, 334, 394, 486, 543, 579}),
    ("Portão eletrônico",           {93, 136, 252}),
    ("Quadra de squash",            {196, 338, 400, 492, 549, 582}),
    ("Quadra de tênis",             {188, 339, 392, 484, 541, 583}),
    ("Quadra Poliesportiva",        {103, 154, 192, 273, 340, 384, 476, 533, 584}),
    ("Quintal",                     {102, 155, 274}),
    ("Sauna",                       {101, 156, 191, 275, 318, 388, 480, 537, 589}),
    ("Sauna úmida",                 {96, 161, 180, 280, 319, 396, 488, 545, 588}),
    ("Solarium",                    {320, 381, 436, 473, 530}),
    ("Terraço",                     {7, 54, 222}),
    ("Varanda",                     {22, 71, 205}),
    ("Área de serviço",             {19, 67, 112, 209}),
    ("Cozinha americana",           {3, 49, 227}),
    ("Armário embutido",            {30, 75, 249}),
    ("Condominio fechado",          {641}),
    ("Energia elétrica",            {167, 199, 217}),
    ("Entrada lateral",             {59, 123}),
    ("Estacionamento rotativo",     {299, 352, 446}),
    ("Gás encanado",                {300}),
    ("Casas",                       {55, 221}),         # Geminada
    ("Piso laminado",               {40, 110, 147}),
    ("Piso frio",                   {43, 107, 150}),
    ("Playground",                  {190, 337, 401, 441, 493, 550, 581}),
    ("Porcelanato",                 {591}),
    ("Sala de TV",                  {1, 47, 229}),
    ("Salão de Festas",             {97, 160, 181, 279, 332, 398, 437, 490, 547, 586}),
    ("Salão de Jogos",              {100, 157, 187, 276, 317, 390, 440, 482, 539, 587}),
    ("Sala de ginástica",           {195, 341, 382, 474, 531, 585}),
    ("Sala de massagem",            {314, 397, 489, 546}),
    ("Ventilador",                  {254}),
    ("Piso de madeira",             {45, 105, 152, 271}),
    ("Piscina com raia",            {194, 578}),
    ("Portaria 24 Hrs",             {615, 620}),
    ("Entrada de serviço independente", {124}),
    ("Aquecimento",                 {33, 79, 84}),
    ("Lobby com pé direito duplo",  {6, 70, 206}),
    ("Gerador elétrico",            {142, 301, 366, 428, 458, 515}),
    ("Internet wireless",           {38}),
    ("Muro",                        {593}),
    ("Asfalto",                     {176, 202, 369, 431, 461, 518}),
    ("Geminada",                    {55, 221}),
]

# Campo estruturado do PropertyRecord → IDs de característica Code49 que ativam o campo (valor "1")
_FIELD_CHAR_IDS: dict[str, set[int]] = {
    "closets":              {5, 13, 52, 69, 207, 224},
    "copas":                {11, 58, 113, 218},
    "cozinhas":             {18, 66, 122, 210},
    "despensas":            {4, 50, 226},
    "lavanderias":          {12, 51, 225},
    "halls":                {16},
    "dorm_funcionario":     {8, 72, 204},
    "banheiro_funcionario": {23, 63, 213},
    "escritorio":           {21, 61, 119, 215},
    "depositos":            {24, 120, 596},
    "poco_artesiano":       {94, 130, 177, 253, 292},
    "lago":                 {184, 395, 487, 544, 575},
    "canil":                {89, 144, 178, 238, 293},
    "casa_sede":            {165},
    "galpao":               {169},
}


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
            cid  = _txt(c, "ID") or _txt(c, "IDCIDADE")
            nome = _txt(c, "CIDADE")
            sigla = _txt(c, "SIGLA")
            if cid:
                cidades[cid] = (nome, sigla)

        bairros: dict[str, str] = {}               # id → nome
        for b in root.findall(".//BAIRROS/BAIRRO"):
            bid  = _txt(b, "ID")
            nome = _txt(b, "BAIRRO")
            if bid:
                bairros[bid] = nome

        categorias: dict[str, str] = {}            # id → descricao
        for c in root.findall(".//CATEGORIAS/CATEGORIA"):
            cid  = _txt(c, "ID")
            desc = _txt(c, "DESCRICAO")
            if cid:
                categorias[cid] = desc

        tipos_internos: dict[str, str] = {}        # id → descricao
        for t in root.findall(".//TIPOSINTERNOS/TIPOINTERNO"):
            tid  = _txt(t, "ID")
            desc = _txt(t, "DESCRICAO")
            if tid:
                tipos_internos[tid] = desc

        condominios: dict[str, str] = {}           # id → nome empreendimento
        for c in root.findall(".//CONDOMINIOS/CONDOMINIO"):
            cid  = _txt(c, "ID")
            nome = _txt(c, "EMPREENDIMENTO") or _txt(c, "NOME")
            if cid:
                condominios[cid] = nome

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

        # CARAC_IMOVEL: imovel_id → set[char_id_int] (para mapeamento direto por ID)
        imovel_char_ids: dict[str, set[int]] = {}
        for ic in root.findall(".//CARAC_IMOVEL/DESCRICAO"):
            imovel_id   = _txt(ic, "ID_IMOVEL")
            char_id_str = _txt(ic, "ID_CARACTERISTICA")
            try:
                char_id_int = int(char_id_str)
            except (ValueError, TypeError):
                continue
            if imovel_id:
                imovel_char_ids.setdefault(imovel_id, set()).add(char_id_int)

        # Proprietários de imóveis (para classificar tipo OW vs BU)
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
            root, cidades, bairros, categorias, tipos_internos,
            condominios, clientes_info, imovel_char_ids,
        )
        return result

    # ── Scan hooks ────────────────────────────────────────────────────────────

    def scan_characteristics(self, data: ET.Element) -> set[str]:
        """Retorna nomes de características presentes nos imóveis via CARAC_IMOVEL."""
        # Reconstrói o mapeamento id→nome a partir do XML (igual ao extract)
        char_names: set[str] = set()
        char_id_to_name: dict[int, str] = {}
        for _, ids_set in _SIMNAO_CHAR_IDS:
            # Mapear pelo mapeamento canônico — não há names extras aqui
            pass

        # Monta char_id → canonical_name via _SIMNAO_CHAR_IDS (reverso)
        for canonical_name, ids_set in _SIMNAO_CHAR_IDS:
            for cid in ids_set:
                char_id_to_name.setdefault(cid, canonical_name)

        imovel_char_ids_scan: dict[str, set[int]] = {}
        for ic in data.findall(".//CARAC_IMOVEL/DESCRICAO"):
            imovel_id   = _txt(ic, "ID_IMOVEL")
            char_id_str = _txt(ic, "ID_CARACTERISTICA")
            try:
                char_id_int = int(char_id_str)
            except (ValueError, TypeError):
                continue
            if imovel_id:
                imovel_char_ids_scan.setdefault(imovel_id, set()).add(char_id_int)

        for ids_set in imovel_char_ids_scan.values():
            for cid in ids_set:
                name = char_id_to_name.get(cid)
                if name:
                    char_names.add(name)
        return char_names

    def scan_subcategories(self, data: ET.Element) -> set[str]:
        """Retorna pares 'cat_desc|tipo_desc' sem mapeamento configurado."""
        # Reconstrói categorias/tipos do XML
        categorias: dict[str, str] = {}
        for c in data.findall(".//CATEGORIAS/CATEGORIA"):
            cid  = _txt(c, "ID")
            desc = _txt(c, "DESCRICAO")
            if cid:
                categorias[cid] = desc
        tipos_internos: dict[str, str] = {}
        for t in data.findall(".//TIPOSINTERNOS/TIPOINTERNO"):
            tid  = _txt(t, "ID")
            desc = _txt(t, "DESCRICAO")
            if tid:
                tipos_internos[tid] = desc

        pairs: set[str] = set()
        for im in data.findall(".//IMOVEIS/IMOVEL"):
            cat_id   = _txt(im, "CATEGORIA")
            tipo_id  = _txt(im, "TIPOINTERNO")
            cat_desc  = categorias.get(cat_id, cat_id)
            tipo_desc = tipos_internos.get(tipo_id, tipo_id)
            if _resolve_subcat(cat_desc, tipo_desc) == "":
                pairs.add(f"{cat_desc}|{tipo_desc}")
        return pairs

    # ── Property extraction ───────────────────────────────────────────────────

    def _extract_properties(
        self,
        root: ET.Element,
        cidades: dict[str, tuple[str, str]],
        bairros: dict[str, str],
        categorias: dict[str, str],
        tipos_internos: dict[str, str],
        condominios: dict[str, str],
        clientes_info: dict[str, tuple[str, str, str]],
        imovel_char_ids: dict[str, set[int]],
    ) -> PropertyExtractionResult:
        prop_result = PropertyExtractionResult()

        imob_doc  = re.sub(r"\D", "", self.context.get("imob_cpf_cnpj", ""))
        imob_cpf  = imob_doc if len(imob_doc) == 11 else ""
        imob_cnpj = imob_doc if len(imob_doc) == 14 else ""
        imob_nome = self.context.get("imob_nome", "")

        # Monta reverso: char_id → nome canônico (para build_sim_nao)
        char_id_to_name: dict[int, str] = {}
        for canonical_name, ids_set in _SIMNAO_CHAR_IDS:
            for cid in ids_set:
                char_id_to_name.setdefault(cid, canonical_name)

        for im in root.findall(".//IMOVEIS/IMOVEL"):
            imovel_id = _txt(im, "ID")
            if not imovel_id:
                continue

            # ── Status: SITUACAO=0 → ativo (1); outro → inativo (5) ───────────
            try:
                situacao = int(_txt(im, "SITUACAO") or "0")
            except ValueError:
                situacao = 0
            status = "1" if situacao == 0 else "5"

            # ── Tipo (S / L / SL) ─────────────────────────────────────────────
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
            has_venda = bool({"VENDA", "LANÇAMENTO"} & transacoes) or sv > 0
            has_loc   = "LOCACAO" in transacoes or rv > 0
            tipo = "SL" if has_venda and has_loc else ("L" if has_loc else "S")

            # ── Subcategoria ──────────────────────────────────────────────────
            cat_id    = _txt(im, "CATEGORIA")
            tipo_id   = _txt(im, "TIPOINTERNO")
            cat_desc  = categorias.get(cat_id, "")
            tipo_desc = tipos_internos.get(tipo_id, "")
            sub_cat   = _resolve_subcat(cat_desc, tipo_desc)

            # ── Data ─────────────────────────────────────────────────────────
            data_raw = _txt(im, "DATA")
            data_registro = data_raw[:10] if data_raw else date.today().isoformat()

            # ── Finalidade ────────────────────────────────────────────────────
            finalidades = {
                (f.text or "").strip().upper()
                for f in im.findall("FINALIDADES/FINALIDADE")
            }
            if "COMERCIAL" in finalidades and finalidades & {"RURAL", "RESIDENCIAL"}:
                finalidade = "Comercial/Residencial"
            elif "COMERCIAL" in finalidades and "INDUSTRIAL" in finalidades:
                finalidade = "Comercial/Industrial"
            elif finalidades & {"RESIDENCIAL", "RURAL"}:
                finalidade = "Residencial"
            elif "COMERCIAL" in finalidades:
                finalidade = "Comercial"
            elif "INDUSTRIAL" in finalidades:
                finalidade = "Industrial"
            else:
                finalidade = "Não residencial"

            # ── CEP — padding para 7 dígitos ──────────────────────────────────
            cep_raw = re.sub(r"\D", "", _txt(im, "CEP"))
            if len(cep_raw) == 7:
                cep_raw = "0" + cep_raw

            # ── Endereço ──────────────────────────────────────────────────────
            cidade_id   = _txt(im, "IDCIDADE")
            bairro_id   = _txt(im, "IDBAIRRO")
            cidade_nome, cidade_sigla = cidades.get(cidade_id, ("", ""))
            bairro_nome = bairros.get(bairro_id, "")

            # Complemento: COMPLEMENTO + Cond. empreendimento + Andar
            comp_parts: list[str] = []
            raw_comp = _txt(im, "COMPLEMENTO")
            if raw_comp:
                comp_parts.append(raw_comp)
            empr_id = _txt(im, "EMPREENDIMENTO")
            if empr_id and empr_id not in ("", "0"):
                empr_nome = condominios.get(empr_id, "")
                if empr_nome:
                    comp_parts.append(f"Cond. {empr_nome}")
            numeroandar = _txt(im, "NUMEROANDAR")
            if numeroandar and numeroandar not in ("", "0"):
                comp_parts.append(f"Andar. {numeroandar}")
            complemento_raw = " ".join(comp_parts)

            bairro_n, rua, numero_end, complemento = normalize_address(
                bairro_nome,
                _txt(im, "ENDERECO"),
                _txt(im, "NUMERO"),
                complemento_raw,
            )

            # ── Áreas ─────────────────────────────────────────────────────────
            au = _fmt(_txt(im, "AREAUTIL"))
            at = _fmt(_txt(im, "AREA"))
            ac = _fmt(_txt(im, "AREACONSTRUIDA"))

            # ── Garagem: total = GARAGEM + GARAGEMCOBERTA ─────────────────────
            try:
                g_total = int(_txt(im, "GARAGEM") or 0) + int(_txt(im, "GARAGEMCOBERTA") or 0)
                garagem_total = str(g_total) if g_total else ""
            except ValueError:
                garagem_total = _txt(im, "GARAGEM") or _txt(im, "GARAGEMCOBERTA")
            garagem_coberta = _txt(im, "GARAGEMCOBERTA")

            # ── Banheiros = BANHEIRO − SUITE ──────────────────────────────────
            try:
                nb = int(_txt(im, "BANHEIRO") or 0)
                ns = int(_txt(im, "SUITE")    or 0)
                banheiros = str(max(nb - ns, 0))
            except ValueError:
                banheiros = _txt(im, "BANHEIRO")

            # ── Ocupado ───────────────────────────────────────────────────────
            try:
                ocupacao_val = int(_txt(im, "OCUPACAO") or "0")
            except ValueError:
                ocupacao_val = 0
            ocupado = "1" if ocupacao_val < 2 else "0"

            # ── Exclusividade ─────────────────────────────────────────────────
            exclusividade = _txt(im, "EXCLUSIVIDADE") or "0"

            # ── Características via IDs diretos ───────────────────────────────
            char_ids = imovel_char_ids.get(imovel_id, set())

            # Campos estruturados (closets, copa, etc.)
            structured: dict[str, str] = {}
            for field_name, ids_set in _FIELD_CHAR_IDS.items():
                if char_ids & ids_set:
                    structured[field_name] = "1"

            # Nomes canônicos para CARACTSIMNAO
            feature_names: list[str] = []
            seen_names: set[str] = set()
            for canonical_name, ids_set in _SIMNAO_CHAR_IDS:
                if (char_ids & ids_set) and canonical_name not in seen_names:
                    feature_names.append(canonical_name)
                    seen_names.add(canonical_name)

            # ── PropertyRecord ────────────────────────────────────────────────
            pr = PropertyRecord()
            pr.codigo            = imovel_id
            pr.imobiliaria       = "1"
            pr.status            = status
            pr.tipo              = tipo
            pr.sub_categoria     = sub_cat
            pr.data_registro     = data_registro
            pr.finalidade        = finalidade

            pr.valor_venda       = _fmt(sv_raw) if sv else ""
            pr.valor_locacao     = _fmt(rv_raw) if rv else ""
            pr.valor_condominio  = _fmt(_txt(im, "VALOR_CONDOMINIO"))

            pr.ocupado           = ocupado
            pr.mostrar_site      = "1" if _txt(im, "EXIBIRIMOVELSITE") == "1" else "0"
            pr.destaque          = "1" if _txt(im, "DESTAQUE") == "1" else "0"
            pr.locacao_exclusiva = exclusividade
            pr.venda_exclusiva   = exclusividade
            pr.street_view       = "1"
            pr.mapa_site         = "1"

            # OBS = "Ref: {CODIGO}" / OBS_SITE = vazio (conforme SQL de migração)
            pr.observacao        = f"Ref: {_txt(im, 'CODIGO') or imovel_id}"
            pr.obs_site          = ""

            pr.cep               = cep_raw
            pr.cidade            = _nfc(cidade_nome)
            pr.estado            = cidade_sigla
            pr.bairro            = _nfc(bairro_n)
            pr.rua               = _nfc(rua)
            pr.numero_end        = numero_end
            pr.complemento       = _nfc(complemento)

            pr.dormitorios       = _txt(im, "DORMITORIO")
            pr.suites            = _txt(im, "SUITE")
            pr.banheiros         = banheiros
            pr.lavabos           = "1" if _txt(im, "LAVABO") == "1" else ""
            pr.salas             = _txt(im, "SALAS")
            pr.garagem           = garagem_total
            pr.garagem_coberta   = garagem_coberta
            pr.ano_construcao    = _txt(im, "ANO_CONSTRUCAO")
            pr.latitude          = _txt(im, "LATITUDE")
            pr.longitude         = _txt(im, "LONGITUDE")
            pr.ponto_referencia  = _txt(im, "REFERENCIA")

            pr.area_util         = au or at
            pr.area_total        = at or au
            pr.area_construida   = ac or au or at

            pr.titulo_site       = _nfc(_txt(im, "TITULO"))

            # Campos estruturados de características
            for field_name, value in structured.items():
                if not getattr(pr, field_name, ""):
                    setattr(pr, field_name, value)

            # CARACTSIMNAO: via IDs + build_sim_nao para filtrar ao canônico
            pr.caracteristicas_sim_nao = build_sim_nao(feature_names)

            # Adiciona campos de imovel (ACEITAFINANCIAMENTO, PERMUTA) ao sim_nao
            extra_simnao: list[str] = []
            if _txt(im, "ACEITAFINANCIAMENTO") == "1":
                extra_simnao.append("Aceita financiamento")
            if _txt(im, "PERMUTA") == "1":
                extra_simnao.append("Aceita Permuta")
            if extra_simnao:
                existing = pr.caracteristicas_sim_nao
                pr.caracteristicas_sim_nao = ",".join(filter(None, [existing] + extra_simnao))

            # map_characteristics_to_fields para campos não cobertos por _FIELD_CHAR_IDS
            for fld, qty in map_characteristics_to_fields(feature_names).items():
                if not getattr(pr, fld, ""):
                    setattr(pr, fld, qty)

            prop_result.properties.append(pr)

            # ── IPTU ──────────────────────────────────────────────────────────
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

            # ── Proprietário ──────────────────────────────────────────────────
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

            # ── Captivador — fallback imobiliária (USUARIOS não tem CPF) ──────
            if imob_doc:
                prop_result.captivators.append(PropertyCaptivatorRecord(
                    codigo_imovel=imovel_id,
                    cpf_cnpj=imob_doc,
                    departamento=tipo,
                    data_captacao="",
                ))

        return prop_result
