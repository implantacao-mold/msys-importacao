from __future__ import annotations
import pytest
from core.characteristics_utils import match_feature, build_sim_nao


def test_exact_match():
    assert match_feature("Piscina") == "Piscina"


def test_exact_case_insensitive():
    assert match_feature("PISCINA") == "Piscina"
    assert match_feature("piscina") == "Piscina"


def test_fuzzy_match_returns_none():
    # Fuzzy matching foi removido de match_feature: só exato e EN→PT são automáticos.
    # "AR CONDICIONADO" sem mapeamento customizado → None (vai para revisão do usuário).
    from core.characteristics_utils import _custom, _norm
    norm_key = _norm("AR CONDICIONADO")
    if norm_key not in _custom:
        assert match_feature("AR CONDICIONADO") is None


def test_scan_feature_fuzzy_is_uncertain():
    from core.characteristics_utils import scan_feature, _custom, _norm
    norm_key = _norm("AR CONDICIONADO")
    if norm_key not in _custom:
        info = scan_feature("AR CONDICIONADO")
        assert info["status"] == "uncertain"
        assert "suggested" in info


def test_english_mapping():
    assert match_feature("pool") == "Piscina"
    assert match_feature("sauna") == "Sauna"


def test_unrecognized_returns_none():
    assert match_feature("COISA COMPLETAMENTE INEXISTENTE XYZ") is None


# --- Blocklist de proximidades ---

def test_blocklist_bares_e_restaurantes():
    """'Bares e Restaurantes' indica proximidade, não que o imóvel tem restaurante."""
    assert match_feature("BARES E RESTAURANTES") is None
    assert match_feature("Bares e Restaurantes") is None


def test_blocklist_restaurantes_plural():
    assert match_feature("RESTAURANTES") is None


def test_blocklist_escola():
    assert match_feature("Escola") is None
    assert match_feature("ESCOLA") is None


def test_blocklist_farmacia():
    assert match_feature("Farmácia") is None
    assert match_feature("FARMÁCIA") is None


def test_blocklist_supermercado():
    assert match_feature("Supermercado") is None


def test_blocklist_voltagem():
    assert match_feature("Voltagem 220V") is None
    assert match_feature("VOLTAGEM 110V 220V") is None
    assert match_feature("Voltagem 110V / 220V") is None


# --- Cômodos — falsos positivos confirmados ---

def test_blocklist_banheiro_nao_vira_banheira():
    """'Banheiro' (cômodo) batia em 'Banheira' (feature) com score 0.88."""
    assert match_feature("Banheiro") is None
    assert match_feature("BANHEIRO") is None


def test_blocklist_quarto_nao_vira_quadra():
    """'Quarto' batia em 'Quadra' com score 0.67."""
    assert match_feature("Quarto") is None


def test_blocklist_cozinha_nao_vira_cortina():
    """'Cozinha' batia em 'Cortina' com score 0.71."""
    assert match_feature("Cozinha") is None
    assert match_feature("COZINHA") is None


def test_blocklist_copa_nao_vira_coifa():
    """'Copa' batia em 'Coifa' com score 0.67."""
    assert match_feature("Copa") is None


def test_blocklist_sala_nao_vira_sauna():
    """'Sala' batia em 'Sauna' com score 0.67."""
    assert match_feature("Sala") is None


def test_sala_de_estar_continua_mapeada():
    """'Sala de Estar' é match exato canônico — não deve ser bloqueada."""
    result = match_feature("Sala de Estar")
    assert result is not None
    assert "Sala" in result


def test_blocklist_proximo_ao_mar_nao_vira_metro():
    """'Próximo ao mar' batia em 'Próximo ao metrô' com score 0.87 após remoção de acentos."""
    assert match_feature("Próximo ao mar") is None
    assert match_feature("PROXIMO AO MAR") is None


def test_blocklist_does_not_block_canonical_restaurante():
    """'Restaurante' singular (característica do imóvel) deve continuar sendo mapeado."""
    result = match_feature("Restaurante")
    assert result == "Restaurante"


def test_build_sim_nao_skips_proximity():
    features = ["PISCINA", "BARES E RESTAURANTES", "Escola", "AR CONDICIONADO"]
    result = build_sim_nao(features)
    assert "Piscina" in result
    assert "Restaurante" not in result
    assert "Bar" not in result
    assert "Escola" not in result


def test_build_sim_nao_deduplicates():
    result = build_sim_nao(["Piscina", "PISCINA", "piscina"])
    assert result.count("Piscina") == 1


def test_build_sim_nao_empty():
    assert build_sim_nao([]) == ""


def test_build_sim_nao_all_unmatched():
    assert build_sim_nao(["XYZXYZXYZ", "ABCDEFGHIJ", "ESCOLA"]) == ""


# ---------------------------------------------------------------------------
# map_characteristics_to_fields
# ---------------------------------------------------------------------------
from core.characteristics_utils import map_characteristics_to_fields


def test_field_map_singular_defaults_to_1():
    result = map_characteristics_to_fields(["COZINHA"])
    assert result == {"cozinhas": "1"}


def test_field_map_plural_defaults_to_1():
    result = map_characteristics_to_fields(["BANHEIROS"])
    assert result == {"banheiros": "1"}


def test_field_map_quantity_prefix():
    """'3 Dormitórios' → dormitorios=3"""
    result = map_characteristics_to_fields(["3 DORMITORIOS"])
    assert result.get("dormitorios") == "3"


def test_field_map_quantity_suffix():
    """'Suítes 2' → suites=2"""
    result = map_characteristics_to_fields(["SUITES 2"])
    assert result.get("suites") == "2"


def test_field_map_quantity_colon():
    """'Cozinhas: 2' → cozinhas=2"""
    result = map_characteristics_to_fields(["COZINHAS: 2"])
    assert result.get("cozinhas") == "2"


def test_field_map_first_occurrence_wins():
    """Duas ocorrências do mesmo campo: a primeira prevalece."""
    result = map_characteristics_to_fields(["COPA", "2 COPAS"])
    assert result.get("copas") == "1"


def test_field_map_ignores_unknown():
    result = map_characteristics_to_fields(["BARES E RESTAURANTES", "ESCOLA", "VOLTAGEM 220V"])
    assert result == {}


def test_field_map_multiple_fields():
    result = map_characteristics_to_fields(["COZINHA", "COPA", "DESPENSA", "2 SUITES"])
    assert result.get("cozinhas") == "1"
    assert result.get("copas") == "1"
    assert result.get("despensas") == "1"
    assert result.get("suites") == "2"


def test_field_map_uppercase_cdata_style():
    """Simula como _caracs() entrega os valores após strip+upper das aspas do CDATA."""
    result = map_characteristics_to_fields(["LAVANDERIA", "ESCRITORIO", "HALL"])
    assert result.get("lavanderias") == "1"
    assert result.get("escritorio") == "1"
    assert result.get("halls") == "1"
