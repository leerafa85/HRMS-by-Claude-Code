import datetime


def next_occurrence(d, today=None):
    """Próxima fecha (hoy inclusive) en que se cumple el aniversario de `d`. El 29/02 se celebra el 01/03."""
    today = today or datetime.date.today()
    for year in (today.year, today.year + 1):
        try:
            candidate = d.replace(year=year)
        except ValueError:
            candidate = datetime.date(year, 3, 1)
        if candidate >= today:
            return candidate
    return None


MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre",
         "Noviembre", "Diciembre"]
MONTH_CHOICES = [(i + 1, m) for i, m in enumerate(MESES)]
DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]


# ---------------------------------------------------------------- Mes trabajado / mes de cobro
# Criterio de la empresa: la vigencia de un sueldo indica el MES TRABAJADO. Ese mes se abona
# en el mes siguiente, dentro de la franja de días de acreditación de cada empleado.


def month_label(d):
    return f"{MESES[d.month - 1]} {d.year}" if d else ""


def payment_month(d):
    """Primer día del mes en que se cobra el mes trabajado de la fecha `d`."""
    if not d:
        return None
    return datetime.date(d.year + (d.month == 12), d.month % 12 + 1, 1)


def worked_month_text(d, employee=None):
    """Texto aclaratorio: «mes trabajado Noviembre 2026 · se abona en Diciembre 2026 (días 1 al 5)»."""
    if not d:
        return ""
    text = f"mes trabajado {month_label(d)} · se abona en {month_label(payment_month(d))}"
    if employee is not None and getattr(employee, "pay_day_from", None):
        text += f" (días {employee.pay_day_from} al {employee.pay_day_to})"
    return text
