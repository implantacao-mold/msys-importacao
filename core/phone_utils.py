import re


def processar_telefone(raw: str, ddd_hint: str = "") -> dict | None:
    """Valida e normaliza um número de telefone.

    Retorna dict com ddi, ddd, numero, tipo ou None se inválido.
    """
    if not raw:
        return None

    digits = re.sub(r"\D", "", raw)

    # Remove DDI 55 se o número ficar muito longo
    if digits.startswith("55") and len(digits) > 11:
        digits = digits[2:]

    if len(digits) < 8:
        return None

    # Todos os dígitos iguais
    if len(set(digits)) == 1:
        return None

    ddi = "55"
    ddd = ddd_hint or "00"
    numero = digits

    if len(digits) >= 10:
        ddd = digits[:2]
        numero = digits[2:]
    elif ddd_hint:
        ddd = ddd_hint
        numero = digits

    # Valida DDD brasileiro (11-99)
    if ddd != "00":
        try:
            ddd_int = int(ddd)
            if ddd_int < 11 or ddd_int > 99:
                ddd = "00"
        except ValueError:
            ddd = "00"

    # Tipo: celular se começa com 9 e tem 9 dígitos
    if len(numero) == 9 and numero.startswith("9"):
        tipo = "M"
    elif len(numero) == 8:
        tipo = "R"
    else:
        tipo = "M"

    return {"ddi": ddi, "ddd": ddd, "numero": numero, "tipo": tipo}
