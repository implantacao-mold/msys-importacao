import xml.etree.ElementTree as ET
import pytest
from mappers.imobi_brasil import ImobiBrasilMapper

MAPPER = ImobiBrasilMapper()

_XML = """\
<root>
  <imovel>
    <ref>42</ref>
    <transacao>Venda</transacao>
    <subtipoimovel>Apartamento</subtipoimovel>
    <valor>350000.00</valor>
    <imovel_status>ATIVO</imovel_status>
    <data_cadastro>2023-05-15</data_cadastro>
    <destacado>SIM</destacado>
    <dormitorios>3</dormitorios>
    <banheiro>2</banheiro>
    <suites>1</suites>
    <vagas>1</vagas>
    <area_construida>85,50</area_construida>
    <area_total>90,00</area_total>
    <valor_iptu>1200.00</valor_iptu>
    <titulo>Apto 3 quartos Centro</titulo>
    <ano_construcao>2010</ano_construcao>
    <video>https://yt.com/abc</video>
    <aceitafinanciamento>SIM</aceitafinanciamento>
    <endereco_cep>01310100</endereco_cep>
    <endereco_cidade>Sao Paulo</endereco_cidade>
    <endereco_estado>SP</endereco_estado>
    <endereco_bairro>Centro</endereco_bairro>
    <endereco_logradouro>Rua das Flores</endereco_logradouro>
    <endereco_numero>123</endereco_numero>
    <endereco_complemento>Apto 1</endereco_complemento>
    <empreendimento_nome>Residencial das Flores</empreendimento_nome>
    <endereco_pontoreferencia>Proximo ao metro</endereco_pontoreferencia>
    <valor_condominio>800.00</valor_condominio>
    <caracteristicas>
      <item>AR CONDICIONADO</item>
      <item>ÁREA DE SERVIÇO</item>
    </caracteristicas>
    <proprietario>
      <nome>Joao Silva</nome>
      <cpf>12345678901</cpf>
      <telefone1>(11) 99999-8888</telefone1>
      <email>joao@example.com</email>
    </proprietario>
    <corretor>
      <nome>Carlos Corretor</nome>
      <cpf>11122233344</cpf>
      <telefone1>(11) 88888-7777</telefone1>
      <email>carlos@imob.com</email>
    </corretor>
  </imovel>
</root>
"""


def test_proprietario_tipo_ow():
    root = ET.fromstring(_XML)
    r = MAPPER.extract(root)
    ow = [p for p in r.persons if p.tipo == "OW"]
    assert len(ow) == 1
    assert ow[0].nome == "Joao Silva"
    assert ow[0].cpf == "12345678901"


def test_corretor_tipo_em():
    root = ET.fromstring(_XML)
    r = MAPPER.extract(root)
    em = [p for p in r.persons if p.tipo == "EM"]
    assert len(em) == 1
    assert em[0].nome == "Carlos Corretor"


def test_total_pessoas():
    root = ET.fromstring(_XML)
    r = MAPPER.extract(root)
    assert len(r.persons) == 2


def test_emails_capturados():
    root = ET.fromstring(_XML)
    r = MAPPER.extract(root)
    assert len(r.emails) == 2
    emails = {e.tipo_pessoa: e.email for e in r.emails}
    assert emails["OW"] == "joao@example.com"
    assert emails["EM"] == "carlos@imob.com"


def test_telefone_capturado():
    root = ET.fromstring(_XML)
    r = MAPPER.extract(root)
    phones_ow = [ph for ph in r.phones if ph.tipo_pessoa == "OW"]
    assert len(phones_ow) == 1
    assert phones_ow[0].ddd == "11"


def test_endereco_pessoa_em_branco():
    root = ET.fromstring(_XML)
    r = MAPPER.extract(root)
    joao = next(p for p in r.persons if p.tipo == "OW")
    assert joao.cidade == ""
    assert joao.estado == ""
    assert joao.cep == ""


def test_property_result_populado():
    root = ET.fromstring(_XML)
    r = MAPPER.extract(root)
    assert r.property_result is not None
    assert len(r.property_result.properties) == 1


def test_property_codigo_e_tipo():
    root = ET.fromstring(_XML)
    r = MAPPER.extract(root)
    prop = r.property_result.properties[0]
    assert prop.codigo == "42"
    assert prop.tipo == "S"
    assert prop.status == "1"
    assert prop.imobiliaria == "1"


def test_property_subcategoria():
    root = ET.fromstring(_XML)
    r = MAPPER.extract(root)
    prop = r.property_result.properties[0]
    assert prop.sub_categoria == "1"


def test_property_valor_venda():
    root = ET.fromstring(_XML)
    r = MAPPER.extract(root)
    prop = r.property_result.properties[0]
    assert prop.valor_venda == "350000.00"
    assert prop.valor_locacao == ""


