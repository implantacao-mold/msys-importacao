from __future__ import annotations
import re
from dataclasses import dataclass, field


def normalize_address(bairro: str, rua: str, numero: str, complemento: str) -> tuple[str, str, str, str]:
    """Normaliza campos de endereço de imóvel.

    Bairro/rua vazios → "Não Informado".
    Número vazio → "0". Número com letras → move para complemento e zera.
    Retorna (bairro, rua, numero, complemento).
    """
    bairro = bairro or "Não Informado"
    rua = rua or "Não Informado"
    if not numero:
        numero = "0"
    elif re.search(r"\D", numero):
        complemento = " ".join(p for p in [complemento, f"Nº {numero}"] if p)
        numero = "0"
    return bairro, rua, numero, complemento


@dataclass
class PropertyRecord:
    codigo: str = ""
    data_registro: str = ""
    imobiliaria: str = ""
    status: str = ""
    tipo: str = ""
    sub_categoria: str = ""
    valor_venda: str = ""
    valor_locacao: str = ""
    desligar_energia: str = ""
    desligar_agua: str = ""
    ocupado: str = ""
    mostrar_site: str = ""
    destaque: str = ""
    locacao_exclusiva: str = ""
    venda_exclusiva: str = ""
    nao_aluga_estudantes: str = ""
    street_view: str = ""
    mapa_site: str = ""
    observacao: str = ""
    obs_site: str = ""
    url_video: str = ""
    matricula: str = ""
    num_iptu: str = ""
    valor_anual_iptu: str = ""
    valor_mensal_iptu: str = ""
    parcelas_iptu: str = ""
    perc_iptu: str = ""
    agua_esgoto: str = ""
    energia_uc: str = ""
    finalidade: str = ""
    id_condominio: str = ""
    cep: str = ""
    cidade: str = ""
    bairro: str = ""
    estado: str = ""
    rua: str = ""
    numero_end: str = ""
    complemento: str = ""
    num_apto: str = ""
    num_cond: str = ""
    num_piso: str = ""
    num_bloco: str = ""
    obs_cond: str = ""
    num_lote: str = ""
    num_quadra: str = ""
    dormitorios: str = ""
    banheiros: str = ""
    area_util: str = ""
    area_total: str = ""
    area_construida: str = ""
    nome_propriedade: str = ""
    lado1: str = ""
    lado2: str = ""
    lado3: str = ""
    lado4: str = ""
    area_total_rural: str = ""
    unidade_medida: str = ""
    suites: str = ""
    closets: str = ""
    salas: str = ""
    copas: str = ""
    cozinhas: str = ""
    despensas: str = ""
    lavanderias: str = ""
    lavabos: str = ""
    halls: str = ""
    sala_jogos: str = ""
    dorm_funcionario: str = ""
    banheiro_funcionario: str = ""
    escritorio: str = ""
    despejo: str = ""
    depositos: str = ""
    recepcoes: str = ""
    pe_direito: str = ""
    topografia: str = ""
    garagem: str = ""
    garagem_coberta: str = ""
    tipo_garagem: str = ""
    obs_garagem: str = ""
    tipo_acabamento: str = ""
    tipo_piso: str = ""
    tipo_forro: str = ""
    est_conservacao: str = ""
    obs_permuta: str = ""
    inst_financiamento: str = ""
    meses_restantes: str = ""
    valor_prestacao: str = ""
    saldo_devedor: str = ""
    dist_asfalto: str = ""
    medida_dist_asfalto: str = ""
    dist_terra: str = ""
    medida_dist_terra: str = ""
    como_chegar: str = ""
    agua: str = ""
    caixa_agua: str = ""
    lago: str = ""
    lagoa: str = ""
    poco_artesiano: str = ""
    poco_cacimba: str = ""
    represa: str = ""
    baia: str = ""
    canil: str = ""
    capela: str = ""
    casa_empregado: str = ""
    casa_sede: str = ""
    estabulo: str = ""
    galpao: str = ""
    granja: str = ""
    mangueiro: str = ""
    pocilga: str = ""
    benfeitorias: str = ""
    plantacao: str = ""
    plantacao_outros: str = ""
    tipo_terra: str = ""
    pomar: str = ""
    pomar_outros: str = ""
    padrao_acabamento: str = ""
    estado_conservacao: str = ""
    idade_imovel: str = ""
    isolamento: str = ""
    isolamento_outros: str = ""
    caracteristicas_sim_nao: str = ""
    perc_administracao: str = ""
    valor_administracao: str = ""
    perc_intermediacao: str = ""
    valor_intermediacao: str = ""
    num_parcelas: str = ""
    tipo_garantia: str = ""
    meses_garantido: str = ""
    pagto_proprietario: str = ""
    dia_pagto: str = ""
    dias_pagto_prop: str = ""
    latitude: str = ""
    longitude: str = ""
    ponto_referencia: str = ""
    valor_condominio: str = ""
    titulo_site: str = ""
    ano_construcao: str = ""

    def to_row(self) -> list[str]:
        return [
            (f"'{self.codigo}" if self.codigo else ""), self.data_registro, self.imobiliaria, self.status,
            self.tipo, self.sub_categoria, self.valor_venda, self.valor_locacao,
            self.desligar_energia, self.desligar_agua, self.ocupado, self.mostrar_site,
            self.destaque, self.locacao_exclusiva, self.venda_exclusiva,
            self.nao_aluga_estudantes, self.street_view, self.mapa_site,
            self.observacao, self.obs_site, self.url_video, self.matricula,
            self.num_iptu, self.valor_anual_iptu, self.valor_mensal_iptu, self.parcelas_iptu,
            self.perc_iptu, self.agua_esgoto, self.energia_uc,
            self.finalidade, self.id_condominio,
            (f"'{self.cep}" if self.cep else ""), self.cidade, self.bairro, self.estado, self.rua,
            self.numero_end, self.complemento,
            self.num_apto, self.num_cond, self.num_piso, self.num_bloco,
            self.obs_cond, self.num_lote, self.num_quadra,
            self.dormitorios, self.banheiros,
            self.area_util, self.area_total, self.area_construida,
            self.nome_propriedade,
            self.lado1, self.lado2, self.lado3, self.lado4,
            self.area_total_rural, self.unidade_medida,
            self.suites, self.closets, self.salas,
            self.copas, self.cozinhas, self.despensas, self.lavanderias, self.lavabos,
            self.halls, self.sala_jogos, self.dorm_funcionario, self.banheiro_funcionario,
            self.escritorio, self.despejo, self.depositos, self.recepcoes,
            self.pe_direito, self.topografia,
            self.garagem, self.garagem_coberta, self.tipo_garagem, self.obs_garagem,
            self.tipo_acabamento, self.tipo_piso, self.tipo_forro, self.est_conservacao, self.obs_permuta,
            self.inst_financiamento, self.meses_restantes, self.valor_prestacao, self.saldo_devedor,
            self.dist_asfalto, self.medida_dist_asfalto, self.dist_terra, self.medida_dist_terra,
            self.como_chegar,
            self.agua, self.caixa_agua, self.lago, self.lagoa,
            self.poco_artesiano, self.poco_cacimba, self.represa, self.baia,
            self.canil, self.capela, self.casa_empregado, self.casa_sede,
            self.estabulo, self.galpao, self.granja, self.mangueiro, self.pocilga,
            self.benfeitorias, self.plantacao, self.plantacao_outros, self.tipo_terra,
            self.pomar, self.pomar_outros,
            self.padrao_acabamento, self.estado_conservacao, self.idade_imovel,
            self.isolamento, self.isolamento_outros,
            self.caracteristicas_sim_nao,
            self.perc_administracao, self.valor_administracao,
            self.perc_intermediacao, self.valor_intermediacao,
            self.num_parcelas, self.tipo_garantia, self.meses_garantido,
            self.pagto_proprietario, self.dia_pagto, self.dias_pagto_prop,
            self.latitude, self.longitude, self.ponto_referencia,
            self.valor_condominio, self.titulo_site, self.ano_construcao,
        ]


