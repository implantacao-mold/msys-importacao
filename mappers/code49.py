from __future__ import annotations
import re
import xml.etree.ElementTree as ET
from typing import Any

from core.base_mapper import BaseMapper, ExtractionResult, PersonRecord, EmailRecord, PhoneRecord
from core.phone_utils import processar_telefone


def _txt(el: ET.Element | None, tag: str) -> str:
    if el is None:
        return ""
    found = el.find(tag)
    return (found.text or "").strip() if found is not None else ""


class Code49Mapper(BaseMapper):
    NAME = "Code49"
    EXTENSIONS = [".xml"]
    DESCRIPTION = "Code49 (XML)"

    def can_handle(self, filename: str) -> bool:
        return filename.lower().endswith(".xml")

    def extract(self, root: ET.Element) -> ExtractionResult:
        result = ExtractionResult()

        # Monta lookup de cidades: id → (nome, uf)
        cidades: dict[str, tuple[str, str]] = {}
        for c in root.findall(".//CIDADES/CIDADE") or root.findall(".//CIDADE"):
            cid = _txt(c, "ID") or _txt(c, "CODIGO")
            nome = _txt(c, "CIDADE") or _txt(c, "NOME")
            uf = _txt(c, "SIGLA") or _txt(c, "UF")
            if cid:
                cidades[cid] = (nome, uf)

        # Proprietários: clientes com imóvel via INNER JOIN
        imoveis_prop: set[str] = set()
        for im in root.findall(".//IMOVEIS/IMOVEL") or root.findall(".//IMOVEL"):
            prop_id = _txt(im, "PROPRIETARIO")
            if prop_id:
                imoveis_prop.add(prop_id)

        # Emails por cliente
        emails_by_cli: dict[str, list[str]] = {}
        for em in root.findall(".//EMAILCLIENTE/EMAIL") or root.findall(".//EMAILCLIENTE"):
            cli_id = _txt(em, "IDCLIENTE") or _txt(em, "CLIENTE")
            email = _txt(em, "EMAIL") or _txt(em, "ENDERECO")
            if cli_id and email:
                emails_by_cli.setdefault(cli_id, []).append(email)

        # Telefones por cliente
        fones_by_cli: dict[str, list[str]] = {}
        for tel in root.findall(".//TELEFONECLIENTE/TELEFONE") or root.findall(".//TELEFONECLIENTE"):
            cli_id = _txt(tel, "IDCLIENTE") or _txt(tel, "CLIENTE")
            numero = _txt(tel, "NUMERO") or _txt(tel, "TELEFONE")
            if cli_id and numero:
                fones_by_cli.setdefault(cli_id, []).append(numero)

        seen: set[str] = set()
        clientes = root.findall(".//CLIENTES/CLIENTE") or root.findall(".//CLIENTE")
        for cli in clientes:
            cli_id = _txt(cli, "ID")
            if not cli_id:
                continue
            tipo = "OW" if cli_id in imoveis_prop else "BU"
            key = f"{cli_id}|{tipo}"
            if key in seen:
                continue
            seen.add(key)

            cidade_id = _txt(cli, "CIDADE")
            cidade_nome, cidade_uf = cidades.get(cidade_id, ("", ""))

            p = PersonRecord()
            p.codigo = cli_id
            p.tipo = tipo
            p.nome = _txt(cli, "NOME")
            p.cpf = re.sub(r"\D", "", _txt(cli, "CPF"))
            p.cnpj = re.sub(r"\D", "", _txt(cli, "CNPJ"))
            p.rg = _txt(cli, "RG")
            p.data_nascimento = _txt(cli, "DATANASCIMENTO") or _txt(cli, "NASCIMENTO")
            p.cep = re.sub(r"\D", "", _txt(cli, "CEP"))
            p.cidade = cidade_nome or _txt(cli, "NOMECIDADE")
            p.estado = cidade_uf or _txt(cli, "UF")
            p.bairro = _txt(cli, "BAIRRO")
            p.endereco = _txt(cli, "ENDERECO") or _txt(cli, "LOGRADOURO")
            p.numero = _txt(cli, "NUMERO")
            p.complemento = _txt(cli, "COMPLEMENTO")
            p.observacao = _txt(cli, "OBSERVACAO") or _txt(cli, "OBS")

            result.persons.append(p)

            for raw in fones_by_cli.get(cli_id, []):
                parsed = processar_telefone(raw)
                if parsed:
                    result.phones.append(PhoneRecord(
                        codigo_pessoa=cli_id,
                        tipo_pessoa=tipo,
                        ddi=parsed["ddi"],
                        ddd=parsed["ddd"],
                        telefone=parsed["numero"],
                        tipo_telefone=parsed["tipo"],
                    ))

            for email in emails_by_cli.get(cli_id, []):
                result.emails.append(EmailRecord(
                    codigo_pessoa=cli_id,
                    tipo_pessoa=tipo,
                    email=email,
                    tipo_email="",
                ))

        return result
