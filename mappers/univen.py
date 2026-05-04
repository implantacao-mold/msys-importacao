from __future__ import annotations
import html
import re
import xml.etree.ElementTree as ET
from datetime import date
from typing import Any

from core.base_mapper import BaseMapper, ExtractionResult, PersonRecord, EmailRecord, PhoneRecord
from core.characteristics_utils import build_sim_nao, map_characteristics_to_fields
from core.phone_utils import processar_telefone, is_valid_email
from core.property_records import (
    PropertyExtractionResult, PropertyRecord, PropertyOwnerRecord,
    PropertyOwnerFavoredRecord, PropertyCaptivatorRecord, PropertyIptuRecord,
    normalize_address,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _txt(el: ET.Element | None, tag: str) -> str:
    if el is None:
        return ""
    found = el.find(tag)
    return (found.text or "").strip() if found is not None else ""


def _num(el: ET.Element, tag: str) -> float:
    """Parse comma-decimal value from XML tag: '450000,0000' → 450000.0"""
    s = _txt(el, tag).replace(",", ".")
    try:
        return float(s) if s else 0.0
    except ValueError:
        return 0.0


def _fmt(v: float) -> str:
    """Format non-zero float to '123.45', zero → ''."""
    return f"{v:.2f}" if v else ""


def _bool(el: ET.Element, tag: str) -> bool:
    return _txt(el, tag) == "1"


def _strip_html(v: str) -> str:
    v = re.sub(r"<[^>]+>", " ", v or "")
    v = html.unescape(v)
    return re.sub(r"\s+", " ", v).strip()


def _data_registro(el: ET.Element) -> str:
    """captacaocadem: '2007-11-20 09:14:41' → '2007-11-20'. Invalid/empty → today."""
    raw = _txt(el, "captacaocadem")
    if raw and not raw.startswith("1900"):
        return raw[:10]
    return date.today().isoformat()


# ── Subcategoria CASE ─────────────────────────────────────────────────────────

def _subcategoria(tipo: str, categoria: str) -> str:
    t = tipo.upper().strip()
    c = (categoria or "").upper().strip()

    # APARTAMENTO
    if t == "APARTAMENTO":
        if c in ("COBERTURA", "APTO. COBERTURA"):        return "2"
        if c == "DUPLEX":                                return "5"
        if c == "FLAT":                                  return "3"
        if c == "KITNET":                                return "4"
        if c == "STUDIO":                                return "46"
        if c == "SOBRADO":                               return "5"
        return "1"
    if t == "FLAT" and c == "DUPLEX":                    return "5"

    # APARTAMENTO DUPLEX / GARDEN / COBERTURA
    if t == "APARTAMENTO DUPLEX":                        return "5"
    if t == "APARTAMENTO GARDEN" and c == "NORMAL":      return "43"
    if t == "APTO. COBERTURA":
        if c in ("NORMAL", "COBERTURA"):                 return "2"
        if c == "DUPLEX":                                return "5"
        return "2"
    if t in ("COBERTURA", "COBERTURA/DUPLEX"):
        if c in ("DUPLEX", "NORMAL", "COBERTURA", "PADRÃO", ""):
            return "2"
        return "2"

    # ÁREA / LAZER
    if t in ("ÁREA", "AREA"):                            return "28"
    if "ÁREA DE LAZER" in t or t == "CLUBE":             return "34"

    # GALPÃO / BARRACÃO
    if t in ("BARRACAO", "BARRACÃO", "GALPÃO", "GALPAO",
             "ARMAZEM", "GALPÃO / BARRACÃO"):             return "41"

    # CASA
    if t in ("CASA", "CASA NOVA"):
        if c == "ÁREA DE LAZER":                         return "34"
        if c == "KITNET":                                return "39"
        if c in ("DUPLEX", "SOBRADO", "COBERTURA"):      return "8"
        if c in ("CONDOMÍNIO", "CASA EM CONDOMINIO",
                 "CASA DE CONDOMÍNIO", "COND  CASA"):    return "10"
        return "7"
    if t in ("CASA EM CONDOMINIO", "CASA EM CONDOMÍNIO", "CASA CONDOMINIO"):
        if c == "SOBRADO":                               return "40"
        return "10"
    if t in ("CASA COM EDÍCULA", "CASA COM SALÃO"):      return "7"
    if t == "VILLAGE":                                   return "36"

    # RURAL
    if t == "CHÁCARA":
        if c == "CASA":                                  return "56"
        return "16"
    if t in ("FAZENDA", "ESTÂNCIA"):                     return "17"
    if t in ("SÍTIO", "SITIO"):                          return "19"
    if t == "RANCHO":                                    return "29"
    if t == "HARAS":                                     return "20"

    # COMERCIAL
    if t == "COMERCIAL":
        if c == "LOJA/SALÃO":                            return "25"
        return "11"
    if t in ("IMÓVEL COMERCIAL", "SALA", "SALA COMERCIAL",
             "SALA / SALÃO COMERCIAL"):                  return "11"
    if t in ("SALÃO", "SALAO"):                          return "12"
    if t == "LOJA":                                      return "25"
    if t in ("PONTO", "POSTO DE GASOLINA", "MOTEL"):     return "31"
    if t == "PONTO COMERCIAL":
        if c == "SOBRADO":                               return "57"
        return "31"
    if t in ("PRÉDIO COMERCIAL", "PRÉDIO", "PREDIO", "EDIFICIO COMERCIAL"):
        if c == "SOBRADO":                               return "57"
        return "14"
    if t == "POUSADA":                                   return "38"
    if t == "HOTEL":                                     return "12"
    if t == "NEGÓCIO MONTADO":                           return "31"

    # KITNET / STUDIO
    if t in ("KITNET", "KITCHENET"):                     return "4"
    if t == "KITINETE / JK":
        if c == "FLAT":                                  return "3"
        return "4"
    if t in ("STUDIO", "STUDIO"):
        if c == "FLAT":                                  return "3"
        if c == "KITNET":                                return "4"
        return "46"

    # TERRENO / CONDOMÍNIO
    if t == "CONDOMÍNIO":
        if c == "TERRENO":                               return "22"
        return "10"
    if t in ("TERRENO", "TERRENO CONDOMINIO",
             "TERRENO EM CONDOMÍNIO", "TERRENO EM CONDOMINIO"):
        if c in ("CONDOMÍNIO", "COND  CASA", "CASA EM CONDOMINIO",
                 "TERRENO EM CONDOMINIO"):               return "22"
        if c == "LOTEAMENTO  MISTO":                     return "23"
        return "21"

    # OUTROS
    if t == "EDICULA":                                   return "9"
    if t == "BOX":                                       return "15"
    if t in ("LANÇAMENTO",):                             return "1"

    return "7"


# ── Características ───────────────────────────────────────────────────────────

# (tag, feature_name) — directly maps XML bool field to Msys feature name
_CARACTERISTICAS: list[tuple[str, str]] = [
    ("detalhearmcloset",        "Armário no closet"),
    ("detalhearmcozinha",       "Armários na Cozinha"),
    ("detalhearmdormitorio",    "Armários no Quarto"),
    ("detalhearmbanheiro",      "Armários nos Banheiros"),
    ("detalhecarpete",          "Carpete"),
    ("detalhechurrasqueira",    "Churrasqueiras"),
    ("detalhecozplan",          "Móveis planejados na cozinha"),
    ("detalheentcaminhoes",     "Entrada de caminhões"),
    ("detalheesgoto",           "Esgoto"),
    ("detalhegasnatural",       "Gás natural"),
    ("detalhepiscina",          "Piscina"),
    ("detalhepisofrio",         "Piso frio"),
    ("detalheportaoeletronico", "Portão eletrônico"),
    ("detalheportaria24h",      "Portaria 24 Hrs"),
    ("detalhequadrapoli",       "Quadra Poliesportiva"),
    ("detalhesacada",           "Sacada"),
    ("detalhevaranda",          "Varanda"),
    ("detalhecerca",            "Cerca"),
    ("detalhemurado",           "Muro"),
    ("detalhemezanino",         "Mezanino"),
    ("detalhecircuitotv",       "Circuito de televisão"),
    ("detalhearcondicionado",   "Ar-condicionado"),
    ("detalheadega",            "Adega"),
    ("detalhealarme",           "Alarme"),
    ("detalhecampfutebol",      "Campo de futebol"),
    ("detalhecozamericana",     "Cozinha americana"),
    ("detalhecozindependente",  "Cozinha independente"),
    ("detalheedicula",          "Edícula"),
    ("detalheelevadorservico",  "Elevador de Serviço"),
    ("detalhegerador",          "Gerador de energia solar"),
    ("detalhehidro",            "Hidro"),
    ("detalhewireless",         "Internet wireless"),
    ("detalhejardim",           "Jardim"),
    ("detalhelareira",          "Lareira"),
    ("detalhemarina",           "Marina"),
    ("detalhemobiliado",        "Mobília"),
    ("detalhepiscaquecida",     "Piscina Aquecida"),
    ("detalhepiscinfantil",     "Piscina infantil"),
    ("detalhequadrasquash",     "Quadra de squash"),
    ("detalhequintal",          "Quintal"),
    ("detalherefeitorio",       "Refeitório"),
    ("detalheresagua",          "Reservatório de água"),
    ("detalhesalafesta",        "Salão de Festas"),
    ("detalhesauna",            "Sauna"),
    ("detalhetelefone",         "Telefone"),
    ("detalhevestiario",        "Vestiários"),
    ("detalhezelador",          "Zelador"),
    ("detalhepersianaelet",     "Persiana motorizada"),
    ("detalheofuro",            "Ofurô"),
    ("detalhebar",              "Bar"),
    ("detalhedeck",             "Deck"),
    ("detalhearmariosala",      "Armário na sala"),
    ("detalhesemimobiliado",    "Semi mobiliado"),
    ("detalhemoveisplanej",     "Móveis Planejados"),
    ("detalheterraco",          "Terraço"),
    ("detalhevistamar",         "Vista Mar"),
    ("detalheporcelanato",      "Porcelanato"),
    ("detalheplayground",       "Play Ground"),
    ("detalhesalacinema",       "Cinema"),
    ("detalhebicicletario",     "Bicicletário"),
    ("detalhelaminado",         "Piso laminado"),
    ("detalhevarandagourmet",   "Varanda Gourmet"),
    ("detalhebrinquedoteca",    "Brinquedoteca"),
    ("detalheguarita",          "Guarita"),
    ("detalhearealazer",        "Área de lazer"),
    ("detalheaquesolar",        "Aquecedor solar"),
    ("detalheinterfone",        "Interfone"),
    ("detalhespa",              "SPA"),
    ("detalhearmlavanderia",    "Armário na área de serviço"),
    ("detalhecooktop",          "Cooktop"),
    ("detalhemicroondas",       "Micro-ondas"),
    ("detalhequadratenis",      "Quadra de tênis"),
    ("detalheelevador",         "Elevador Social"),
    ("detalhesalaginastica",    "Sala de ginástica"),
    ("detalhetvacabo",          "Televisão a cabo"),
    ("detalheareaserv",         "Área de serviço"),
    ("detalheaceitapet",        "Aceita pet"),
    ("detalheaguaquente",       "Aquecedor"),
    ("detalheaquececentral",    "Aquecimento"),
    ("detalheareaverde",        "Área verde"),
    ("detalhedemisuite",        "Demi-suítes"),
    ("detalhebeiralago",        "Vista para lago"),
    ("detalhecalefacao",        "Aquecimento"),
    ("detalheentlateral",       "Entrada lateral"),
    ("detalheentradaservico",   "Entrada de serviço independente"),
    ("detalheentservico",       "Entrada de serviço independente"),
    ("detalheestacionamento",   "Estacionamento"),
    ("detalheestvisitante",     "Estacionamento para visitante"),
    ("detalhefrentepraca",      "Praça"),
    ("detalhegourmet",          "Espaço Gourmet"),
    ("detalhegradeado",         "Cercada"),
    ("detalhesolmanha",         "Sol da manhã"),
    ("detalhesuitemaster",      "Suíte Master"),
    ("detalheventteto",         "Ventilador"),
    ("detalhevinilico",         "Piso vinílico"),
    ("detalhevistalagoa",       "Vista para lago"),
    ("detalhevistalivre",       "Vista livre"),
    ("detalhevistaserra",       "Vista para a montanha"),
    ("detalhesisincendio",      "Sistema de incêndio"),
    ("detalhesplit",            "Ar-condicionado"),
    ("detalhepilotis",          "Heliponto"),
    ("detalhefrentemar",        "Vista mar"),
]

# sala* fields: non-zero value counts as presence
_SALA_FEATURES: list[tuple[str, str]] = [
    ("detalhesalaestar",  "Sala de estar"),
    ("detalhesalajantar", "Sala de jantar"),
    ("detalhesalatv",     "Sala de TV"),
]

# face/isolamento special fields
def _extra_features(im: ET.Element) -> list[str]:
    extras: list[str] = []
    if _txt(im, "detalheface").upper() == "LESTE":
        extras.append("Frente leste")
    if _txt(im, "detalheisolamento").upper() == "ISOLADA":
        extras.append("Isolado")
    if _num(im, "detalheareaprivativa") > 0:
        extras.append("Área privativa")
    return extras


def _build_features(im: ET.Element) -> list[str]:
    features: list[str] = []
    for tag, name in _CARACTERISTICAS:
        if _txt(im, tag) == "1":
            features.append(name)
    for tag, name in _SALA_FEATURES:
        if _num(im, tag) != 0:
            features.append(name)
    features.extend(_extra_features(im))
    return features


# ── Mapper ────────────────────────────────────────────────────────────────────

class UnivenMapper(BaseMapper):
    NAME = "Univen"
    EXTENSIONS = [".zip"]
    DESCRIPTION = "Univen (ZIP com XMLs)"

    def can_handle(self, filename: str) -> bool:
        return filename.lower().endswith(".zip")

    def extract_zip(self, files: dict[str, Any]) -> ExtractionResult:
        result = ExtractionResult()
        seen: set[str] = set()

        clientes_roots: list[ET.Element] = []
        imoveis_roots: list[ET.Element] = []
        usuarios_roots: list[ET.Element] = []

        for name, data in files.items():
            lower = name.lower()
            if not isinstance(data, ET.Element):
                continue
            if "cliente" in lower and "nota" not in lower:
                clientes_roots.append(data)
            elif "imovel" in lower or "imoveis" in lower:
                if "video" not in lower and "midia" not in lower:
                    imoveis_roots.append(data)
            elif "usuario" in lower:
                usuarios_roots.append(data)

        # Build client lookup by codcli (for property owner matching)
        client_by_id: dict[str, ET.Element] = {}
        for root in clientes_roots:
            for cli in root.iter("cliente"):
                cod = _txt(cli, "codcli")
                if cod:
                    client_by_id[cod] = cli

        # Clientes com imóvel = OW
        prop_ids: set[str] = set()
        for root in imoveis_roots:
            for im in root.iter("imovel"):
                fk = _txt(im, "fkcodcli")
                if fk and fk != "0":
                    prop_ids.add(fk)

        # Processar clientes
        for root in clientes_roots:
            for cli in root.iter("cliente"):
                cod = _txt(cli, "codcli")
                if not cod:
                    continue
                tipo = "OW" if cod in prop_ids else "BU"
                self._process_cli(cli, cod, tipo, result, seen)

        # Usuários = EM (somente com CPF)
        for root in usuarios_roots:
            for usr in root.iter("usuario"):
                cpf = re.sub(r"\D", "", _txt(usr, "cpf"))
                if not cpf:
                    continue
                cod_raw = _txt(usr, "codigo") or _txt(usr, "codusr")
                codigo = "U" + cod_raw if cod_raw else "U" + cpf
                self._process_cli(usr, codigo, "EM", result, seen)

        # Imóveis
        result.property_result = self._extract_imoveis(imoveis_roots, client_by_id)

        return result

    def _process_cli(
        self,
        el: ET.Element,
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
        p.nome = _txt(el, "nome")
        p.cpf = re.sub(r"\D", "", _txt(el, "cpf"))
        p.cnpj = re.sub(r"\D", "", _txt(el, "cnpj"))
        p.rg = _txt(el, "rg")
        p.data_nascimento = _txt(el, "dtnascimento") or _txt(el, "nascimento")
        p.sexo = _txt(el, "sexo")
        p.estado_civil = _txt(el, "estadocivil")
        p.cep = re.sub(r"\D", "", _txt(el, "cep"))
        p.cidade = _txt(el, "cidade")
        p.bairro = _txt(el, "bairro")
        p.estado = _txt(el, "uf") or _txt(el, "estado")
        p.endereco = _txt(el, "endereco") or _txt(el, "logradouro")
        p.numero = _txt(el, "numero")
        p.complemento = _txt(el, "complemento")
        p.observacao = _txt(el, "observacao") or _txt(el, "obs")
        p.profissao = _txt(el, "profissao")
        p.nacionalidade = _txt(el, "nacionalidade")

        result.persons.append(p)

        self._add_phones(el, codigo, tipo, result)

        email = _txt(el, "email")
        if is_valid_email(email):
            result.emails.append(EmailRecord(
                codigo_pessoa=codigo,
                tipo_pessoa=tipo,
                email=email,
                tipo_email="",
            ))

    def _add_phones(self, el: ET.Element, codigo: str, tipo: str, result: ExtractionResult) -> None:
        for tag in ("telefone1", "telefone2", "celular"):
            raw = _txt(el, tag)
            if not raw:
                continue
            for part in re.split(r"[\s/]+", raw):
                part = re.sub(r"\D", "", part)
                if len(part) < 8:
                    continue
                parsed = processar_telefone(part)
                if parsed:
                    result.phones.append(PhoneRecord(
                        codigo_pessoa=codigo, tipo_pessoa=tipo,
                        ddi=parsed["ddi"], ddd=parsed["ddd"],
                        telefone=parsed["numero"], tipo_telefone=parsed["tipo"],
                    ))

    # ── Property extraction ───────────────────────────────────────────────────

    def _extract_imoveis(
        self,
        imoveis_roots: list[ET.Element],
        client_by_id: dict[str, ET.Element],
    ) -> PropertyExtractionResult:
        prop_result = PropertyExtractionResult()
        imob_doc = re.sub(r"\D", "", self.context.get("imob_cpf_cnpj", ""))
        imob_nome = self.context.get("imob_nome", "")

        for root in imoveis_roots:
            # Process both <imovel> (active) and <imovel_arquivado> (archived)
            for tag_name in ("imovel", "imovel_arquivado"):
                for im in root.iter(tag_name):
                    self._process_imovel(im, prop_result, client_by_id, imob_doc, imob_nome)

        return prop_result

    def _process_imovel(
        self,
        im: ET.Element,
        prop_result: PropertyExtractionResult,
        client_by_id: dict[str, ET.Element],
        imob_doc: str,
        imob_nome: str,
    ) -> None:
        codigo = _txt(im, "principalreferencia")
        if not codigo:
            return

        data_registro = _data_registro(im)

        # Status
        status = "1" if _txt(im, "principalsituacao") == "ATIVO" else "5"

        # Tipo S / L / SL
        is_venda   = _txt(im, "principalvenda")   == "1"
        is_locacao = _txt(im, "principallocalacao") == "1"
        if is_venda and is_locacao:
            tipo = "SL"
        elif is_venda:
            tipo = "S"
        else:
            tipo = "L"

        # Subcategoria
        sub_categoria = _subcategoria(
            _txt(im, "principaltipo"),
            _txt(im, "principalcategoria"),
        )

        # Valores
        val_venda = _num(im, "principalvalvenda")
        val_loc   = _num(im, "principalvallocalacao")

        # Ocupação
        ocup = _txt(im, "principalocupacao").upper()
        if ocup == "DESOCUPADO":
            ocupado = "0"
        elif ocup in ("PROPRIETÁRIO", "OCUPADO", "INQUILINO", "CONSTRUTORA"):
            ocupado = "1"
        else:
            ocupado = ""

        # Observação
        ref    = _txt(im, "principalreferencia")
        desc   = _strip_html(_txt(im, "principaldescricao"))
        doc    = _txt(im, "confidencialdocumentacao")
        obs_parts = [f"Referencia: {ref}"]
        if desc:
            obs_parts.append(f"Descrição: {desc}")
        if doc:
            obs_parts.append(f"Documentação: {doc}")
        observacao = " - ".join(obs_parts)

        # obs_site
        obs_site = _strip_html(_txt(im, "internetanunciointernet"))

        # IPTU
        iptu_val = _num(im, "captacaovaliptu")

        # CEP — stored as numeric (may need zero-padding)
        cep_raw = re.sub(r"\D", "", _txt(im, "principalcep"))
        cep = cep_raw.zfill(8) if cep_raw and cep_raw != "0" else ""

        # Endereço
        bairro, rua, numero, complemento = normalize_address(
            _txt(im, "principalbairro"),
            _txt(im, "principalendereco") or "Não Consta",
            _txt(im, "principalnumero"),
            _txt(im, "principalcomplemento"),
        )
        # Complemento extra: condo name / bloco / apto
        condo = _txt(im, "principalcondonome")
        bloco = _txt(im, "principalblocalo")
        apto  = _txt(im, "principalapartamento")
        if condo and condo != "0":
            complemento = (complemento + f" Cond. {condo}").strip()
        if bloco:
            complemento = (complemento + f" Bloco: {bloco}").strip()
        if apto:
            complemento = (complemento + f" Nº apto: {apto}").strip()

        # Áreas
        au  = _num(im, "detalheareautil")
        ac  = _num(im, "detalheareaconst")
        at  = _num(im, "detalheareatotal")
        ate = _num(im, "detalheareaterreno")
        dim = _num(im, "detalhedimterreno")

        area_util      = _fmt(au if au else ac)
        area_total     = _fmt(at if at else ate)
        area_construida = _fmt(ate or at or dim or au)

        # Closets: maior entre detalhecloset e detalhesuiteclo
        closet_val = max(_num(im, "detalhecloset"), _num(im, "detalhesuiteclo"))

        # Tipo piso (CASE)
        tipo_piso = ""
        for tag, nome in (
            ("detalhecarpmadeira",  "Carpete de madeira"),
            ("detalhecontrapiso",   "Contrapiso"),
            ("detalhepisoceramica", "Piso de cerâmica"),
            ("detalhepisoelevado",  "Piso elevado"),
            ("detalhetaco",        "Piso taco"),
        ):
            if _bool(im, tag):
                tipo_piso = nome
                break

        # Geo
        lat = _txt(im, "locallatitude")
        lon = _txt(im, "locallongitude")
        latitude  = "" if lat in ("0", "0.0", "0,0", "") else lat
        longitude = "" if lon in ("0", "0.0", "0,0", "") else lon

        # Ano construção
        ano_raw = _txt(im, "captacaoanoconstru")
        try:
            ano = str(int(float(ano_raw))) if ano_raw and float(ano_raw) > 0 else ""
        except (ValueError, TypeError):
            ano = ""

        # Características
        feature_names = _build_features(im)

        # Build PropertyRecord
        pr = PropertyRecord()
        pr.codigo           = codigo
        pr.data_registro    = data_registro
        pr.imobiliaria      = "1"
        pr.status           = status
        pr.tipo             = tipo
        pr.sub_categoria    = sub_categoria
        pr.valor_venda      = _fmt(val_venda)
        pr.valor_locacao    = _fmt(val_loc)
        pr.ocupado          = ocupado
        pr.mostrar_site     = _txt(im, "internetpubsite")
        pr.destaque         = _txt(im, "internetpubdestaque")
        pr.street_view      = "1"
        pr.mapa_site        = "1"
        pr.observacao       = observacao
        pr.obs_site         = obs_site
        pr.num_iptu         = _txt(im, "confidencialcadpref")
        pr.valor_mensal_iptu = _fmt(iptu_val)
        pr.valor_anual_iptu  = _fmt(iptu_val)
        pr.perc_iptu        = "100" if iptu_val else ""
        pr.cep              = cep
        pr.cidade           = _txt(im, "principalcidade")
        pr.bairro           = bairro
        pr.estado           = _txt(im, "principaluf")
        pr.rua              = rua
        pr.numero_end       = numero
        pr.complemento      = complemento
        pr.dormitorios      = _txt(im, "detalhedormitorios")
        pr.banheiros        = _txt(im, "detalhebanheiros")
        pr.area_util        = area_util
        pr.area_total       = area_total
        pr.area_construida  = area_construida
        pr.suites           = _txt(im, "detalhesuite")
        pr.closets          = str(int(closet_val)) if closet_val else ""
        pr.salas            = _txt(im, "detalhesala")
        pr.copas            = _txt(im, "detalhecopa")
        pr.cozinhas         = _txt(im, "detalhecozinha")
        pr.despensas        = _txt(im, "detalhedespensa")
        pr.lavanderias      = _txt(im, "detalhelavanderia")
        pr.lavabos          = _txt(im, "detalhelavabo")
        pr.halls            = _txt(im, "detalhehall")
        pr.sala_jogos       = _txt(im, "detalhesalajogo")
        pr.dorm_funcionario = _txt(im, "detalhedormemp")
        pr.banheiro_funcionario = _txt(im, "detalhebanemp")
        pr.escritorio       = _txt(im, "detalheescritorio")
        pr.depositos        = _txt(im, "detalhedeposito")
        pr.recepcoes        = _txt(im, "detalherecepcao")
        pr.pe_direito       = _fmt(_num(im, "detalhepedireito"))
        pr.garagem          = _txt(im, "detalhegaragens")
        pr.garagem_coberta  = _txt(im, "detalhegaragenscob")
        pr.tipo_piso        = tipo_piso
        pr.lago             = _txt(im, "detalhelago")
        pr.poco_artesiano   = _txt(im, "detalhepoco")
        pr.casa_empregado   = _txt(im, "detalhecasacaseiro")
        pr.latitude         = latitude
        pr.longitude        = longitude
        pr.ponto_referencia = _txt(im, "principalpontoref")
        pr.valor_condominio = _fmt(_num(im, "captacaovalcondominio"))
        pr.titulo_site      = _txt(im, "internettitle")
        pr.ano_construcao   = ano

        pr.caracteristicas_sim_nao = build_sim_nao(feature_names)
        for fld, qty in map_characteristics_to_fields(feature_names).items():
            if not getattr(pr, fld, ""):
                setattr(pr, fld, qty)

        prop_result.properties.append(pr)

        # ── IPTU ─────────────────────────────────────────────────────────────
        if iptu_val > 0:
            prop_result.iptu.append(PropertyIptuRecord(
                codigo_imovel=codigo,
                tipo_iptu="IPTU Principal",
                inscricao_iptu="",
                valor_mensal_iptu=_fmt(iptu_val),
                valor_anual_iptu=_fmt(iptu_val),
                parcelas_iptu="",
                perc_iptu="100",
                obs_iptu="",
            ))

        # ── Owner ─────────────────────────────────────────────────────────────
        fk = _txt(im, "fkcodcli")
        has_owner = fk and fk != "0" and fk in client_by_id
        if has_owner:
            cli = client_by_id[fk]
            ow_cpf  = re.sub(r"\D", "", _txt(cli, "cpf"))
            ow_cnpj = re.sub(r"\D", "", _txt(cli, "cnpj"))
            # Unified rule: if owner has real CPF use it; if CNPJ only use that; else blank
            if not ow_cpf and not ow_cnpj:
                ow_cpf, ow_cnpj = "", ""  # no doc, linked by ID only
            ow_codigo = fk
            ow_nome   = _txt(cli, "nome")
        else:
            ow_cpf    = ""
            ow_cnpj   = imob_doc
            ow_codigo = ""
            ow_nome   = imob_nome

        prop_result.owners.append(PropertyOwnerRecord(
            codigo_imovel=codigo,
            cpf=ow_cpf,
            cnpj=ow_cnpj,
            codigo_pessoa=ow_codigo,
            percentual="100",
        ))
        prop_result.owners_favored.append(PropertyOwnerFavoredRecord(
            codigo_imovel=codigo,
            cpf=ow_cpf,
            cnpj=ow_cnpj,
            codigo_pessoa=ow_codigo,
            tipo_pagamento="M",
            percentual="100",
            cpf_favorecido=ow_cpf,
            cnpj_favorecido=ow_cnpj,
            id_favorecido=ow_codigo,
            favorecido=ow_nome,
            banco="", agencia="", digito_agencia="",
            conta="", digito_conta="", poupanca="0",
        ))

        # ── Captivadores ─────────────────────────────────────────────────────
        if imob_doc:
            if is_venda:
                prop_result.captivators.append(PropertyCaptivatorRecord(
                    codigo_imovel=codigo,
                    cpf_cnpj=imob_doc,
                    departamento="S",
                    data_captacao=data_registro,
                ))
            if is_locacao or (not is_venda and not is_locacao):
                prop_result.captivators.append(PropertyCaptivatorRecord(
                    codigo_imovel=codigo,
                    cpf_cnpj=imob_doc,
                    departamento="L",
                    data_captacao=data_registro,
                ))
