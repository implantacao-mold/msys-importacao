from __future__ import annotations
import re
from typing import Any

from core.base_mapper import BaseMapper, ExtractionResult, PersonRecord, EmailRecord, PhoneRecord
from core.phone_utils import processar_telefone, is_valid_email


def parse_sql(sql: str, table: str) -> list[dict]:
    """Parser para INSERT INTO multi-row do Vista CRM."""
    rows: list[dict] = []
    header_re = re.compile(
        rf"INSERT INTO\s+`?{re.escape(table)}`?\s*\(([^)]+)\)\s*VALUES\s*",
        re.IGNORECASE,
    )
    for hm in header_re.finditer(sql):
        cols = [c.strip().strip("`\"' ") for c in hm.group(1).split(",")]
        pos = hm.end()
        while pos < len(sql):
            # skip whitespace
            while pos < len(sql) and sql[pos] in " \t\n\r":
                pos += 1
            if pos >= len(sql) or sql[pos] != "(":
                break
            pos += 1  # consume '('
            vals: list[str] = []
            current = ""
            while pos < len(sql):
                c = sql[pos]
                if c in ('"', "'"):
                    quote = c
                    pos += 1
                    while pos < len(sql):
                        ch = sql[pos]
                        if ch == quote:
                            if pos + 1 < len(sql) and sql[pos + 1] == quote:
                                current += quote
                                pos += 2
                                continue
                            pos += 1
                            break
                        current += ch
                        pos += 1
                    vals.append(current)
                    current = ""
                elif c == ")":
                    stripped = current.strip()
                    if stripped and stripped.upper() != "NULL":
                        vals.append(stripped)
                    elif stripped.upper() == "NULL":
                        vals.append("")
                    pos += 1
                    break
                elif c == ",":
                    stripped = current.strip()
                    if stripped and stripped.upper() != "NULL":
                        vals.append(stripped)
                    elif stripped.upper() == "NULL":
                        vals.append("")
                    current = ""
                    pos += 1
                else:
                    current += c
                    pos += 1
            if len(vals) == len(cols):
                rows.append(dict(zip(cols, vals)))
            # skip whitespace then expect ',' (more rows) or ';' (end)
            while pos < len(sql) and sql[pos] in " \t\n\r":
                pos += 1
            if pos >= len(sql) or sql[pos] == ";":
                break
            if sql[pos] == ",":
                pos += 1
            else:
                break
    return rows


def _get_sql(files: dict, filename: str) -> str:
    for k, v in files.items():
        if k.lower() == filename.lower() and isinstance(v, str):
            return v
    return ""


