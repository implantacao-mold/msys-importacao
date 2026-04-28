import pytest
from mappers.imobzi import ImobziMapper

MAPPER = ImobziMapper()

_FILES = {
    "person-0.json": [
        {
            "_id": "P001",
            "code": "C001",
            "fullname": "Joao Silva",
            "cpf": "123.456.789-00",
            "phone.number": ["11987654321"],
            "phone.type": ["mobile"],
            "email": ["joao@example.com"],
        },
        {
            "_id": "P002",
            "code": "C002",
            "fullname": "Maria Santos",
            "cpf": "987.654.321-00",
        },
    ],
    "contactmanager-0.json": [
        {"type": "owner", "person_id": "P001"},
    ],
    "property-0.json": [
        {
            "_id": "PROP001",
            "code": "IM001",
            "status": "available",
            "finality": "residential",
            "property_type": "apartment",
            "sale_value": "500000",
            "rental_value": "2500",
            "city": "Sao Paulo",
            "neighborhood": "Centro",
            "state": "SP",
            "address": "Rua das Flores, 123",
            "zipcode": "01310100",
            "bedroom": "3",
            "bathroom": "2",
            "garage": "1",
            "useful_area": "80",
        },
    ],
    "organization-0.json": [],
    "user.json": [
        {
            "_id": "U001",
            "fullname": "Carlos Agente",
            "cpf": "12345678901",
            "email": "carlos@agencia.com",
            "phones": [{"number": "11977776666"}],
        }
    ],
    "bankdata-0.json": [],
    "propertyfeaturevalue-0.json": [],
    "parameters-0.json": [{}],
}


def test_owner_via_contactmanager():
    r = MAPPER.extract_zip(_FILES)
    joao = next(p for p in r.persons if p.codigo == "P001")
    assert joao.tipo == "OW"


def test_pessoa_sem_contactmanager_eh_bu():
    r = MAPPER.extract_zip(_FILES)
    maria = next(p for p in r.persons if p.codigo == "P002")
    assert maria.tipo == "BU"


def test_usuario_tipo_em():
    r = MAPPER.extract_zip(_FILES)
    em = [p for p in r.persons if p.tipo == "EM"]
    assert len(em) == 1
    assert em[0].nome == "Carlos Agente"


def test_property_result_populado():
    r = MAPPER.extract_zip(_FILES)
    assert r.property_result is not None
    assert len(r.property_result.properties) == 1


def test_property_fields():
    r = MAPPER.extract_zip(_FILES)
    prop = r.property_result.properties[0]
    assert prop.codigo == "IM001"
    assert prop.status == "1"
    assert prop.finalidade == "Residencial"
    assert prop.tipo == "SL"
    assert prop.sub_categoria == "1"
    assert prop.imobiliaria == "1"
    assert prop.cidade == "Sao Paulo"
    assert prop.estado == "SP"
    assert prop.valor_venda == "500000.00"
    assert prop.valor_locacao == "2500.00"


def test_property_numero_extraido_do_endereco():
    r = MAPPER.extract_zip(_FILES)
    prop = r.property_result.properties[0]
    assert prop.rua == "Rua das Flores"
    assert prop.numero_end == "123"


def test_email_pessoa():
    r = MAPPER.extract_zip(_FILES)
    emails_joao = [e for e in r.emails if e.codigo_pessoa == "P001"]
    assert len(emails_joao) == 1
    assert emails_joao[0].email == "joao@example.com"


def test_telefone_pessoa():
    r = MAPPER.extract_zip(_FILES)
    phones_joao = [ph for ph in r.phones if ph.codigo_pessoa == "P001"]
    assert len(phones_joao) == 1
    assert phones_joao[0].ddd == "11"
    assert phones_joao[0].tipo_telefone == "M"


def test_email_usuario():
    r = MAPPER.extract_zip(_FILES)
    emails_em = [e for e in r.emails if e.tipo_pessoa == "EM"]
    assert len(emails_em) == 1
    assert emails_em[0].email == "carlos@agencia.com"


def test_property_sem_dados_retorna_vazio():
    files = {
        "person-0.json": [],
        "organization-0.json": [],
        "property-0.json": [],
        "user.json": [],
        "bankdata-0.json": [],
        "propertyfeaturevalue-0.json": [],
        "parameters-0.json": [{}],
        "contactmanager-0.json": [],
    }
    r = MAPPER.extract_zip(files)
    assert len(r.persons) == 0
    assert r.property_result is not None
    assert len(r.property_result.properties) == 0
