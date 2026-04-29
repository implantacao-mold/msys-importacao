from __future__ import annotations
import hashlib
import html
import re
import unicodedata
import xml.etree.ElementTree as ET
from datetime import date

from core.base_mapper import BaseMapper, ExtractionResult, PersonRecord, EmailRecord, PhoneRecord
from core.cep_lookup import fill_city_state, is_valid_cep, lookup_cep_by_city
from core.characteristics_utils import build_sim_nao, map_characteristics_to_fields
from core.subcategorias import get_custom_subcat
from core.phone_utils import processar_telefone, is_valid_email
from core.property_records import (
    PropertyRecord, PropertyOwnerRecord, PropertyOwnerFavoredRecord,
    PropertyCaptivatorRecord, PropertyIptuRecord,
    PropertyExtractionResult, normalize_address,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _txt(el: ET.Element | None, tag: str) -> str:
    if el is None:
        return ""
    found = el.find(tag)
    return (found.text or "").strip() if found is not None else ""


def _md5(s: str) -> str:
    return hashlib.md5(s.encode("utf-8")).hexdigest()[:16].upper()


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
    v = html.unescape(v)
    return re.sub(r"\s+", " ", v).strip()


# ── Subcategoria (TipoImovel, SubTipoImovel) → ID ─────────────────────────────

_SUB: dict[tuple[str, str], str] = {
    ("Empreendimento",             ""):                              "1",
    ("Apartamento",                "Apartamento com terraço"):       "1",
    ("Apartamento",                "Apartamento duplex"):            "5",
    ("Cobertura",                  "Apartamento duplex"):            "65",
    ("Apartamento",                "Apartamento garden"):            "43",
    ("Apartamento",                "Apartamento padrão"):            "1",
    ("Apartamento",                "Apartamento sem condomínio"):    "1",
    ("Area",                       "Area"):                          "28",
    ("Terreno",                    "Area"):                          "28",
    ("Casa",                       "Casa"):                          "7",
    ("Casa",                       "Casa comercial"):                "0",
    ("",                           "Casa de Condomínio"):            "10",
    ("Casa",                       "Casa de vila"):                  "66",
    ("Casa",                       "Casa duplex"):                   "8",
    ("Casa",                       "Casa em condomínio"):            "10",
    ("Casa",                       "Casa geminada"):                 "66",
    ("Casa",                       "Casa padrão"):                   "7",
    ("Casa",                       "Casa plana"):                    "7",
    ("Chácara",                    "Chácara"):                       "16",
    ("Casa",                       "Chalé"):                         "47",
    ("Cobertura / Penthouse",      "Cobertura / Penthouse"):         "65",
    ("Conjunto comercial",         "Conjunto comercial"):            "68",
    ("Galpão / Barracão",          "Depósito"):                      "41",
    ("Casa",                       "Edícula"):                       "9",
    ("Flat",                       "Flat"):                          "3",
    ("Galpão / Barracão",          "Galpão logístico"):              "61",
    ("Hotel",                      "Hotel"):                         "59",
    ("Apartamento",                "Kitnet"):                        "4",
    ("Kitnet",                     "Kitnet"):                        "39",
    ("Lançamento",                 "Lançamento"):                    "23",
    ("Loft",                       "Loft"):                          "33",
    ("Loja",                       "Loja"):                          "25",
    ("Loja",                       "Loja em shopping"):              "25",
    ("Terreno",                    "Lote"):                          "23",
    ("Terreno",                    "Loteamento"):                    "23",
    ("Casa",                       "Mansão"):                        "63",
    ("Galpão / Barracão",          "Pavilhão"):                      "62",
    ("Loja",                       "Ponto comercial"):               "31",
    ("Ponto",                      "Ponto comercial"):               "31",
    ("Pousada",                    "Pousada"):                       "38",
    ("Prédio",                     "Prédio"):                        "14",
    ("Prédio",                     "Prédio comercial"):              "14",
    ("Sala",                       "Sala comercial"):                "11",
    ("Loja",                       "Salão comercial"):               "12",
    ("Sítio",                      "Sítio"):                         "19",
    ("Sobrado",                    "Sobrado"):                       "8",
    ("Studio",                     "Studio"):                        "46",
    ("Terreno",                    "Terreno"):                       "21",
    ("Terreno",                    "Terreno em condomínio"):         "22",
    ("Lote / Terreno Residencial", "Terreno padrão"):                "26",
    ("Terreno",                    "Terreno padrão"):                "21",
    ("Studio",                     "Studio comercial"):              "46",
    ("Andar corporativo",          "Andar inteiro"):                 "14",
    ("Galpão / Barracão",          "Barracão"):                      "41",
    ("Fazenda",                    "Fazenda"):                       "17",
}

# ── Características booleanas (XML tag → nome canônico Msys) ─────────────────

_BOOL_CHARS: list[tuple[str, str]] = [
    ("Academia",                    "Academia"),
    ("Adega",                       "Adega"),
    ("Alarme",                      "Alarme"),
    ("AndarAlto",                   "Apartamento Andar Alto"),
    ("AquecimentoCentral",          "Aquecimento"),
    ("AquecimentoEletrico",         "Aquecimento elétrico"),
    ("AquecimentoGas",              "Aquecimento a gás"),
    ("aquecimento_solar",           "Aquecedor solar"),
    ("ArCondicionado",              "Ar-condicionado"),
    ("ar_condicionado",             "Ar-condicionado"),
    ("ArCondicionadoSplit",         "Ar-condicionado"),
    ("AreaDeServico",               "Área de serviço"),
    ("AreaServico",                 "Área de serviço"),
    ("ArmarioAreaDeServico",        "Armário na área de serviço"),
    ("ArmarioBanheiro",             "Armários nos Banheiros"),
    ("ArmarioCloset",               "Armário no closet"),
    ("ArmarioCozinha",              "Armários na Cozinha"),
    ("ArmarioDormitorio",           "Armários no Quarto"),
    ("ArmarioDormitorioEmpregada",  "Armários no Quarto"),
    ("ArmarioQuarto",               "Armários no Quarto"),
    ("ArmarioSuite",                "Armários no Quarto"),
    ("ArmarioEscritorio",           "Armário no escritório"),
    ("EscritorioArmario",           "Armário no escritório"),
    ("ArmarioHomeTheater",          "Armário na sala"),
    ("ArmarioSala",                 "Armário na sala"),
    ("auditorio",                   "Auditório"),
    ("Bar",                         "Bar"),
    ("bicicletario",                "Bicicletário"),
    ("bosque",                      "Bosque"),
    ("Brinquedoteca",               "Brinquedoteca"),
    ("CampoDeFutebol",              "Campo de futebol"),
    ("Carpete",                     "Carpete"),
    ("CarpeteMadeira",              "Piso laminado"),
    ("Cerca",                       "Cerca"),
    ("Churrasqueira",               "Churrasqueira"),
    ("Churrasqueiras",              "Churrasqueiras"),
    ("CircuitoInternoTV",           "Circuito de televisão"),
    ("circuitointernotv",           "Circuito de televisão"),
    ("CozinhaAmericana",            "Cozinha americana"),
    ("Deck",                        "Deck"),
    ("DeckMolhado",                 "Deck Molhado"),
    ("Edicula",                     "Edícula"),
    ("elevador",                    "Elevadores"),
    ("ElevadorComGerador",          "Elevadores"),
    ("ElevadorGerador",             "Elevadores"),
    ("elevador_privativo",          "Elevadores"),
    ("entrada_lateral",             "Entrada lateral"),
    ("EntradaServico",              "Entrada de serviço independente"),
    ("EntradaServicoIndependente",  "Entrada de serviço independente"),
    ("esquina",                     "Esquina"),
    ("EspacoLeitura",               "Espaço de leitura"),
    ("FornoDePizza",                "Forno de pizza"),
    ("Gourmet",                     "Espaço Gourmet"),
    ("Grama",                       "Gramada"),
    ("Guarita",                     "Guarita"),
    ("GuaritaSeguranca",            "Guarita"),
    ("guarita_seguranca",           "Guarita"),
    ("guarita_blindada",            "Guarita Blindada"),
    ("Heliponto",                   "Heliponto"),
    ("Hidromassagem",               "Hidro"),
    ("SpaHidromassagem",            "Hidro"),
    ("HomeTheater",                 "Home theater"),
    ("Interfone",                   "Interfone"),
    ("Jardim",                      "Jardim"),
    ("JardimInverno",               "Jardim de inverno"),
    ("LajeTecnica",                 "Teto em laje"),
    ("Lareira",                     "Lareira"),
    ("LojaConveniencia",            "Loja"),
    ("Madeira",                     "Piso de madeira"),
    ("Mezanino",                    "Mezanino"),
    ("Mezanino0",                   "Mezanino"),
    ("Mezanino1",                   "Mezanino"),
    ("Mobiliado",                   "Mobília"),
    ("Norte",                       "Frente norte"),
    ("Ofuro",                       "Ofurô"),
    ("Pavimentacao",                "Asfalto"),
    ("PeDireitoDuplo",              "Lobby com pé direito duplo"),
    ("PetPlace",                    "Pet Place"),
    ("Piscina",                     "Piscina"),
    ("Piscinas",                    "Piscina"),
    ("piscina_aquecida",            "Piscina Aquecida"),
    ("PiscinaAquecida",             "Piscina Aquecida"),
    ("PiscinaInfantil",             "Piscina infantil"),
    ("piscina_infantil",            "Piscina infantil"),
    ("PiscinaRaia",                 "Piscina com raia"),
    ("PisoElevado",                 "Piso elevado"),
    ("PisoFrio",                    "Piso frio"),
    ("PisoLaminado",                "Piso laminado"),
    ("PisoPorcelanato",             "Porcelanato"),
    ("PisoTacoMadeira",             "Piso de madeira"),
    ("pista_cooper",                "Pista de Cooper"),
    ("Playground",                  "Playground"),
    ("PocoArtesiano",               "Poço artesiano"),
    ("PortaoEletronico",            "Portão eletrônico"),
    ("portal_eletronico",           "Portão eletrônico"),
    ("Portaria24Horas",             "Portaria 24 Hrs"),
    ("Portaria24h",                 "Portaria 24 Hrs"),
    ("QuadraPoliEsportiva",         "Quadra Poliesportiva"),
    ("QuadraDeEsportes",            "Quadra Poliesportiva"),
    ("QuadraDeTenis",               "Quadra de tênis"),
    ("quadra_tenis",                "Quadra de tênis"),
    ("quadra_squash",               "Quadra de squash"),
    ("Quintal",                     "Quintal"),
    ("QuiosqueComChurrasqueiraEF",  "Quiosque com churrasqueira e forno"),
    ("Refeitorio",                  "Refeitório"),
    ("RestaurantePrivado",          "Restaurante"),
    ("restaurante",                 "Restaurante"),
    ("SPA",                         "SPA"),
    ("Sacada",                      "Sacada"),
    ("SacadaComSkinGlass",          "Sacada fechada em Reiki"),
    ("SalaDePilates",               "Sala de ginástica"),
    ("SalaFitness",                 "Sala de ginástica"),
    ("SalaGinastica",               "Sala de ginástica"),
    ("SalaEstar",                   "Sala de estar"),
    ("SalaJantar",                  "Sala de jantar"),
    ("SalaMassagem",                "Sala de massagem"),
    ("SalaReuniao",                 "Salas de reuniões"),
    ("SalaTV",                      "Sala de TV"),
    ("SalaoJogos",                  "Salão de Jogos"),
    ("salao_jogos",                 "Salão de Jogos"),
    ("Boliche",                     "Salão de Jogos"),
    ("SalaoFestas",                 "Salão de Festas"),
    ("SalaoVideoCinema",            "Cinema"),
    ("salao_video_cinema",          "Cinema"),
    ("salaogourmet",                "Salão gourmet"),
    ("Sauna",                       "Sauna"),
    ("sauna_seca",                  "Sauna"),
    ("sauna_umida",                 "Sauna úmida"),
    ("Seguranca",                   "Segurança"),
    ("Semimobiliado",               "Semi mobiliado"),
    ("Solarium",                    "Solarium"),
    ("SolManha",                    "Sol da manhã"),
    ("SolTarde",                    "Sol da tarde"),
    ("Sul",                         "Frente sul"),
    ("Terraco",                     "Terraço"),
    ("TerracoColetivo",             "Terraço"),
    ("TomadaCarroEletrico",         "Tomada elétrica para todas as vagas de garagem"),
    ("TvCabo",                      "Televisão a cabo"),
    ("Varanda",                     "Varanda"),
    ("VarandaGourmet",              "Varanda Gourmet"),
    ("VentiladorDeTeto",            "Ventilador"),
    ("vestiario_diaristas",         "Vestiário para empregados"),
    ("Vinilico",                    "Piso Vinílico"),
    ("VistaMar",                    "Vista mar"),
    ("QuadraMar",                   "Vista mar"),
    ("Zelador",                     "Zelador"),
    ("DepositoPrivativoNoSubsolo",  "Deposito subsolo"),
    ("EstacionamentoRotativo",      "Estacionamento rotativo"),
    ("GasCentralCondominal",        "Gás encanado"),
    ("quadra_gramada",              "Quadra Gramada"),
    ("QuadraTenis",                 "Quadra de tênis"),
    ("EscritorioVirtual",           "Escritório virtual"),
    ("CondominioFechado",           "Condominio fechado"),
    ("BeachPoint",                  "Ponto comercial"),
]


def _resolve_subcat(tipo: str, subtipo: str) -> str:
    """Returns subcategory ID: custom mapping → _SUB dict → '' (needs review)."""
    custom = get_custom_subcat(tipo, subtipo)
    if custom is not None:
        return custom
    return _SUB.get((tipo, subtipo), "")


# ── Mapper ────────────────────────────────────────────────────────────────────

class ArboMapper(BaseMapper):
    NAME = "Arbo"
    EXTENSIONS = [".xml"]
    DESCRIPTION = "Arbo (XML)"

    def can_handle(self, filename: str) -> bool:
        return filename.lower().endswith(".xml")

    def extract(self, root: ET.Element) -> ExtractionResult:
        result = ExtractionResult()
        seen: set[str] = set()
        person_by_codigo_imovel: dict[str, PersonRecord] = {}

        person_by_codigo: dict[str, PersonRecord] = {}

        for imovel in root.findall(".//Imovel"):
            prop = imovel.find("Proprietario")
            codigo_imovel = _txt(imovel, "CodigoImovel")

            if prop is not None:
                nome = _txt(prop, "Nome")
                if nome:
                    tel_raw = _txt(prop, "Telefone")
                    parsed_tel = processar_telefone(tel_raw) if tel_raw else None
                    first_digits = (parsed_tel["ddd"] + parsed_tel["numero"]) if parsed_tel else ""

                    codigo = _md5(nome.upper() + first_digits)
                    key = f"{codigo}|OW"
                    if key not in seen:
                        seen.add(key)

                        p = PersonRecord()
                        p.codigo = codigo
                        p.tipo = "OW"
                        p.nome = nome
                        p.cpf = re.sub(r"\D", "", _txt(prop, "CPF"))
                        result.persons.append(p)
                        person_by_codigo[codigo] = p

                        if parsed_tel:
                            result.phones.append(PhoneRecord(
                                codigo_pessoa=codigo,
                                tipo_pessoa="OW",
                                ddi=parsed_tel["ddi"],
                                ddd=parsed_tel["ddd"],
                                telefone=parsed_tel["numero"],
                                tipo_telefone=parsed_tel["tipo"],
                            ))

                        email = _txt(prop, "Email")
                        if is_valid_email(email) and "@temp-email.com.br" not in email:
                            result.emails.append(EmailRecord(
                                codigo_pessoa=codigo,
                                tipo_pessoa="OW",
                                email=email,
                                tipo_email="",
                            ))

                    person_by_codigo_imovel[codigo_imovel] = person_by_codigo[codigo]

        result.property_result = self._extract_properties(root, person_by_codigo_imovel)
        return result

    def scan_subcategories(self, data: ET.Element) -> set[str]:
        """Returns 'TipoImovel|SubTipoImovel' pairs that have no mapping configured."""
        pairs: set[str] = set()
        for imovel in data.findall(".//Imovel"):
            tipo    = _txt(imovel, "TipoImovel")
            subtipo = _txt(imovel, "SubTipoImovel")
            if _resolve_subcat(tipo, subtipo) == "":
                pairs.add(f"{tipo}|{subtipo}")
        return pairs

    # ── Property extraction ───────────────────────────────────────────────────

    def _extract_properties(
        self,
        root: ET.Element,
        person_by_codigo_imovel: dict[str, PersonRecord],
    ) -> PropertyExtractionResult:
        prop_result = PropertyExtractionResult()
        imob_doc = re.sub(r"\D", "", self.context.get("imob_cpf_cnpj", ""))

        for imovel in root.findall(".//Imovel"):
            codigo_orig = _txt(imovel, "CodigoImovel")
            # Remove suffix after underscore (e.g. "AD0001_BRC" → "AD0001")
            codigo = codigo_orig.split("_")[0]
            if not codigo:
                continue

            # Status
            ativo      = _txt(imovel, "Ativo")
            publicado  = _txt(imovel, "Publicado")
            status = "1" if ativo == "1" and publicado == "1" else "5"

            # Tipo (departamento)
            sv_raw = _txt(imovel, "PrecoVenda")
            rv_raw = _txt(imovel, "PrecoLocacao")
            try:
                sv = float(sv_raw) if sv_raw else 0.0
            except ValueError:
                sv = 0.0
            try:
                rv = float(rv_raw) if rv_raw else 0.0
            except ValueError:
                rv = 0.0
            tipo = "SL" if sv and rv else ("S" if sv else "L")

            # Subcategoria — custom override → _SUB dict → "" (exibido para revisão)
            tipo_imovel = _txt(imovel, "TipoImovel")
            sub_tipo    = _txt(imovel, "SubTipoImovel")
            sub_cat     = _resolve_subcat(tipo_imovel, sub_tipo)

            pr = PropertyRecord()
            pr.codigo       = codigo
            pr.imobiliaria  = "1"
            pr.status       = status
            pr.tipo         = tipo
            pr.sub_categoria = sub_cat

            pr.valor_venda   = _fmt(sv_raw) if sv else ""
            pr.valor_locacao = _fmt(rv_raw) if rv else ""

            pr.data_registro = date.today().isoformat()
            pr.titulo_site  = _nfc(_txt(imovel, "TituloImovel"))
            pr.obs_site     = _nfc(_strip_html(_txt(imovel, "Observacao")))
            pr.observacao   = _nfc(_strip_html(_txt(imovel, "ObservacoesInternas")))

            pr.mostrar_site = publicado if publicado in ("0", "1") else "0"
            pr.street_view  = "1"
            pr.mapa_site    = "1"

            pr.valor_condominio = _fmt(_txt(imovel, "PrecoCondominio"))
            pr.ano_construcao   = _txt(imovel, "AnoConstrucao")

            # Address
            cep_raw = re.sub(r"\D", "", _txt(imovel, "CEP"))
            cidade  = _txt(imovel, "Cidade")
            estado  = _txt(imovel, "UF")

            bairro, rua, numero_end, complemento = normalize_address(
                _txt(imovel, "Bairro"),
                _txt(imovel, "Endereco"),
                _txt(imovel, "Numero"),
                _txt(imovel, "Complemento"),
            )

            cidade, estado = fill_city_state(cep_raw, cidade, estado)
            cep = cep_raw
            if not is_valid_cep(cep) and cidade and estado:
                cep = lookup_cep_by_city(cidade, estado) or ""

            pr.cep        = cep
            pr.cidade     = _nfc(cidade)
            pr.estado     = estado
            pr.bairro     = _nfc(bairro)
            pr.rua        = _nfc(rua)
            pr.numero_end = numero_end
            pr.complemento = _nfc(complemento)

            # Rooms
            pr.dormitorios = _txt(imovel, "QtdDormitorios")
            pr.suites      = _txt(imovel, "QtdSuites")
            pr.garagem     = _txt(imovel, "QtdVagas")
            pr.salas       = _txt(imovel, "QtdSalas")
            pr.copas       = _txt(imovel, "Copa")
            pr.despensas   = _txt(imovel, "Despensa")
            pr.lavabos     = _txt(imovel, "lavabo")
            pr.halls       = _txt(imovel, "hall")
            pr.dorm_funcionario     = _txt(imovel, "QuartoServico")
            pr.banheiro_funcionario = _txt(imovel, "WCEmpregada")
            pr.escritorio  = _txt(imovel, "Escritorio")
            pr.depositos   = _txt(imovel, "deposito") or _txt(imovel, "DepositoPrivativoNoSubsolo")
            pr.closets     = _txt(imovel, "closet")
            pr.casa_empregado = _txt(imovel, "DependenciaEmpregados")

            # Banheiros = QtdBanheiros - QtdSuites (se positivo), senão QtdBanheiros
            try:
                nb = int(_txt(imovel, "QtdBanheiros") or 0)
                ns = int(_txt(imovel, "QtdSuites") or 0)
                pr.banheiros = str(max(nb - ns, 0) if nb > ns else nb)
            except ValueError:
                pr.banheiros = _txt(imovel, "QtdBanheiros")

            # Lavanderia = Lavanderia + lavanderia_coletiva
            try:
                lav = int(_txt(imovel, "Lavanderia") or 0) + int(_txt(imovel, "lavanderia_coletiva") or 0)
                pr.lavanderias = str(lav) if lav else ""
            except ValueError:
                pr.lavanderias = ""

            # Areas: area_util = ifnull(AreaUtil, AreaTotal); area_total = ifnull(AreaTotal, AreaUtil)
            au = _fmt(_txt(imovel, "AreaUtil"))
            at = _fmt(_txt(imovel, "AreaTotal"))
            pr.area_util      = au or at
            pr.area_total     = at or au
            pr.area_construida = au or at

            # Characteristics
            features: list[str] = []
            seen_f: set[str] = set()
            for tag, nome_msys in _BOOL_CHARS:
                if _txt(imovel, tag) == "1" and nome_msys not in seen_f:
                    features.append(nome_msys)
                    seen_f.add(nome_msys)

            pr.caracteristicas_sim_nao = build_sim_nao(features)
            for field, qty in map_characteristics_to_fields(features).items():
                if not getattr(pr, field, ""):
                    setattr(pr, field, qty)

            prop_result.properties.append(pr)

            # IPTU
            iptu_val = _fmt(_txt(imovel, "ValorIPTU"))
            if iptu_val and float(iptu_val) > 0:
                prop_result.iptu.append(PropertyIptuRecord(
                    codigo_imovel=codigo,
                    tipo_iptu="IPTU Principal",
                    inscricao_iptu="",
                    valor_mensal_iptu=iptu_val,
                    valor_anual_iptu="0",
                    parcelas_iptu="0",
                    perc_iptu="100",
                    obs_iptu="",
                ))

            # Owner
            person = person_by_codigo_imovel.get(codigo_orig)
            if person:
                ow_cpf    = person.cpf
                ow_cnpj   = "" if person.cpf else person.cnpj
                ow_codigo = person.codigo
                ow_nome   = person.nome
            else:
                ow_cpf    = ""
                ow_cnpj   = imob_doc
                ow_codigo = ""
                ow_nome   = ""

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
                banco="",
                agencia="",
                digito_agencia="",
                conta="",
                digito_conta="",
                poupanca="0",
            ))

            # Captivador
            if imob_doc:
                prop_result.captivators.append(PropertyCaptivatorRecord(
                    codigo_imovel=codigo,
                    cpf_cnpj=imob_doc,
                    departamento=tipo,
                    data_captacao="",
                ))

        return prop_result
