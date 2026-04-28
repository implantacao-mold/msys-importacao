import csv
import os
import unicodedata
import pytest
from core.base_mapper import ExtractionResult, PersonRecord, EmailRecord, PhoneRecord
from core.exporter import export
from core.schema import ENCODING, SEPARATOR, PERSON_COLUMNS, EMAIL_COLUMNS, PHONE_COLUMNS


def _read_csv(path: str) -> list[list[str]]:
    with open(path, encoding=ENCODING) as f:
        return list(csv.reader(f, delimiter=SEPARATOR))


def test_encoding_cp1252(tmp_path):
    result = ExtractionResult()
    p = PersonRecord()
    p.codigo = "001"
    p.tipo = "BU"
    p.nome = "José Coração"
    result.persons.append(p)

    export(result, str(tmp_path))

    path = tmp_path / "PERSON" / "PERSON.csv"
    raw = path.read_bytes()
    # "José" em cp1252: J=0x4A, o=0x6F, s=0x73, é=0xE9
    assert b"\xe9" in raw  # é em cp1252


def test_separador_ponto_virgula(tmp_path):
    result = ExtractionResult()
    p = PersonRecord()
    p.codigo = "001"
    p.tipo = "BU"
    p.nome = "Teste"
    result.persons.append(p)

    export(result, str(tmp_path))

    path = tmp_path / "PERSON" / "PERSON.csv"
    first_line = path.read_bytes().split(b"\r\n")[0]
    assert b";" in first_line


def test_nfc_normalizacao(tmp_path):
    result = ExtractionResult()
    p = PersonRecord()
    p.codigo = "001"
    p.tipo = "BU"
    # Cria string em forma NFD (e + combining acute)
    p.nome = unicodedata.normalize("NFD", "José")
    result.persons.append(p)

    export(result, str(tmp_path))

    path = tmp_path / "PERSON" / "PERSON.csv"
    rows = _read_csv(str(path))
    nome_col = PERSON_COLUMNS.index("Nome")
    assert rows[1][nome_col] == "José"


def test_person_csv_57_colunas(tmp_path):
    result = ExtractionResult()
    export(result, str(tmp_path))
    rows = _read_csv(str(tmp_path / "PERSON" / "PERSON.csv"))
    assert len(rows[0]) == 57


def test_person_csv_cabecalho(tmp_path):
    result = ExtractionResult()
    export(result, str(tmp_path))

    rows = _read_csv(str(tmp_path / "PERSON" / "PERSON.csv"))
    assert rows[0] == PERSON_COLUMNS


def test_email_csv_cabecalho(tmp_path):
    result = ExtractionResult()
    export(result, str(tmp_path))

    rows = _read_csv(str(tmp_path / "PERSON" / "EMAIL.csv"))
    assert rows[0] == EMAIL_COLUMNS


def test_phone_csv_cabecalho(tmp_path):
    result = ExtractionResult()
    export(result, str(tmp_path))

    rows = _read_csv(str(tmp_path / "PERSON" / "PHONE.csv"))
    assert rows[0] == PHONE_COLUMNS


def test_person_csv_linha_de_dados(tmp_path):
    result = ExtractionResult()
    p = PersonRecord()
    p.codigo = "X001"
    p.tipo = "OW"
    p.nome = "Joao Silva"
    p.cpf = "12345678901"
    p.cidade = "Sao Paulo"
    result.persons.append(p)

    export(result, str(tmp_path))

    rows = _read_csv(str(tmp_path / "PERSON" / "PERSON.csv"))
    assert len(rows) == 2  # header + 1 data row
    assert rows[1][PERSON_COLUMNS.index("Código")] == "X001"
    assert rows[1][PERSON_COLUMNS.index("Tipo")] == "OW"
    assert rows[1][PERSON_COLUMNS.index("Nome")] == "Joao Silva"
    assert rows[1][PERSON_COLUMNS.index("CPF/CNPJ")] == "'12345678901"
    assert rows[1][PERSON_COLUMNS.index("Cidade")] == "Sao Paulo"


def test_email_csv_linha_de_dados(tmp_path):
    result = ExtractionResult()
    result.emails.append(EmailRecord(
        codigo_pessoa="X001", tipo_pessoa="OW",
        email="joao@example.com", tipo_email="",
    ))

    export(result, str(tmp_path))

    rows = _read_csv(str(tmp_path / "PERSON" / "EMAIL.csv"))
    assert len(rows) == 2
    assert rows[1][0] == "X001"
    assert rows[1][1] == "joao@example.com"


def test_phone_csv_linha_de_dados(tmp_path):
    result = ExtractionResult()
    result.phones.append(PhoneRecord(
        codigo_pessoa="X001", tipo_pessoa="OW",
        ddi="55", ddd="11", telefone="999998888", tipo_telefone="M",
    ))

    export(result, str(tmp_path))

    rows = _read_csv(str(tmp_path / "PERSON" / "PHONE.csv"))
    assert len(rows) == 2
    assert rows[1][0] == "X001"
    assert rows[1][1] == "11"
    assert rows[1][2] == "999998888"
    assert rows[1][3] == "M"


def test_quebra_linha_substituida_por_espaco(tmp_path):
    result = ExtractionResult()
    p = PersonRecord()
    p.codigo = "X001"
    p.tipo = "BU"
    p.observacao = "Linha 1\nLinha 2"
    result.persons.append(p)

    export(result, str(tmp_path))

    rows = _read_csv(str(tmp_path / "PERSON" / "PERSON.csv"))
    obs = rows[1][PERSON_COLUMNS.index("Observação")]
    assert "\n" not in obs
    assert "Linha 1" in obs


def test_pessoa_dir_criado(tmp_path):
    result = ExtractionResult()
    export(result, str(tmp_path))
    assert (tmp_path / "PERSON").is_dir()
