import hashlib
import xml.etree.ElementTree as ET

import pytest
from mappers.arbo import ArboMapper

MAPPER = ArboMapper()


def _md5(s: str) -> str:
    return hashlib.md5(s.encode("utf-8")).hexdigest()[:16].upper()


def _build_xml(proprietarios: list[dict]) -> ET.Element:
    root = ET.Element("root")
    for prop in proprietarios:
        imovel = ET.SubElement(root, "Imovel")
        node = ET.SubElement(imovel, "Proprietario")
        for tag, val in prop.items():
            el = ET.SubElement(node, tag)
            el.text = val
    return root


def test_proprietario_extraido():
    root = _build_xml([{"Nome": "Joao Silva", "CPF": "123.456.789-00",
                        "Telefone": "(11) 99999-8888", "Email": "joao@example.com"}])
    r = MAPPER.extract(root)
    assert len(r.persons) == 1
    assert r.persons[0].tipo == "OW"
    assert r.persons[0].nome == "Joao Silva"
    assert r.persons[0].cpf == "12345678900"


def test_email_capturado():
    root = _build_xml([{"Nome": "Joao", "Email": "joao@example.com"}])
    r = MAPPER.extract(root)
    assert len(r.emails) == 1
    assert r.emails[0].email == "joao@example.com"
    assert r.emails[0].tipo_pessoa == "OW"


def test_email_temp_filtrado():
    root = _build_xml([{"Nome": "Joao", "Email": "joao@temp-email.com.br"}])
    r = MAPPER.extract(root)
    assert len(r.emails) == 0


def test_telefone_capturado():
    root = _build_xml([{"Nome": "Joao", "Telefone": "11999998888"}])
    r = MAPPER.extract(root)
    assert len(r.phones) == 1
    assert r.phones[0].ddd == "11"
    assert r.phones[0].tipo_telefone == "M"


def test_codigo_md5_baseado_em_nome_e_telefone():
    root = _build_xml([{"Nome": "Joao Silva", "Telefone": "11999998888"}])
    r = MAPPER.extract(root)
    expected_codigo = _md5("JOAO SILVA" + "11999998888")
    assert r.persons[0].codigo == expected_codigo


def test_sem_nome_ignorado():
    root = _build_xml([{"CPF": "12345678900", "Email": "sem@nome.com"}])
    r = MAPPER.extract(root)
    assert len(r.persons) == 0


def test_sem_proprietario_ignorado():
    root = ET.Element("root")
    ET.SubElement(ET.SubElement(root, "Imovel"), "OutroNodo")
    r = MAPPER.extract(root)
    assert len(r.persons) == 0


def test_deduplicacao_mesmo_proprietario_em_multiplos_imoveis():
    root = ET.Element("root")
    for _ in range(3):
        imovel = ET.SubElement(root, "Imovel")
        node = ET.SubElement(imovel, "Proprietario")
        ET.SubElement(node, "Nome").text = "Joao Silva"
        ET.SubElement(node, "Telefone").text = "11999998888"
    r = MAPPER.extract(root)
    assert len(r.persons) == 1


def test_multiplos_proprietarios_distintos():
    root = _build_xml([
        {"Nome": "Joao Silva", "Telefone": "11999998888"},
        {"Nome": "Maria Santos", "Telefone": "11888887777"},
    ])
    r = MAPPER.extract(root)
    assert len(r.persons) == 2
