import xml.etree.ElementTree as ET
import pytest
from mappers.code49 import Code49Mapper

MAPPER = Code49Mapper()

_XML = """\
<root>
  <CIDADES>
    <CIDADE><ID>1</ID><NOME>Sao Paulo</NOME><SIGLA>SP</SIGLA></CIDADE>
    <CIDADE><ID>2</ID><NOME>Campinas</NOME><SIGLA>SP</SIGLA></CIDADE>
  </CIDADES>
  <IMOVEIS>
    <IMOVEL><PROPRIETARIO>100</PROPRIETARIO></IMOVEL>
  </IMOVEIS>
  <CLIENTES>
    <CLIENTE>
      <ID>100</ID><NOME>Joao Proprietario</NOME><CPF>12345678901</CPF><CIDADE>1</CIDADE>
    </CLIENTE>
    <CLIENTE>
      <ID>101</ID><NOME>Maria Compradora</NOME><CPF>98765432100</CPF><CIDADE>2</CIDADE>
    </CLIENTE>
  </CLIENTES>
  <EMAILCLIENTE>
    <EMAIL><IDCLIENTE>100</IDCLIENTE><EMAIL>joao@example.com</EMAIL></EMAIL>
    <EMAIL><IDCLIENTE>101</IDCLIENTE><EMAIL>maria@example.com</EMAIL></EMAIL>
  </EMAILCLIENTE>
  <TELEFONECLIENTE>
    <TELEFONE><IDCLIENTE>100</IDCLIENTE><NUMERO>11999998888</NUMERO></TELEFONE>
  </TELEFONECLIENTE>
</root>
"""


def test_proprietario_tipo_ow():
    root = ET.fromstring(_XML)
    r = MAPPER.extract(root)
    joao = next(p for p in r.persons if p.codigo == "100")
    assert joao.tipo == "OW"
    assert joao.nome == "Joao Proprietario"
    assert joao.cpf == "12345678901"


def test_comprador_tipo_bu():
    root = ET.fromstring(_XML)
    r = MAPPER.extract(root)
    maria = next(p for p in r.persons if p.codigo == "101")
    assert maria.tipo == "BU"


def test_lookup_cidade():
    root = ET.fromstring(_XML)
    r = MAPPER.extract(root)
    joao = next(p for p in r.persons if p.codigo == "100")
    assert joao.cidade == "Sao Paulo"
    assert joao.estado == "SP"
    maria = next(p for p in r.persons if p.codigo == "101")
    assert maria.cidade == "Campinas"


def test_email_capturado():
    root = ET.fromstring(_XML)
    r = MAPPER.extract(root)
    emails_100 = [e for e in r.emails if e.codigo_pessoa == "100"]
    assert len(emails_100) == 1
    assert emails_100[0].email == "joao@example.com"


def test_telefone_capturado():
    root = ET.fromstring(_XML)
    r = MAPPER.extract(root)
    phones_100 = [ph for ph in r.phones if ph.codigo_pessoa == "100"]
    assert len(phones_100) == 1
    assert phones_100[0].ddd == "11"


def test_total_pessoas():
    root = ET.fromstring(_XML)
    r = MAPPER.extract(root)
    assert len(r.persons) == 2


def test_deduplicacao():
    xml_dup = _XML.replace("</CLIENTES>", """
    <CLIENTE>
      <ID>100</ID><NOME>Joao Dup</NOME><CPF>12345678901</CPF><CIDADE>1</CIDADE>
    </CLIENTE>
</CLIENTES>""")
    root = ET.fromstring(xml_dup)
    r = MAPPER.extract(root)
    joaos = [p for p in r.persons if p.codigo == "100"]
    assert len(joaos) == 1
