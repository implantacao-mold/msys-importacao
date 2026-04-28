from __future__ import annotations
import csv
import html
import os
import re
import unicodedata

from core.base_mapper import ExtractionResult
from core.cep_lookup import fix_record_cep
from core.schema import ENCODING, SEPARATOR, PERSON_COLUMNS, EMAIL_COLUMNS, PHONE_COLUMNS
from core.property_exporter import export_properties


def _q(v: str) -> str:
    """Prefix document fields with single-quote so importers treat them as text (preserves leading zeros)."""
    s = str(v) if v else ""
    return f"'{s}" if s else ""


def _sanitize(value: str) -> str:
    text = str(value) if value is not None else ""
    # Decode XML/HTML numeric and named entity references (&#xA; &#10; &amp; etc.)
    text = html.unescape(text)
    # Remove any residual XML character references that html.unescape may have missed
    text = re.sub(r"&#x[0-9A-Fa-f]+;|&#\d+;", " ", text)
    text = unicodedata.normalize("NFC", text)
    return text.replace("\r\n", " ").replace("\n", " ").replace("\r", " ").replace("\t", " ")


def _person_to_row(p) -> list[str]:
    return [
        p.codigo,                    # Código
        _q(p.cpf or p.cnpj),         # CPF/CNPJ
        p.telefone,                  # Telefone
        p.nome,                      # Nome
        p.observacao,                # Observação
        p.como_chegou,               # Como chegou
        p.tipo,                      # Tipo
        p.rg,                        # RG
        p.data_nascimento,           # Data Nascimento
        p.local_nascimento,          # Local de nascimento
        p.sexo,                      # Sexo
        p.salario,                   # Salário
        p.orgao_expedidor,           # Órgão emissor
        p.estado_civil,              # Estado civil
        p.profissao,                 # Profissão
        p.escolaridade,              # Escolaridade
        p.nacionalidade,             # Nacionalidade
        p.nome_fantasia,             # Razão Social
        p.inscricao_estadual,        # Núm. Inscr. Estadual
        p.inscricao_municipal,       # Núm. Inscr. Municipal
        _q(p.cpf_representante),     # CPF do responsável
        p.rg_representante,          # RG do responsável
        p.nome_representante,        # Nome do responsável
        p.cep,                       # CEP
        p.cidade,                    # Cidade
        p.bairro,                    # Bairro
        p.estado,                    # Estado
        p.endereco,                  # Rua
        p.numero,                    # Número
        p.complemento,               # Complemento
        p.num_apto,                  # Num apto
        p.num_cond,                  # Num. Cond.
        p.num_piso,                  # Núm. Piso
        p.num_bloco,                 # Núm.Bloco
        p.obs_cond,                  # Obs. Cond.
        p.num_lote,                  # Núm. Lote
        p.num_bloco,                 # Núm. bloco
        p.cobrar_taxa_bco,           # Cobrar taxa de bco
        p.imobiliaria,               # Imobiliária
        p.departamento,              # Departamento
        p.cargo,                     # Cargo
        p.possui_acesso,             # Possui acesso ao sistema
        p.login,                     # login
        p.senha_md5,                 # SenhaMD5
        p.tipo_captador,             # Tipo captador
        p.nao_trocar_email,          # Não trocar no envio automático de e-mail
        p.comissao,                  # % de comissão
        p.comissao_loc,              # % Comissao Loc
        p.area_atuacao,              # Área de atuação
        p.creci,                     # Creci
        p.vinculo_imobiliaria,       # Vínculo com a imobiliária
        p.tipo_corretor,             # Tipo corretor
        p.piso_salarial,             # Piso salarial
        p.tipo_servico,              # Tipo serviço prestado
        _q(p.conjuge_cpf),           # CPF Cônjuge
        p.conjuge_nome,              # Nome cônjuge
        p.conjuge_rg,                # RG Cônjuge
    ]


def _code_key(code: str):
    try:
        return (0, int(code), "")
    except (ValueError, TypeError):
        return (1, 0, str(code or ""))


def export(result: ExtractionResult, output_dir: str) -> None:
    person_dir = os.path.join(output_dir, "PERSON")
    os.makedirs(person_dir, exist_ok=True)

    def write_csv(path: str, columns: list[str], rows: list[list[str]]) -> None:
        with open(path, "w", newline="", encoding=ENCODING, errors="replace") as f:
            writer = csv.writer(f, delimiter=SEPARATOR)
            writer.writerow(columns)
            for row in rows:
                writer.writerow([_sanitize(v) for v in row])

    persons = sorted(result.persons, key=lambda p: _code_key(p.codigo))
    emails  = sorted(result.emails,  key=lambda e: _code_key(e.codigo_pessoa))
    phones  = sorted(result.phones,  key=lambda p: _code_key(p.codigo_pessoa))

    # Normaliza CEP de todas as pessoas (válido para todos os mappers)
    for p in persons:
        fix_record_cep(p)

    write_csv(
        os.path.join(person_dir, "PERSON.csv"),
        PERSON_COLUMNS,
        [_person_to_row(p) for p in persons],
    )

    write_csv(
        os.path.join(person_dir, "EMAIL.csv"),
        EMAIL_COLUMNS,
        [[e.codigo_pessoa, e.email] for e in emails],
    )

    write_csv(
        os.path.join(person_dir, "PHONE.csv"),
        PHONE_COLUMNS,
        [[p.codigo_pessoa, p.ddd, p.telefone, p.tipo_telefone] for p in phones],
    )

    if result.property_result is not None:
        export_properties(result.property_result, output_dir)
