from __future__ import annotations
import csv
import dataclasses
import html
import os
import re
import unicodedata

from core.bank_codes import bank_name_to_code
from core.property_records import PropertyExtractionResult
from core.property_schema import (
    PROPERTY_COLUMNS,
    PROPERTY_OWNER_COLUMNS,
    PROPERTY_OWNER_FAVORED_COLUMNS,
    PROPERTY_CAPTIVATOR_COLUMNS,
    PROPERTY_IPTU_COLUMNS,
)
from core.cep_lookup import fix_record_cep
from core.schema import ENCODING, SEPARATOR


def _q(v: str) -> str:
    """Prefix document fields with single-quote so importers treat them as text (preserves leading zeros)."""
    s = str(v) if v else ""
    return f"'{s}" if s else ""


def _sanitize(value: str) -> str:
    text = str(value) if value is not None else ""
    # Decode XML/HTML numeric and named entity references (&#xA; &#10; &amp; etc.)
    text = html.unescape(text)
    # Remove any residual XML character references that html.unescape may have missed
    text = re.sub(r"&#x[0-9A-Fa-f]+;|&#\d+;", " ", text)
    text = unicodedata.normalize("NFC", text)
    return text.replace("\r\n", " ").replace("\n", " ").replace("\r", " ").replace("\t", " ")


def _write_csv(path: str, columns: list[str], rows: list[list[str]]) -> None:
    with open(path, "w", newline="", encoding=ENCODING, errors="replace") as f:
        writer = csv.writer(f, delimiter=SEPARATOR)
        writer.writerow(columns)
        for row in rows:
            writer.writerow([_sanitize(v) for v in row])


def _code_key(code: str):
    try:
        return (0, int(code), "")
    except (ValueError, TypeError):
        return (1, 0, str(code or ""))


def export_properties(result: PropertyExtractionResult, output_dir: str) -> None:
    prop_dir = os.path.join(output_dir, "PROPERTY")
    os.makedirs(prop_dir, exist_ok=True)

    # Normaliza CEP de todos os imóveis (válido para todos os mappers)
    for pr in result.properties:
        fix_record_cep(pr)

    # Imóvel SL → expande captivadores em 2 registros (um "S" e um "L")
    # Captivadores que já estejam com departamento "S" ou "L" são mantidos como estão.
    _tipo_imovel = {pr.codigo: pr.tipo for pr in result.properties}
    expanded_captivators: list = []
    for c in result.captivators:
        if _tipo_imovel.get(c.codigo_imovel) == "SL" and c.departamento not in ("S", "L"):
            expanded_captivators.append(dataclasses.replace(c, departamento="S"))
            expanded_captivators.append(dataclasses.replace(c, departamento="L"))
        else:
            expanded_captivators.append(c)
    result.captivators = expanded_captivators

    # data_captacao sempre igual a data_registro do imóvel correspondente
    _data_registro = {pr.codigo: pr.data_registro for pr in result.properties}
    for c in result.captivators:
        c.data_captacao = _data_registro.get(c.codigo_imovel, "")

    properties      = sorted(result.properties,    key=lambda p: _code_key(p.codigo))
    owners          = sorted(result.owners,         key=lambda o: _code_key(o.codigo_imovel))
    owners_favored  = sorted(result.owners_favored, key=lambda f: _code_key(f.codigo_imovel))
    captivators     = sorted(result.captivators,    key=lambda c: _code_key(c.codigo_imovel))
    iptu            = sorted(result.iptu,           key=lambda i: _code_key(i.codigo_imovel))

    _write_csv(
        os.path.join(prop_dir, "PROPERTY.csv"),
        PROPERTY_COLUMNS,
        [p.to_row() for p in properties],
    )

    _write_csv(
        os.path.join(prop_dir, "PROPERTY_OWNER.csv"),
        PROPERTY_OWNER_COLUMNS,
        [
            [_q(o.codigo_imovel), _q(o.cpf or o.cnpj), o.codigo_pessoa, o.percentual]
            for o in owners
        ],
    )

    _write_csv(
        os.path.join(prop_dir, "PROPERTY_OWNER_FAVORED.csv"),
        PROPERTY_OWNER_FAVORED_COLUMNS,
        [
            [
                _q(f.codigo_imovel),
                _q(f.cpf or f.cnpj),
                f.codigo_pessoa,
                "A" if (f.banco or f.agencia or f.conta) else f.tipo_pagamento,
                f.percentual,
                _q(f.cpf_favorecido or f.cnpj_favorecido),
                f.id_favorecido,
                f.favorecido,
                bank_name_to_code(f.banco),
                f.agencia,
                f.digito_agencia,
                f.conta,
                f.digito_conta,
                f.poupanca,
            ]
            for f in owners_favored
        ],
    )

    _write_csv(
        os.path.join(prop_dir, "PROPERTY_CAPTIVATOR.csv"),
        PROPERTY_CAPTIVATOR_COLUMNS,
        [
            [_q(c.codigo_imovel), _q(c.cpf_cnpj), c.departamento, c.data_captacao]
            for c in captivators
        ],
    )

    _write_csv(
        os.path.join(prop_dir, "PROPERTY_IPTU.csv"),
        PROPERTY_IPTU_COLUMNS,
        [
            [
                _q(i.codigo_imovel),
                i.tipo_iptu,
                i.inscricao_iptu,
                i.valor_mensal_iptu,
                i.valor_anual_iptu,
                i.parcelas_iptu,
                i.perc_iptu,
                i.obs_iptu,
            ]
            for i in iptu
        ],
    )
