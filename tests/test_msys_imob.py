import pytest
from mappers.msys_imob import MsysImobMapper

MAPPER = MsysImobMapper()

_BASE_SQL = """\
INSERT INTO person (idt_person, nam_person, num_document, typ_person, idt_address) VALUES
('P001', 'Joao Silva', '12345678901', 'owner', 'A001'),
('P002', 'Maria Santos', '98765432100', 'buyer', 'A002'),
('P003', 'Carlos Lima', '11122233344', 'occupant', 'A001'),
('P004', 'Ana Costa', '55566677788', 'guarantor', 'A001');

INSERT INTO person_individual (idt_person, nam_fantasy, idt_person_spouse) VALUES
('P001', 'Joao Silva', 'P002'),
('P002', 'Maria Santos', ''),
('P003', 'Carlos Lima', ''),
('P004', 'Ana Costa', '');

INSERT INTO address (idt_address, nam_city, nam_neighborhood, idt_state, nam_street, num_address, des_complement, num_zip_code) VALUES
('A001', 'Sao Paulo', 'Centro', 'SP', 'Rua das Flores', '123', 'Apto 1', '01310100'),
('A002', 'Campinas', 'Vila Nova', 'SP', 'Av Paulista', '456', '', '13010100');

INSERT INTO person_contact (idt_person, typ_contact, des_contact) VALUES
('P001', 'phone', '11999998888'),
('P001', 'email', 'joao@example.com'),
('P002', 'mobile', '11988887777');
"""


def test_extracao_basica():
    r = MAPPER.extract(_BASE_SQL)
    assert len(r.persons) == 4


def test_tipo_owner():
    r = MAPPER.extract(_BASE_SQL)
    ow = [p for p in r.persons if p.tipo == "OW"]
    assert len(ow) == 1
    assert ow[0].nome == "Joao Silva"
    assert ow[0].cpf == "12345678901"


def test_tipo_buyer():
    r = MAPPER.extract(_BASE_SQL)
    bu = [p for p in r.persons if p.tipo == "BU"]
    assert len(bu) == 1
    assert bu[0].nome == "Maria Santos"


def test_tipo_occupant():
    r = MAPPER.extract(_BASE_SQL)
    oc = [p for p in r.persons if p.tipo == "OC"]
    assert len(oc) == 1


def test_tipo_guarantor():
    r = MAPPER.extract(_BASE_SQL)
    gu = [p for p in r.persons if p.tipo == "GU"]
    assert len(gu) == 1


def test_conjuge_cpf_buscado_da_tabela_person():
    """Bug fix: conjuge_cpf deve ser buscado de num_document na tabela person."""
    r = MAPPER.extract(_BASE_SQL)
    joao = next(p for p in r.persons if p.codigo == "P001")
    assert joao.conjuge_nome == "Maria Santos"
    assert joao.conjuge_cpf == "98765432100"


def test_conjuge_vazio_sem_spouse_id():
    r = MAPPER.extract(_BASE_SQL)
    maria = next(p for p in r.persons if p.codigo == "P002")
    assert maria.conjuge_nome == ""
    assert maria.conjuge_cpf == ""


def test_endereco_extraido():
    r = MAPPER.extract(_BASE_SQL)
    joao = next(p for p in r.persons if p.codigo == "P001")
    assert joao.cidade == "Sao Paulo"
    assert joao.bairro == "Centro"
    assert joao.estado == "SP"
    assert joao.endereco == "Rua das Flores"
    assert joao.cep == "01310100"


def test_telefone_extraido():
    r = MAPPER.extract(_BASE_SQL)
    phones_p001 = [ph for ph in r.phones if ph.codigo_pessoa == "P001"]
    assert len(phones_p001) == 1
    assert phones_p001[0].ddd == "11"
    assert phones_p001[0].telefone == "999998888"


def test_email_extraido():
    r = MAPPER.extract(_BASE_SQL)
    emails_p001 = [e for e in r.emails if e.codigo_pessoa == "P001"]
    assert len(emails_p001) == 1
    assert emails_p001[0].email == "joao@example.com"


def test_deduplicacao_mesmo_tipo():
    sql_dup = _BASE_SQL + "\n-- duplicate:\n" + _BASE_SQL
    r = MAPPER.extract(sql_dup)
    # Apesar de 8 linhas de INSERT, só 4 pessoas únicas (chave codigo|tipo)
    assert len(r.persons) == 4


def test_extract_zip():
    r = MAPPER.extract_zip({"dados.sql": _BASE_SQL})
    assert len(r.persons) == 4


def test_extract_zip_sem_sql():
    r = MAPPER.extract_zip({"dados.xlsx": "não-sql"})
    assert len(r.persons) == 0


def test_tipo_desconhecido_vira_bu():
    sql = """\
INSERT INTO person (idt_person, nam_person, num_document, typ_person, idt_address) VALUES
('X001', 'Pessoa Desconhecida', '00011122233', 'unknown_type', '');
INSERT INTO person_individual (idt_person, nam_fantasy, idt_person_spouse) VALUES
('X001', 'Pessoa Desconhecida', '');
"""
    r = MAPPER.extract(sql)
    assert r.persons[0].tipo == "BU"
