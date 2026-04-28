from __future__ import annotations
import re
from typing import Any

from core.base_mapper import BaseMapper, ExtractionResult, PersonRecord, EmailRecord, PhoneRecord
from core.phone_utils import processar_telefone


def _v(row: dict, *keys: str) -> str:
    for k in keys:
        v = row.get(k)
        if v is not None:
            s = str(v).strip()
            if s and s.lower() not in ("none", "nan"):
                return s
    return ""


def _parse_phones(telefones_text: str) -> list[str]:
    """Extrai números de texto como 'Tel. Residencial: (16) 3987-1482 Celular: (16) 9937-41792'."""
    results = []
    for m in re.finditer(r"\((\d{2})\)\s*([\d\s\-]+)", telefones_text):
        ddd = m.group(1)
        num = re.sub(r"\D", "", m.group(2))
        if num:
            results.append(ddd + num)
    return results


def _parse_emails(emails_text: str) -> list[str]:
    return [e.strip() for e in re.split(r"[,;\s]+", emails_text) if "@" in e.strip()]


class KenloMapper(BaseMapper):
    NAME = "Kenlo"
    EXTENSIONS = [".zip"]
    DESCRIPTION = "Kenlo (ZIP com XLSX)"

    def can_handle(self, filename: str) -> bool:
        return filename.lower().endswith(".zip")

    def extract_zip(self, files: dict[str, Any]) -> ExtractionResult:
        result = ExtractionResult()
        seen: set[str] = set()

        clientes_data = self._find(files, "clientes")
        imoveis_data = self._find(files, "imoveis")
        usuarios_data = self._find(files, "usuarios")

        # OW = clientes cujo 'id cliente' aparece em Imoveis como dono
        prop_cli_ids: set[str] = set()
        if imoveis_data:
            for row in imoveis_data:
                cli_id = _v(row, "id cliente")
                if cli_id:
                    prop_cli_ids.add(cli_id)

        if clientes_data:
            for row in clientes_data:
                cli_id = _v(row, "id cliente")
                nome = _v(row, "nome")
                if not nome:
                    continue
                tipo = "OW" if cli_id in prop_cli_ids else "BU"
                self._process_cliente(row, cli_id or nome, tipo, result, seen)

        if usuarios_data:
            for row in usuarios_data:
                usr_id = _v(row, "id")
                nome = _v(row, "nome")
                if not nome:
                    continue
                codigo = "U" + usr_id if usr_id else "U" + re.sub(r"\D", "", _v(row, "cpf"))
                if not codigo or codigo == "U":
                    continue
                self._process_usuario(row, codigo, result, seen)

        return result

    def _find(self, files: dict, prefix: str) -> list[dict] | None:
        def _extract(data):
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                for v in data.values():
                    if isinstance(v, list):
                        return v
            return None

        # Exact stem match first (e.g. "Usuarios.xlsx" not "ClientesUsuarios.xlsx")
        for name, data in files.items():
            stem = name.rsplit(".", 1)[0].lower()
            if stem == prefix.lower():
                r = _extract(data)
                if r is not None:
                    return r
        # Fall back to contains match
        for name, data in files.items():
            if prefix.lower() in name.lower():
                r = _extract(data)
                if r is not None:
                    return r
        return None

    def _process_cliente(
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

        p = PersonRecord()
        p.codigo = codigo
        p.tipo = tipo
        p.nome = _v(row, "nome")
        p.cpf = re.sub(r"\D", "", _v(row, "cpf"))
        p.cnpj = re.sub(r"\D", "", _v(row, "cnpj"))
        p.rg = _v(row, "rg")
        p.data_nascimento = _v(row, "data nascimento")
        p.sexo = _v(row, "sexo")
        p.estado_civil = _v(row, "estado civil")
        p.profissao = _v(row, "profissão", "profissao")
        p.nacionalidade = _v(row, "nacionalidade")
        p.cep = re.sub(r"\D", "", _v(row, "cep"))
        p.cidade = _v(row, "cidade")
        p.bairro = _v(row, "bairro")
        p.estado = _v(row, "uf")
        p.endereco = _v(row, "logradouro")
        p.numero = _v(row, "número", "numero")
        p.complemento = _v(row, "complemento")
        p.observacao = _v(row, "observações", "observacoes")
        result.persons.append(p)

        for digits in _parse_phones(_v(row, "telefones")):
            parsed = processar_telefone(digits)
            if parsed:
                result.phones.append(PhoneRecord(
                    codigo_pessoa=codigo, tipo_pessoa=tipo,
                    ddi=parsed["ddi"], ddd=parsed["ddd"],
                    telefone=parsed["numero"], tipo_telefone=parsed["tipo"],
                ))

        for email in _parse_emails(_v(row, "emails")):
            result.emails.append(EmailRecord(
                codigo_pessoa=codigo, tipo_pessoa=tipo,
                email=email, tipo_email="",
            ))

    def _process_usuario(
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

        p = PersonRecord()
        p.codigo = codigo
        p.tipo = "EM"
        p.nome = _v(row, "nome", "nome completo")
        p.cpf = re.sub(r"\D", "", _v(row, "cpf"))
        if not p.cpf:
            return
        p.rg = _v(row, "rg")
        p.sexo = _v(row, "sexo")
        p.creci = _v(row, "creci")
        p.cep = re.sub(r"\D", "", _v(row, "cep"))
        p.cidade = _v(row, "cidade")
        p.bairro = _v(row, "bairro")
        p.estado = _v(row, "uf")
        p.endereco = _v(row, "logradouro")
        p.numero = _v(row, "número", "numero")
        p.complemento = _v(row, "complemento")
        result.persons.append(p)

        for field in ("telefone", "celular"):
            raw = _v(row, field)
            if not raw:
                continue
            parsed = processar_telefone(raw)
            if parsed:
                result.phones.append(PhoneRecord(
                    codigo_pessoa=codigo, tipo_pessoa="EM",
                    ddi=parsed["ddi"], ddd=parsed["ddd"],
                    telefone=parsed["numero"], tipo_telefone=parsed["tipo"],
                ))

        email = _v(row, "e-mail", "email")
        if email:
            result.emails.append(EmailRecord(
                codigo_pessoa=codigo, tipo_pessoa="EM",
                email=email, tipo_email="",
            ))
