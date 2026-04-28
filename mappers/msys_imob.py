from __future__ import annotations
import re
from typing import Any

from core.base_mapper import BaseMapper, ExtractionResult, PersonRecord, EmailRecord, PhoneRecord
from core.phone_utils import processar_telefone


def _parse_inserts(sql: str, table: str) -> list[list[str]]:
    """Extrai linhas de INSERT INTO table VALUES (...) com suporte a JSON aninhado."""
    pattern = re.compile(
        rf"INSERT INTO\s+[`'\"]?{re.escape(table)}[`'\"]?\s*(?:\([^)]+\)\s*)?VALUES\s*",
        re.IGNORECASE,
    )
    results: list[list[str]] = []
    for m in pattern.finditer(sql):
        pos = m.end()
        # Extrai todos os grupos de valores
        while pos < len(sql):
            # Pula espaços
            while pos < len(sql) and sql[pos] in (" ", "\t", "\n", "\r"):
                pos += 1
            if pos >= len(sql) or sql[pos] != "(":
                break
            # Extrai grupo balanceado
            depth = 0
            start = pos
            in_str = False
            escape = False
            i = pos
            while i < len(sql):
                c = sql[i]
                if escape:
                    escape = False
                elif c == "\\" and in_str:
                    escape = True
                elif c == "'" and not in_str:
                    in_str = True
                elif c == "'" and in_str:
                    in_str = False
                elif c == "(" and not in_str:
                    depth += 1
                elif c == ")" and not in_str:
                    depth -= 1
                    if depth == 0:
                        i += 1
                        break
                i += 1
            group = sql[start + 1: i - 1]
            results.append(_split_values(group))
            pos = i
            # Pula vírgula entre grupos
            while pos < len(sql) and sql[pos] in (" ", "\t", "\n", "\r", ","):
                if sql[pos] == ";" :
                    break
                pos += 1
            if pos < len(sql) and sql[pos] == ";":
                break
    return results


def _split_values(raw: str) -> list[str]:
    """Divide valores de um grupo INSERT respeitando strings e JSON aninhado."""
    vals: list[str] = []
    current = ""
    in_str = False
    depth = 0
    escape = False
    i = 0
    while i < len(raw):
        c = raw[i]
        if escape:
            current += c
            escape = False
        elif c == "\\" and in_str:
            current += c
            escape = True
        elif c == "'" and not in_str:
            in_str = True
            # não adiciona a aspa ao valor
        elif c == "'" and in_str:
            # aspa dupla = escape
            if i + 1 < len(raw) and raw[i + 1] == "'":
                current += "'"
                i += 2
                continue
            in_str = False
        elif c in ("(", "{", "[") and not in_str:
            depth += 1
            current += c
        elif c in (")", "}", "]") and not in_str:
            depth -= 1
            current += c
        elif c == "," and not in_str and depth == 0:
            vals.append(current.strip() if current.strip().upper() != "NULL" else "")
            current = ""
            i += 1
            continue
        else:
            current += c
        i += 1
    vals.append(current.strip() if current.strip().upper() != "NULL" else "")
    return vals


def _extract_columns(sql: str, table: str) -> list[str]:
    m = re.search(
        rf"INSERT INTO\s+[`'\"]?{re.escape(table)}[`'\"]?\s*\(([^)]+)\)\s*VALUES",
        sql, re.IGNORECASE,
    )
    if m:
        return [c.strip().strip("`'\"") for c in m.group(1).split(",")]
    return []


_ESTADO_CIVIL = {
    "1": "Solteiro", "2": "Casado", "3": "Divorciado", "4": "Viúvo",
    "5": "Separado", "6": "União Estável",
}

_SEXO = {"M": "Masculino", "F": "Feminino"}

_TIPO_MAP = {
    "owner": "OW",
    "occupant": "OC",
    "guarantor": "GU",
    "favored": "FA",
    "buyer": "BU",
}