def test_property_valor_locacao():
    root = ET.Element("root")
    imovel = ET.SubElement(root, "imovel")
    ET.SubElement(imovel, "ref").text = "10"
    ET.SubElement(imovel, "transacao").text = "Locação"
    ET.SubElement(imovel, "valor").text = "2500"
    r = MAPPER.extract(root)
    prop = r.property_result.properties[0]
    assert prop.tipo == "L"
    assert prop.valor_locacao == "2500.00"
    assert prop.valor_venda == ""


def test_property_endereco():
    root = ET.fromstring(_XML)
    r = MAPPER.extract(root)
    prop = r.property_result.properties[0]
    assert prop.cep == "01310100"
    assert prop.cidade == "Sao Paulo"
    assert prop.bairro == "Centro"
    assert prop.estado == "SP"
    assert prop.rua == "Rua das Flores"
    assert prop.numero_end == "123"


def test_property_complemento_com_empreendimento():
    root = ET.fromstring(_XML)
    r = MAPPER.extract(root)
    prop = r.property_result.properties[0]
    assert "Apto 1" in prop.complemento
    assert "Residencial das Flores" in prop.complemento


def test_property_areas():
    root = ET.fromstring(_XML)
    r = MAPPER.extract(root)
    prop = r.property_result.properties[0]
    assert prop.area_util == "85.50"
    assert prop.area_total == "90.00"
    assert prop.area_construida == "85.50"


def test_property_dormitorios_e_garagem():
    root = ET.fromstring(_XML)
    r = MAPPER.extract(root)
    prop = r.property_result.properties[0]
    assert prop.dormitorios == "3"
    assert prop.banheiros == "2"
    assert prop.suites == "1"
    assert prop.garagem == "1"


def test_property_destaque():
    root = ET.fromstring(_XML)
    r = MAPPER.extract(root)
    prop = r.property_result.properties[0]
    assert prop.destaque == "1"
    assert prop.mostrar_site == "1"
    assert prop.street_view == "1"


def test_property_caracteristicas_sim_nao():
    root = ET.fromstring(_XML)
    r = MAPPER.extract(root)
    prop = r.property_result.properties[0]
    assert "Ar-condicionado" in prop.caracteristicas_sim_nao
    assert "Área de serviço" in prop.caracteristicas_sim_nao
    assert "Aceita financiamento" in prop.caracteristicas_sim_nao


def test_property_iptu():
    root = ET.fromstring(_XML)
    r = MAPPER.extract(root)
    assert len(r.property_result.iptu) == 1
    iptu = r.property_result.iptu[0]
    assert iptu.codigo_imovel == "42"
    assert iptu.tipo_iptu == "IPTU Principal"
    assert iptu.inscricao_iptu == ""
    assert iptu.valor_anual_iptu == "1200.00"
    assert iptu.valor_mensal_iptu == "1200.00"
    assert iptu.perc_iptu == "100"


def test_property_owner():
    root = ET.fromstring(_XML)
    r = MAPPER.extract(root)
    assert len(r.property_result.owners) == 1
    owner = r.property_result.owners[0]
    assert owner.codigo_imovel == "42"
    assert owner.cpf == ""
    assert owner.percentual == "100"
    assert owner.codigo_pessoa != ""


def test_property_owner_favored():
    root = ET.fromstring(_XML)
    r = MAPPER.extract(root)
    assert len(r.property_result.owners_favored) == 1
    fav = r.property_result.owners_favored[0]
    assert fav.codigo_imovel == "42"
    assert fav.tipo_pagamento == "M"
    assert fav.percentual == "100"
    assert fav.favorecido == "Joao Silva"
    assert fav.id_favorecido == fav.codigo_pessoa


def test_property_captivator():
    root = ET.fromstring(_XML)
    r = MAPPER.extract(root)
    assert len(r.property_result.captivators) == 1
    cap = r.property_result.captivators[0]
    assert cap.codigo_imovel == "42"
    assert cap.departamento == "S"
    assert cap.data_captacao != ""


def test_property_ref_sem_imovel_ignorado():
    root = ET.Element("root")
    ET.SubElement(root, "imovel")  # sem <ref>
    r = MAPPER.extract(root)
    assert len(r.property_result.properties) == 0


def test_deduplicacao_mesmo_proprietario_em_multiplos_imoveis():
    root = ET.Element("root")
    for i in range(1, 3):
        imovel = ET.SubElement(root, "imovel")
        ET.SubElement(imovel, "ref").text = str(i)
        ET.SubElement(imovel, "transacao").text = "Venda"
        prop = ET.SubElement(imovel, "proprietario")
        ET.SubElement(prop, "nome").text = "Joao Silva"
        ET.SubElement(prop, "telefone1").text = "(11) 99999-8888"
    r = MAPPER.extract(root)
    ow = [p for p in r.persons if p.tipo == "OW"]
    assert len(ow) == 1
    assert len(r.property_result.properties) == 2
    assert len(r.property_result.owners) == 2


def test_sem_proprietario_sem_pessoa():
    root = ET.Element("root")
    imovel = ET.SubElement(root, "imovel")
    ET.SubElement(imovel, "endereco_cidade").text = "Sao Paulo"
    r = MAPPER.extract(root)
    assert len(r.persons) == 0
