"""Template para novos mappers. Copie este arquivo e implemente os métodos."""
from __future__ import annotations
import re
from typing import Any

from core.base_mapper import BaseMapper, ExtractionResult, PersonRecord, EmailRecord, PhoneRecord
from core.phone_utils import processar_telefone
# CEP: NÃO é necessário chamar fill_city_state nem lookup_cep_by_city nos mappers.
# O exporter (core/exporter.py e core/property_exporter.py) chama fix_record_cep()
# automaticamente em todos os records antes de gravar o CSV.
# Basta popular p.cep / p.cidade / p.estado com o que vier da fonte (sem hardcode de fallback).

# Para mappers que exportam imóveis, adicionar também:
# from core.property_records import (
#     PropertyExtractionResult, PropertyRecord, PropertyOwnerRecord,
#     PropertyOwnerFavoredRecord, PropertyCaptivatorRecord, PropertyIptuRecord,
#     normalize_address,
# )
# from core.characteristics_utils import build_sim_nao, map_characteristics_to_fields
#
# Uso obrigatório após criar cada PropertyRecord (pr):
#   pr.caracteristicas_sim_nao = build_sim_nao(feature_names)
#   for field, qty in map_characteristics_to_fields(feature_names).items():
#       if not getattr(pr, field, ""):
#           setattr(pr, field, qty)


def _s(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip()


def _fmt_val(v: Any) -> str:
    """Formata valor numérico com 2 casas decimais; retorna '' se zero ou nulo."""
    if v is None or v == "":
        return ""
    try:
        f = float(str(v).replace(",", "."))
        return f"{f:.2f}" if f else ""
    except (ValueError, TypeError):
        return ""


class TemplateMapper(BaseMapper):
    NAME = "Template"
    EXTENSIONS = [".xml"]
    DESCRIPTION = "Descrição do sistema"

    def can_handle(self, filename: str) -> bool:
        return filename.lower().endswith(".xml")

    def extract(self, data: Any) -> ExtractionResult:
        result = ExtractionResult()
        seen: set[str] = set()
        # TODO: implementar extração

        # Regras obrigatórias ao popular PersonRecord:
        # - tipo "EM" somente se cpf/cnpj não estiver vazio após re.sub(r"\D","",...)
        # - sexo: "F" se fonte for "Feminino"/"female"/"f", "M" para outros valores
        # - cep: nunca usar fallback hardcoded; deixar "" se ausente na fonte
        # - popular p.cep, p.cidade, p.estado com o que vier da fonte; o exporter
        #   normaliza e preenche via CEP lookup automaticamente
        # - popular sempre: profissao, nacionalidade, cep, cidade, bairro, estado, endereco, numero

        return result