class MsysImobMapper(BaseMapper):
    NAME = "Msys Imob"
    EXTENSIONS = [".sql", ".zip"]
    DESCRIPTION = "Msys Imob (SQL)"

    def can_handle(self, filename: str) -> bool:
        lower = filename.lower()
        return lower.endswith(".sql") or lower.endswith(".zip")

    def extract(self, data: str) -> ExtractionResult:
        return self._process_sql(data)

    def extract_zip(self, files: dict[str, Any]) -> ExtractionResult:
        for name, data in files.items():
            if name.lower().endswith(".sql") and isinstance(data, str):
                return self._process_sql(data)
        return ExtractionResult()

    def _process_sql(self, sql: str) -> ExtractionResult:
        result = ExtractionResult()

        # Extrai colunas
        person_cols = _extract_columns(sql, "person")
        person_ind_cols = _extract_columns(sql, "person_individual")
        address_cols = _extract_columns(sql, "address")
        contact_cols = _extract_columns(sql, "person_contact")

        # Tabelas de lookup
        marital = self._lookup(sql, "marital_status", "idt_marital_status", "des_marital_status")
        profession = self._lookup(sql, "profession", "idt_profession", "des_profession")
        schooling = self._lookup(sql, "schooling", "idt_schooling", "des_schooling")
        nationality = self._lookup(sql, "nationality", "idt_nationality", "des_nationality")
        issuing = self._lookup(sql, "issuing_institution", "idt_issuing_institution", "des_issuing_institution")

        # Endereços
        addresses: dict[str, dict] = {}
        addr_cols = _extract_columns(sql, "address")
        for row in _parse_inserts(sql, "address"):
            d = dict(zip(addr_cols, row))
            aid = d.get("idt_address", "")
            if aid:
                addresses[aid] = d

        # person_individual
        ind_by_person: dict[str, dict] = {}
        for row in _parse_inserts(sql, "person_individual"):
            d = dict(zip(person_ind_cols, row))
            pid = d.get("idt_person", "")
            if pid:
                ind_by_person[pid] = d

        # Contatos (telefone/email)
        contacts_by_person: dict[str, list[dict]] = {}
        for row in _parse_inserts(sql, "person_contact"):
            d = dict(zip(contact_cols, row))
            pid = d.get("idt_person", "")
            if pid:
                contacts_by_person.setdefault(pid, []).append(d)

        # Índice de persons por ID (para lookup do CPF do cônjuge)
        persons_raw: dict[str, dict] = {}
        for row in _parse_inserts(sql, "person"):
            d = dict(zip(person_cols, row))
            pid = d.get("idt_person", "")
            if pid:
                persons_raw[pid] = d

        # Persons principais
        seen: set[str] = set()
        for row in _parse_inserts(sql, "person"):
            d = dict(zip(person_cols, row))
            pid = d.get("idt_person", "")
            if not pid:
                continue

            tipo_raw = d.get("typ_person", "").lower()
            tipo = _TIPO_MAP.get(tipo_raw, "BU")

            key = f"{pid}|{tipo}"
            if key in seen:
                continue
            seen.add(key)

            ind = ind_by_person.get(pid, {})
            addr = addresses.get(d.get("idt_address", ""), {})

            p = PersonRecord()
            p.codigo = pid
            p.tipo = tipo
            p.nome = ind.get("nam_fantasy") or d.get("nam_person", "")
            p.cpf = re.sub(r"\D", "", d.get("num_document", ""))
            p.rg = ind.get("num_rg", "")
            p.orgao_expedidor = issuing.get(ind.get("idt_issuing_institution", ""), "")
            p.data_nascimento = ind.get("dat_birth", "")
            p.sexo = _SEXO.get(ind.get("flg_sex", ""), "")
            p.estado_civil = marital.get(ind.get("idt_marital_status", ""), "")
            p.nacionalidade = nationality.get(ind.get("idt_nationality", ""), "")
            p.profissao = profession.get(ind.get("idt_profession", ""), "")
            p.escolaridade = schooling.get(ind.get("idt_schooling", ""), "")
            p.cep = re.sub(r"\D", "", addr.get("num_zip_code", ""))
            p.cidade = addr.get("nam_city", "")
            p.bairro = addr.get("nam_neighborhood", "")
            p.estado = addr.get("idt_state", "")
            p.endereco = addr.get("nam_street", "")
            p.numero = addr.get("num_address", "")
            p.complemento = addr.get("des_complement", "")

            # Cônjuge
            spouse_id = ind.get("idt_person_spouse", "")
            if spouse_id:
                sp_ind = ind_by_person.get(spouse_id, {})
                sp_person = persons_raw.get(spouse_id, {})
                p.conjuge_nome = sp_ind.get("nam_fantasy", "")
                p.conjuge_cpf = re.sub(r"\D", "", sp_person.get("num_document", ""))

            result.persons.append(p)

            for c in contacts_by_person.get(pid, []):
                contact_type = c.get("typ_contact", "").lower()
                value = c.get("des_contact", "").strip()
                if not value:
                    continue
                if contact_type in ("phone", "mobile", "cellphone", "fax", "telefone", "celular"):
                    parsed = processar_telefone(value)
                    if parsed:
                        result.phones.append(PhoneRecord(
                            codigo_pessoa=pid, tipo_pessoa=tipo,
                            ddi=parsed["ddi"], ddd=parsed["ddd"],
                            telefone=parsed["numero"], tipo_telefone=parsed["tipo"],
                        ))
                elif contact_type in ("email",):
                    result.emails.append(EmailRecord(
                        codigo_pessoa=pid, tipo_pessoa=tipo,
                        email=value, tipo_email="",
                    ))

        return result

    def _lookup(self, sql: str, table: str, id_col: str, val_col: str) -> dict[str, str]:
        cols = _extract_columns(sql, table)
        result: dict[str, str] = {}
        for row in _parse_inserts(sql, table):
            d = dict(zip(cols, row))
            k = d.get(id_col, "")
            v = d.get(val_col, "")
            if k:
                result[k] = v
        return result