class VistaMapper(BaseMapper):
    NAME = "Vista CRM"
    EXTENSIONS = [".zip"]
    DESCRIPTION = "Vista CRM (ZIP com SQL)"

    def can_handle(self, filename: str) -> bool:
        return filename.lower().endswith(".zip")

    def extract_zip(self, files: dict[str, Any]) -> ExtractionResult:
        result = ExtractionResult()
        seen: set[str] = set()

        cadcli_sql = _get_sql(files, "CADCLI.sql")
        cadimo_sql = _get_sql(files, "CADIMO.sql")
        cademp_sql = _get_sql(files, "CADEMP.sql")

        # Proprietários: clientes que têm imóvel vinculado via CODIGO_C
        prop_ids: set[str] = set()
        for im in parse_sql(cadimo_sql, "CADIMO"):
            cid = str(im.get("CODIGO_C") or "").strip()
            if cid and cid != "0":
                prop_ids.add(cid)

        for cli in parse_sql(cadcli_sql, "CADCLI"):
            cli_id = str(cli.get("CODIGO_C") or "").strip()
            if not cli_id:
                continue
            # Determina tipo pelas flags da tabela
            tipos: list[str] = []
            if cli.get("PROPRIETARIO", "").strip() == "Sim" or cli_id in prop_ids:
                tipos.append("OW")
            if cli.get("COMPRADOR", "").strip() == "Sim":
                tipos.append("BU")
            if cli.get("FIADOR", "").strip() == "Sim":
                tipos.append("GU")
            if cli.get("AUTORIZADO", "").strip() == "Sim":
                tipos.append("OC")
            if not tipos:
                tipos = ["BU"]
            for tipo in tipos:
                self._process_cli(cli, cli_id, tipo, result, seen)

        for emp in parse_sql(cademp_sql, "CADEMP"):
            cpf = re.sub(r"\D", "", str(emp.get("CPF") or ""))
            emp_id = str(emp.get("CODIGO_D") or emp.get("ID") or "").strip()
            if not emp_id:
                emp_id = cpf
            if not emp_id:
                continue
            self._process_emp(emp, emp_id, result, seen)

        return result

    def _process_cli(
        self,
        row: dict,
        codigo: str,
        tipo: str,
        result: ExtractionResult,
        seen: set[str],
    ) -> None:
        key = f"{codigo}|{tipo}"
        if key in seen:
            return
        seen.add(key)

        def g(*keys: str) -> str:
            for k in keys:
                v = row.get(k)
                if v and str(v).strip() and str(v).strip().upper() not in ("NULL", "0"):
                    return str(v).strip()
            return ""

        p = PersonRecord()
        p.codigo = codigo
        p.tipo = tipo
        p.nome = g("NOME")
        p.cpf = re.sub(r"\D", "", g("CPF"))
        p.cnpj = re.sub(r"\D", "", g("CNPJ"))
        p.rg = g("RG")
        p.orgao_expedidor = g("RG_EM")
        p.data_nascimento = g("NASCIMENTO")
        p.sexo = g("SEXO")
        p.estado_civil = g("EST_CIVIL")
        p.profissao = g("PROFISSAO")
        p.nacionalidade = g("NACIONAL")
        p.cep = re.sub(r"\D", "", g("CEP_R"))
        p.cidade = g("CIDADE_R")
        p.bairro = g("BAIRRO_R")
        p.estado = g("UF_R")
        p.endereco = g("ENDERECO_R")
        p.numero = g("END_NUMERO_RESID")
        p.observacao = g("OBS")
        p.conjuge_nome = g("NOME_E")
        p.conjuge_cpf = re.sub(r"\D", "", g("CPF_E"))
        result.persons.append(p)

        for field in ("FONE_R", "FONE_PRINCIPAL", "CELULAR", "FAX_R"):
            raw = g(field)
            if not raw:
                continue
            parsed = processar_telefone(raw)
            if parsed:
                result.phones.append(PhoneRecord(
                    codigo_pessoa=codigo, tipo_pessoa=tipo,
                    ddi=parsed["ddi"], ddd=parsed["ddd"],
                    telefone=parsed["numero"], tipo_telefone=parsed["tipo"],
                ))

        email = g("EMAIL_R")
        if is_valid_email(email):
            result.emails.append(EmailRecord(
                codigo_pessoa=codigo, tipo_pessoa=tipo,
                email=email, tipo_email="",
            ))

    def _process_emp(
        self,
        row: dict,
        codigo: str,
        result: ExtractionResult,
        seen: set[str],
    ) -> None:
        key = f"{codigo}|EM"
        if key in seen:
            return
        seen.add(key)

        def g(*keys: str) -> str:
            for k in keys:
                v = row.get(k)
                if v and str(v).strip() and str(v).strip().upper() not in ("NULL", "0"):
                    return str(v).strip()
            return ""

        p = PersonRecord()
        p.codigo = codigo
        p.tipo = "EM"
        p.nome = g("NOME", "NOME_COMPLETO")
        p.cpf = re.sub(r"\D", "", g("CPF"))
        if not p.cpf:
            return
        p.rg = g("RG")
        p.sexo = g("SEXO")
        p.estado_civil = g("EST_CIVIL")
        p.creci = g("CRECI")
        p.cep = re.sub(r"\D", "", g("CEP"))
        p.cidade = g("CIDADE")
        p.bairro = g("BAIRRO")
        p.estado = g("UF")
        p.endereco = g("ENDERECO")
        p.observacao = g("OBS")
        result.persons.append(p)

        for field in ("FONE", "CELULAR", "CELULAR1", "CELULAR2", "FAX"):
            raw = g(field)
            if not raw:
                continue
            parsed = processar_telefone(raw)
            if parsed:
                result.phones.append(PhoneRecord(
                    codigo_pessoa=codigo, tipo_pessoa="EM",
                    ddi=parsed["ddi"], ddd=parsed["ddd"],
                    telefone=parsed["numero"], tipo_telefone=parsed["tipo"],
                ))

        email = g("EMAIL")
        if is_valid_email(email):
            result.emails.append(EmailRecord(
                codigo_pessoa=codigo, tipo_pessoa="EM",
                email=email, tipo_email="",
            ))