@dataclass
class PropertyOwnerRecord:
    codigo_imovel: str = ""
    cpf: str = ""
    cnpj: str = ""
    codigo_pessoa: str = ""
    percentual: str = ""


@dataclass
class PropertyOwnerFavoredRecord:
    codigo_imovel: str = ""
    cpf: str = ""
    cnpj: str = ""
    codigo_pessoa: str = ""
    tipo_pagamento: str = ""
    percentual: str = ""
    cpf_favorecido: str = ""
    cnpj_favorecido: str = ""
    id_favorecido: str = ""
    favorecido: str = ""
    banco: str = ""
    agencia: str = ""
    digito_agencia: str = ""
    conta: str = ""
    digito_conta: str = ""
    poupanca: str = ""
    # campos mantidos por compatibilidade (não exportados)
    tipo_conta: str = ""
    chave_pix: str = ""
    tipo_chave_pix: str = ""


@dataclass
class PropertyCaptivatorRecord:
    codigo_imovel: str = ""
    cpf_cnpj: str = ""
    departamento: str = ""
    data_captacao: str = ""


@dataclass
class PropertyIptuRecord:
    codigo_imovel: str = ""
    tipo_iptu: str = ""
    inscricao_iptu: str = ""
    valor_mensal_iptu: str = ""
    valor_anual_iptu: str = ""
    parcelas_iptu: str = ""
    perc_iptu: str = ""
    obs_iptu: str = ""


@dataclass
class PropertyExtractionResult:
    properties: list[PropertyRecord] = field(default_factory=list)
    owners: list[PropertyOwnerRecord] = field(default_factory=list)
    owners_favored: list[PropertyOwnerFavoredRecord] = field(default_factory=list)
    captivators: list[PropertyCaptivatorRecord] = field(default_factory=list)
    iptu: list[PropertyIptuRecord] = field(default_factory=list)
