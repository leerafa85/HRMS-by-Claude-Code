"""Reglas de la Ley de Contrato de Trabajo (Ley 20.744 y modificatorias, incl. Ley 27.802).

Se concentran acá para poder ajustarlas si cambia la normativa o el convenio
colectivo de la empresa establece condiciones más favorables.
"""

import datetime
from decimal import Decimal


def count_days(start, end, business_days=False, holidays=(), include_saturday=False):
    """Cuenta días entre dos fechas inclusive.

    - Corridos: todos los días.
    - Hábiles: excluye domingos, feriados y sábados (salvo que el empleado trabaje sábados).
    """
    if end < start:
        return 0
    total = 0
    day = start
    holidays = set(holidays)
    while day <= end:
        if not business_days:
            total += 1
        else:
            weekday = day.weekday()
            is_weekend = weekday == 6 or (weekday == 5 and not include_saturday)
            if not is_weekend and day not in holidays:
                total += 1
        day += datetime.timedelta(days=1)
    return total


def vacation_days_for_seniority(years):
    """Art. 150 LCT: días corridos de vacaciones según antigüedad al 31/12 del período."""
    if years < 5:
        return 14
    if years < 10:
        return 21
    if years < 20:
        return 28
    return 35


def vacation_entitlement(employee, year):
    """Días de vacaciones que corresponden al empleado por el período `year`.

    - Antigüedad computada al 31 de diciembre del año (art. 150).
    - Si no trabajó al menos la mitad de los días hábiles del año (en la práctica,
      ingreso posterior al 30/06 aprox.), corresponde 1 día cada 20 días trabajados (art. 153).
    """
    start = employee.seniority_start
    year_end = datetime.date(year, 12, 31)
    if start > year_end:
        return Decimal(0)
    if employee.termination_date and employee.termination_date.year < year:
        return Decimal(0)
    years = employee.seniority_years(year_end)
    full = vacation_days_for_seniority(years)

    period_start = max(start, datetime.date(year, 1, 1))
    business_in_year = count_days(datetime.date(year, 1, 1), year_end, business_days=True)
    worked_business = count_days(period_start, year_end, business_days=True)
    if worked_business * 2 >= business_in_year:
        return Decimal(full)
    # Art. 153: un día de vacaciones por cada 20 días de trabajo efectivo.
    return Decimal(worked_business // 20)


def sick_leave_months(seniority_years, has_dependents):
    """Art. 208 LCT: meses de licencia paga por enfermedad inculpable por año."""
    months = 3 if seniority_years < 5 else 6
    return months * 2 if has_dependents else months


def overtime_rate(date, start_time=None, is_holiday=False):
    """Recargo sugerido de horas extras (art. 201 LCT): 50 % días comunes; 100 % sábados
    después de las 13 h, domingos y feriados."""
    if is_holiday or date.weekday() == 6:
        return 100
    if date.weekday() == 5 and start_time and start_time >= datetime.time(13, 0):
        return 100
    return 50
