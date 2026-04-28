import pytest
from mappers.kenlo import KenloMapper

MAPPER = KenloMapper()

_FILES = {
    "clientes.xlsx": [
        {"id cliente": "1", "nome": "Joao Proprietario", "cpf": "12345678901",
         "emails": "joao@example.com", "telefones": "(11) 99999-8888"},
        {"id cliente": "2", "nome": "Maria Compradora", "cpf": "98765432100",
         "emails": "maria@example.com", "telefones": ""},
        {"id cliente": "3", "nome": "", "cpf": ""},
    ],
    "imoveis.xlsx": [
        {"id cliente": "1"},
    ],
    "usuarios.xlsx": [
        {"id": "10", "nome": "Carlos Agente", "cpf": "11122233344",
         "e-mail": "carlos@agencia.com", "celular": "11988887777"},
    ],
}


def test_cliente_ow_por_presenca_em_imoveis():
    r = MAPPER.extract_zip(_FILES)
    joao = next(p for p in r.persons if p.codigo == "1")
    assert joao.tipo == "OW"
    assert joao.nome == "Joao Proprietario"
    assert joao.cpf == "12345678901"


def test_cliente_bu_sem_imovel():
    r = MAPPER.extract_zip(_FILES)
    maria = next(p for p in r.persons if p.codigo == "2")
    assert maria.tipo == "BU"


def test_usuario_tipo_em():
    r = MAPPER.extract_zip(_FILES)
    em = [p for p in r.persons if p.tipo == "EM"]
    assert len(em) == 1
    assert em[0].nome == "Carlos Agente"
    assert em[0].cpf == "11122233344"


def test_cliente_sem_nome_ignorado():
    r = MAPPER.extract_zip(_FILES)
    codigos = {p.codigo for p in r.persons}
    # "3" tem nome vazio → ignorado
    assert "3" not in codigos


def test_email_capturado():
    r = MAPPER.extract_zip(_FILES)
    emails_joao = [e for e in r.emails if e.codigo_pessoa == "1"]
    assert len(emails_joao) == 1
    assert emails_joao[0].email == "joao@example.com"


def test_email_usuario():
    r = MAPPER.extract_zip(_FILES)
    emails_em = [e for e in r.emails if e.tipo_pessoa == "EM"]
    assert len(emails_em) == 1
    assert emails_em[0].email == "carlos@agencia.com"


def test_telefone_de_texto_estruturado():
    r = MAPPER.extract_zip(_FILES)
    phones_joao = [ph for ph in r.phones if ph.codigo_pessoa == "1"]
    assert len(phones_joao) == 1
    assert phones_joao[0].ddd == "11"


def test_telefone_usuario_celular():
    r = MAPPER.extract_zip(_FILES)
    phones_em = [ph for ph in r.phones if ph.tipo_pessoa == "EM"]
    assert len(phones_em) == 1
    assert phones_em[0].ddd == "11"
    assert phones_em[0].tipo_telefone == "M"


def test_sem_imoveis_todos_sao_bu():
    files = {
        "clientes.xlsx": [
            {"id cliente": "1", "nome": "Pessoa A", "cpf": "12345678901"},
        ],
        "imoveis.xlsx": [],
        "usuarios.xlsx": [],
    }
    r = MAPPER.extract_zip(files)
    assert r.persons[0].tipo == "BU"


def test_total_pessoas():
    r = MAPPER.extract_zip(_FILES)
    # "Sem Nome" é ignorado → 2 clientes + 1 usuario
    assert len(r.persons) == 3
