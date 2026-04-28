import pytest
from mappers.vista import VistaMapper

MAPPER = VistaMapper()

_CADCLI = """\
INSERT INTO `CADCLI` (`CODIGO_C`, `NOME`, `CPF`, `PROPRIETARIO`, `COMPRADOR`, `FIADOR`, `AUTORIZADO`, `NOME_E`, `CPF_E`, `EMAIL_R`, `FONE_R`, `CELULAR`) VALUES
('1', 'Joao Proprietario', '123.456.789-00', 'Sim', 'Nao', 'Nao', 'Nao', 'Maria Conjuge', '987.654.321-00', 'joao@example.com', '', '11999998888'),
('2', 'Maria Compradora', '987.654.321-00', 'Nao', 'Sim', 'Nao', 'Nao', '', '', 'maria@example.com', '1134567890', ''),
('3', 'Carlos Fiador', '111.222.333-44', 'Nao', 'Nao', 'Sim', 'Nao', '', '', '', '', ''),
('4', 'Ana Autorizada', '555.666.777-88', 'Nao', 'Nao', 'Nao', 'Sim', '', '', '', '', ''),
('5', 'Multi Tipo', '999.888.777-66', 'Sim', 'Sim', 'Nao', 'Nao', '', '', '', '', '');
"""

_CADIMO = """\
INSERT INTO `CADIMO` (`CODIGO_I`, `CODIGO_C`) VALUES
('I001', '1');
"""

_CADEMP = """\
INSERT INTO `CADEMP` (`CODIGO_D`, `NOME`, `CPF`, `EMAIL`, `CELULAR1`) VALUES
('E01', 'Carlos Agente', '11122233344', 'carlos@agencia.com', '11977776666');
"""

_FILES = {
    "CADCLI.sql": _CADCLI,
    "CADIMO.sql": _CADIMO,
    "CADEMP.sql": _CADEMP,
}


def test_proprietario_ow():
    r = MAPPER.extract_zip(_FILES)
    joao_ow = next(p for p in r.persons if p.codigo == "1" and p.tipo == "OW")
    assert joao_ow.nome == "Joao Proprietario"
    assert joao_ow.cpf == "12345678900"


def test_comprador_bu():
    r = MAPPER.extract_zip(_FILES)
    maria = next(p for p in r.persons if p.codigo == "2" and p.tipo == "BU")
    assert maria.nome == "Maria Compradora"


def test_fiador_gu():
    r = MAPPER.extract_zip(_FILES)
    gu = [p for p in r.persons if p.tipo == "GU"]
    assert len(gu) == 1
    assert gu[0].nome == "Carlos Fiador"


def test_autorizado_oc():
    r = MAPPER.extract_zip(_FILES)
    oc = [p for p in r.persons if p.tipo == "OC"]
    assert len(oc) == 1
    assert oc[0].nome == "Ana Autorizada"


def test_multi_tipo_gera_dois_registros():
    r = MAPPER.extract_zip(_FILES)
    multi = [p for p in r.persons if p.codigo == "5"]
    tipos = {p.tipo for p in multi}
    assert "OW" in tipos
    assert "BU" in tipos


def test_conjuge_nome_e_cpf():
    r = MAPPER.extract_zip(_FILES)
    joao = next(p for p in r.persons if p.codigo == "1" and p.tipo == "OW")
    assert joao.conjuge_nome == "Maria Conjuge"
    assert joao.conjuge_cpf == "98765432100"


def test_funcionario_em():
    r = MAPPER.extract_zip(_FILES)
    em = [p for p in r.persons if p.tipo == "EM"]
    assert len(em) == 1
    assert em[0].nome == "Carlos Agente"


def test_email_cliente():
    r = MAPPER.extract_zip(_FILES)
    emails_1 = [e for e in r.emails if e.codigo_pessoa == "1"]
    assert len(emails_1) == 1
    assert emails_1[0].email == "joao@example.com"


def test_telefone_celular():
    r = MAPPER.extract_zip(_FILES)
    phones_1 = [ph for ph in r.phones if ph.codigo_pessoa == "1"]
    assert len(phones_1) == 1
    assert phones_1[0].ddd == "11"
    assert phones_1[0].tipo_telefone == "M"


def test_telefone_fixo():
    r = MAPPER.extract_zip(_FILES)
    phones_2 = [ph for ph in r.phones if ph.codigo_pessoa == "2"]
    assert len(phones_2) == 1
    assert phones_2[0].tipo_telefone == "R"


def test_sem_sql_retorna_vazio():
    r = MAPPER.extract_zip({})
    assert len(r.persons) == 0


def test_proprietario_via_cadimo():
    # Cliente sem flag PROPRIETARIO mas com imóvel vinculado deve virar OW
    cadcli = """\
INSERT INTO `CADCLI` (`CODIGO_C`, `NOME`, `PROPRIETARIO`, `COMPRADOR`, `FIADOR`, `AUTORIZADO`) VALUES
('99', 'Pessoa Via Cadimo', 'Nao', 'Nao', 'Nao', 'Nao');
"""
    cadimo = """\
INSERT INTO `CADIMO` (`CODIGO_I`, `CODIGO_C`) VALUES
('I99', '99');
"""
    r = MAPPER.extract_zip({"CADCLI.sql": cadcli, "CADIMO.sql": cadimo, "CADEMP.sql": ""})
    p = next(p for p in r.persons if p.codigo == "99")
    assert p.tipo == "OW"
