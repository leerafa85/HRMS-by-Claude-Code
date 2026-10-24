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
