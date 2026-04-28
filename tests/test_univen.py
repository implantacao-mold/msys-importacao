import xml.etree.ElementTree as ET
import pytest
from mappers.univen import UnivenMapper

MAPPER = UnivenMapper()


def _make_files(clientes_xml: str, imoveis_xml: str = "", usuarios_xml: str = "") -> dict:
    files = {}
    if clientes_xml:
        files["cliente.xml"] = ET.fromstring(clientes_xml)
    if imoveis_xml:
        files["imovel.xml"] = ET.fromstring(imoveis_xml)
    if usuarios_xml:
        files["usuario.xml"] = ET.fromstring(usuarios_xml)
    return files


_CLIENTES_XML = """\
<clientes>
  <cliente>
    <codcli>1</codcli><nome>Joao Proprietario</nome><cpf>12345678901</cpf>
    <email>joao@example.com</email><telefone1>11999998888</telefone1>
    <cep>01310100</cep><cidade>Sao Paulo</cidade><bairro>Centro</bairro>
    <uf>SP</uf>
  </cliente>
  <cliente>
    <codcli>2</codcli><nome>Maria Compradora</nome><cpf>98765432100</cpf>
    <telefone1>11988887777</telefone1>
  </cliente>
</clientes>
"""

_IMOVEIS_XML = """\
<imoveis>
  <imovel><fkcodcli>1</fkcodcli></imovel>
</imoveis>
"""

_USUARIOS_XML = """\
<usuarios>
  <usuario>
    <codigo>U01</codigo><nome>Carlos Agente</nome>
    <cpf>11122233344</cpf><email>carlos@agencia.com</email>
  </usuario>
  <usuario>
    <codigo>U02</codigo><nome>Sem CPF</nome>
  </usuario>
</usuarios>
"""


def test_proprietario_ow():
    r = MAPPER.extract_zip(_make_files(_CLIENTES_XML, _IMOVEIS_XML))
    joao = next(p for p in r.persons if p.codigo == "1")
    assert joao.tipo == "OW"
    assert joao.nome == "Joao Proprietario"
    assert joao.cpf == "12345678901"


def test_comprador_bu():
    r = MAPPER.extract_zip(_make_files(_CLIENTES_XML, _IMOVEIS_XML))
    maria = next(p for p in r.persons if p.codigo == "2")
    assert maria.tipo == "BU"


def test_usuario_em_com_cpf():
    r = MAPPER.extract_zip(_make_files(_CLIENTES_XML, _IMOVEIS_XML, _USUARIOS_XML))
    em = [p for p in r.persons if p.tipo == "EM"]
    assert len(em) == 1
    assert em[0].nome == "Carlos Agente"


def test_usuario_sem_cpf_ignorado():
    r = MAPPER.extract_zip(_make_files(_CLIENTES_XML, _IMOVEIS_XML, _USUARIOS_XML))
    nomes = {p.nome for p in r.persons}
    assert "Sem CPF" not in nomes


def test_email_capturado():
    r = MAPPER.extract_zip(_make_files(_CLIENTES_XML, _IMOVEIS_XML))
    emails_joao = [e for e in r.emails if e.codigo_pessoa == "1"]
    assert len(emails_joao) == 1
    assert emails_joao[0].email == "joao@example.com"


def test_telefone_capturado():
    r = MAPPER.extract_zip(_make_files(_CLIENTES_XML, _IMOVEIS_XML))
    phones_joao = [ph for ph in r.phones if ph.codigo_pessoa == "1"]
    assert len(phones_joao) == 1
    assert phones_joao[0].ddd == "11"


def test_endereco_extraido():
    r = MAPPER.extract_zip(_make_files(_CLIENTES_XML, _IMOVEIS_XML))
    joao = next(p for p in r.persons if p.codigo == "1")
    assert joao.cidade == "Sao Paulo"
    assert joao.cep == "01310100"
    assert joao.estado == "SP"


def test_sem_imoveis_todos_bu():
    r = MAPPER.extract_zip(_make_files(_CLIENTES_XML))
    tipos = {p.tipo for p in r.persons}
    assert tipos == {"BU"}


def test_arquivo_desconhecido_ignorado():
    files = {"outro.txt": "conteudo", "cliente.xml": ET.fromstring(_CLIENTES_XML)}
    r = MAPPER.extract_zip(files)
    assert len(r.persons) == 2
