import hashlib
import pytest
from mappers.tec_imob import TecImobMapper

MAPPER = TecImobMapper()

_ROWS = [
    {"Nome": "Joao Proprietario", "Categorias": "proprietário", "CPF/CNPJ": "12345678901",
     "Telefones": "11999998888", "E-mail": "joao@example.com"},
    {"Nome": "Maria Locataria", "Categorias": "locatário", "CPF/CNPJ": "98765432100",
     "Telefones": "11988887777", "E-mail": ""},
    {"Nome": "Pedro Comprador", "Categorias": "comprador", "CPF/CNPJ": "11122233344",
     "Telefones": ""},
    {"Nome": "Empresa LTDA", "Categorias": "proprietário", "CPF/CNPJ": "12345678000195",
     "Telefones": "", "E-mail": "empresa@ltda.com"},
]


def _md5(nome: str, telefones: str = "") -> str:
    return hashlib.md5(f"{nome}-{telefones}".encode("utf-8")).hexdigest()


def test_tipo_proprietario():
    r = MAPPER.extract(_ROWS)
    ow = [p for p in r.persons if p.tipo == "OW"]
    assert len(ow) == 2


def test_tipo_locatario():
    r = MAPPER.extract(_ROWS)
    oc = [p for p in r.persons if p.tipo == "OC"]
    assert len(oc) == 1
    assert oc[0].nome == "Maria Locataria"


def test_tipo_comprador():
    r = MAPPER.extract(_ROWS)
    bu = [p for p in r.persons if p.tipo == "BU"]
    assert len(bu) == 1
    assert bu[0].nome == "Pedro Comprador"


def test_codigo_md5():
    r = MAPPER.extract(_ROWS)
    joao = next(p for p in r.persons if p.nome == "Joao Proprietario")
    assert joao.codigo == _md5("Joao Proprietario", "11999998888")
    assert len(joao.codigo) == 32


def test_cpf_11_digitos():
    r = MAPPER.extract(_ROWS)
    joao = next(p for p in r.persons if p.nome == "Joao Proprietario")
    assert joao.cpf == "12345678901"
    assert joao.cnpj == ""


def test_cnpj_14_digitos():
    r = MAPPER.extract(_ROWS)
    empresa = next(p for p in r.persons if p.nome == "Empresa LTDA")
    assert empresa.cnpj == "12345678000195"
    assert empresa.cpf == ""


def test_email_capturado():
    r = MAPPER.extract(_ROWS)
    joao_codigo = _md5("Joao Proprietario", "11999998888")
    emails_joao = [e for e in r.emails if e.codigo_pessoa == joao_codigo]
    assert len(emails_joao) == 1
    assert emails_joao[0].email == "joao@example.com"


def test_telefone_capturado():
    r = MAPPER.extract(_ROWS)
    joao_codigo = _md5("Joao Proprietario", "11999998888")
    phones_joao = [ph for ph in r.phones if ph.codigo_pessoa == joao_codigo]
    assert len(phones_joao) == 1
    assert phones_joao[0].ddd == "11"
    assert phones_joao[0].tipo_telefone == "M"


def test_multi_sheet_seleciona_clientes():
    data = {
        "Clientes": _ROWS,
        "Configuracoes": [{"chave": "valor"}],
    }
    r = MAPPER.extract(data)
    assert len(r.persons) == len(_ROWS)


def test_multi_sheet_fallback_cliente():
    data = {
        "minha_cliente_lista": _ROWS,
    }
    r = MAPPER.extract(data)
    assert len(r.persons) == len(_ROWS)


def test_ddi_55_removido():
    rows = [{"Nome": "Pessoa A", "Categorias": "comprador",
             "Telefones": "5511987654321"}]
    r = MAPPER.extract(rows)
    pessoa_codigo = _md5("Pessoa A", "5511987654321")
    phones = [ph for ph in r.phones if ph.codigo_pessoa == pessoa_codigo]
    assert phones[0].ddd == "11"
    assert phones[0].numero if hasattr(phones[0], "numero") else phones[0].telefone == "987654321"


def test_categoria_desconhecida_vira_bu():
    rows = [{"Nome": "Desconhecido", "Categorias": "investidor"}]
    r = MAPPER.extract(rows)
    assert r.persons[0].tipo == "BU"


def test_sem_nome_ignorado():
    rows = [{"Nome": "", "Categorias": "comprador"}]
    r = MAPPER.extract(rows)
    assert len(r.persons) == 0
