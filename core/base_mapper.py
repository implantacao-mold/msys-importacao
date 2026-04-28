from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PersonRecord:
    codigo: str = ""
    tipo: str = ""
    nome: str = ""
    nome_fantasia: str = ""
    cpf: str = ""
    cnpj: str = ""
    rg: str = ""
    orgao_expedidor: str = ""
    data_nascimento: str = ""
    sexo: str = ""
    estado_civil: str = ""
    nacionalidade: str = ""
    profissao: str = ""
    escolaridade: str = ""
    salario: str = ""
    cep: str = ""
    cidade: str = ""
    bairro: str = ""
    estado: str = ""
    endereco: str = ""
    numero: str = ""
    complemento: str = ""
    observacao: str = ""
    telefone: str = ""
    como_chegou: str = ""
    local_nascimento: str = ""
    inscricao_estadual: str = ""
    inscricao_municipal: str = ""
    cpf_representante: str = ""
    rg_representante: str = ""
    nome_representante: str = ""
    num_apto: str = ""
    num_cond: str = ""
    num_piso: str = ""
    num_bloco: str = ""
    obs_cond: str = ""
    num_lote: str = ""
    cobrar_taxa_bco: str = ""
    imobiliaria: str = ""
    departamento: str = ""
    cargo: str = ""
    possui_acesso: str = ""
    login: str = ""
    senha_md5: str = ""
    tipo_captador: str = ""
    nao_trocar_email: str = ""
    comissao: str = ""
    comissao_loc: str = ""
    area_atuacao: str = ""
    creci: str = ""
    vinculo_imobiliaria: str = ""
    tipo_corretor: str = ""
    piso_salarial: str = ""
    tipo_servico: str = ""
    conjuge_cpf: str = ""
    conjuge_nome: str = ""
    conjuge_rg: str = ""
    conjuge_orgao_expedidor: str = ""
    conjuge_data_nascimento: str = ""
    conjuge_sexo: str = ""
    conjuge_profissao: str = ""
    conjuge_escolaridade: str = ""
    conjuge_salario: str = ""
    conjuge_nacionalidade: str = ""
    conjuge_estado_civil: str = ""
    conjuge_email: str = ""
    conjuge_telefone: str = ""
    banco: str = ""
    agencia: str = ""
    conta: str = ""
    tipo_conta: str = ""
    favorecido: str = ""
    cpf_favorecido: str = ""
    cnpj_favorecido: str = ""
    banco_favorecido: str = ""
    agencia_favorecido: str = ""
    conta_favorecido: str = ""
    tipo_conta_favorecido: str = ""
    chave_pix: str = ""
    tipo_chave_pix: str = ""
    data_fundacao: str = ""
    site: str = ""
    observacao_empresa: str = ""


@dataclass
class EmailRecord:
    codigo_pessoa: str = ""
    tipo_pessoa: str = ""
    email: str = ""
    tipo_email: str = ""


@dataclass
class PhoneRecord:
    codigo_pessoa: str = ""
    tipo_pessoa: str = ""
    ddi: str = "55"
    ddd: str = ""
    telefone: str = ""
    tipo_telefone: str = ""
    ramal: str = ""


@dataclass
class ExtractionResult:
    persons: list[PersonRecord] = field(default_factory=list)
    emails: list[EmailRecord] = field(default_factory=list)
    phones: list[PhoneRecord] = field(default_factory=list)
    property_result: Any = None


class BaseMapper(ABC):
    NAME: str = ""
    EXTENSIONS: list[str] = []
    DESCRIPTION: str = ""
    context: dict = {}

    def can_handle(self, filename: str) -> bool:
        lower = filename.lower()
        return any(lower.endswith(ext) for ext in self.EXTENSIONS)

    def extract(self, data: list[dict]) -> ExtractionResult:
        raise NotImplementedError

    def extract_zip(self, files: dict[str, Any]) -> ExtractionResult:
        raise NotImplementedError

    def scan_characteristics(self, data: Any) -> set[str]:
        """Retorna nomes brutos de características encontradas no arquivo.

        Override em mappers que exportam imóveis para habilitar o painel de revisão.
        """
        return set()

    def scan_subcategories(self, data: Any) -> set[str]:
        """Retorna pares 'TipoImovel|SubTipoImovel' sem mapeamento configurado.

        Override em mappers que exportam imóveis com subcategoria dinâmica.
        """
        return set()
