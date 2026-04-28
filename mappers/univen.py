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


class UnivenMapper(BaseMapper):
    NAME = "Univen"
    EXTENSIONS = [".zip"]
    DESCRIPTION = "Univen (ZIP com XMLs)"

    def can_handle(self, filename: str) -> bool:
        return filename.lower().endswith(".zip")

    def extract_zip(self, files: dict[str, Any]) -> ExtractionResult:
        result = ExtractionResult()
        seen: set[str] = set()

        # Coleta arquivos por prefixo
        clientes_roots: list[ET.Element] = []
        imoveis_roots: list[ET.Element] = []
        usuarios_roots: list[ET.Element] = []

        for name, data in files.items():
            lower = name.lower()
            if not isinstance(data, ET.Element):
                continue
            if "cliente" in lower:
                clientes_roots.append(data)
            elif "imovel" in lower or "imoveis" in lower:
                imoveis_roots.append(data)
            elif "usuario" in lower:
                usuarios_roots.append(data)

        # Clientes com imóvel = OW
        prop_ids: set[str] = set()
        for root in imoveis_roots:
            for im in root.iter("imovel"):
                fk = _txt(im, "fkcodcli")
                if fk:
                    prop_ids.add(fk)

        # Processar clientes
        for root in clientes_roots:
            for cli in root.iter("cliente"):
                cod = _txt(cli, "codcli")
                if not cod:
                    continue
                tipo = "OW" if cod in prop_ids else "BU"
                self._process_cli(cli, cod, tipo, result, seen)

        # Usuários = EM (somente com CPF)
        for root in usuarios_roots:
            for usr in root.iter("usuario"):
                cpf = re.sub(r"\D", "", _txt(usr, "cpf"))
                if not cpf:
                    continue
                cod_raw = _txt(usr, "codigo") or _txt(usr, "codusr")
                codigo = "U" + cod_raw if cod_raw else "U" + cpf
                self._process_cli(usr, codigo, "EM", result, seen)

        return result

    def _process_cli(
        self,
        el: ET.Element,
        codigo: str,
        tipo: str,
        result: ExtractionResult,
        seen: set[str],
    ) -> None:
        key = f"{codigo}|{tipo}"
        if key in seen:
            return
        seen.add(key)

        p = PersonRecord()
        p.codigo = codigo
        p.tipo = tipo
        p.nome = _txt(el, "nome")
        p.cpf = re.sub(r"\D", "", _txt(el, "cpf"))
        p.cnpj = re.sub(r"\D", "", _txt(el, "cnpj"))
        p.rg = _txt(el, "rg")
        p.data_nascimento = _txt(el, "dtnascimento") or _txt(el, "nascimento")
        p.sexo = _txt(el, "sexo")
        p.estado_civil = _txt(el, "estadocivil")
        p.cep = re.sub(r"\D", "", _txt(el, "cep"))
        p.cidade = _txt(el, "cidade")
        p.bairro = _txt(el, "bairro")
        p.estado = _txt(el, "uf") or _txt(el, "estado")
        p.endereco = _txt(el, "endereco") or _txt(el, "logradouro")
        p.numero = _txt(el, "numero")
        p.complemento = _txt(el, "complemento")
        p.observacao = _txt(el, "observacao") or _txt(el, "obs")
        p.profissao = _txt(el, "profissao")
        p.nacionalidade = _txt(el, "nacionalidade")

        result.persons.append(p)

        # Telefones: DDD separado + número, múltiplos por "/"
        self._add_phones(el, codigo, tipo, result)

        email = _txt(el, "email")
        if email:
            result.emails.append(EmailRecord(
                codigo_pessoa=codigo,
                tipo_pessoa=tipo,
                email=email,
                tipo_email="",
            ))

    def _add_phones(self, el: ET.Element, codigo: str, tipo: str, result: ExtractionResult) -> None:
        # telefone1/telefone2: números separados por espaço ou "/"
        for tag in ("telefone1", "telefone2", "celular"):
            raw = _txt(el, tag)
            if not raw:
                continue
            for part in re.split(r"[\s/]+", raw):
                part = re.sub(r"\D", "", part)
                if len(part) < 8:
                    continue
                parsed = processar_telefone(part)
                if parsed:
                    result.phones.append(PhoneRecord(
                        codigo_pessoa=codigo, tipo_pessoa=tipo,
                        ddi=parsed["ddi"], ddd=parsed["ddd"],
                        telefone=parsed["numero"], tipo_telefone=parsed["tipo"],
                    ))
