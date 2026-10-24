from decimal import ROUND_HALF_UP, Decimal, InvalidOperation


def format_ars(value, decimals=2):
    """Formatea un importe en pesos argentinos: $ 1.234.567,89"""
    if value is None or value == "":
        return "—"
    try:
        amount = Decimal(value).quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError):
        return str(value)
    sign = "-" if amount < 0 else ""
    integer, _, frac = f"{abs(amount):.{decimals}f}".partition(".")
    groups = []
    while integer:
        groups.insert(0, integer[-3:])
        integer = integer[:-3]
    text = ".".join(groups)
    if decimals:
        text += "," + frac
    return f"{sign}$ {text}"


def format_number(value, decimals=2):
    if value is None:
        return "—"
    return format_ars(value, decimals).replace("$ ", "")
