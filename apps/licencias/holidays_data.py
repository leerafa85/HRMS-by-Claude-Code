"""Feriados nacionales de Argentina.

La lista 2026 se armó a partir del calendario oficial difundido por el Gobierno
nacional (Ley 27.399 y decreto de días no laborables con fines turísticos).
Verificá siempre contra https://www.argentina.gob.ar/interior/feriados, ya que el
Poder Ejecutivo puede agregar o mover fechas durante el año.
"""

import datetime

from .models import Holiday

K = Holiday.Kind

HOLIDAYS = {
    2026: [
        ("2026-01-01", "Año Nuevo", K.INAMOVIBLE),
        ("2026-02-16", "Carnaval", K.INAMOVIBLE),
        ("2026-02-17", "Carnaval", K.INAMOVIBLE),
        ("2026-03-23", "Día no laborable con fines turísticos", K.PUENTE),
        ("2026-03-24", "Día Nacional de la Memoria por la Verdad y la Justicia", K.INAMOVIBLE),
        ("2026-04-02", "Día del Veterano y de los Caídos en la Guerra de Malvinas / Jueves Santo", K.INAMOVIBLE),
        ("2026-04-03", "Viernes Santo", K.INAMOVIBLE),
        ("2026-05-01", "Día del Trabajador", K.INAMOVIBLE),
        ("2026-05-25", "Día de la Revolución de Mayo", K.INAMOVIBLE),
        ("2026-06-15", "Paso a la Inmortalidad del Gral. Martín Miguel de Güemes (17/6)", K.TRASLADABLE),
        ("2026-06-20", "Paso a la Inmortalidad del Gral. Manuel Belgrano", K.INAMOVIBLE),
        ("2026-07-09", "Día de la Independencia", K.INAMOVIBLE),
        ("2026-07-10", "Día no laborable con fines turísticos", K.PUENTE),
        ("2026-08-17", "Paso a la Inmortalidad del Gral. José de San Martín", K.TRASLADABLE),
        ("2026-10-12", "Día del Respeto a la Diversidad Cultural", K.TRASLADABLE),
        ("2026-11-23", "Día de la Soberanía Nacional (20/11)", K.TRASLADABLE),
        ("2026-12-07", "Día no laborable con fines turísticos", K.PUENTE),
        ("2026-12-08", "Inmaculada Concepción de María", K.INAMOVIBLE),
        ("2026-12-25", "Navidad", K.INAMOVIBLE),
    ],
}

# Feriados de fecha fija (inamovibles) que se repiten todos los años. Carnaval y
# Semana Santa dependen de la Pascua y los trasladables de cada decreto anual.
FIXED = [
    ("01-01", "Año Nuevo"),
    ("03-24", "Día Nacional de la Memoria por la Verdad y la Justicia"),
    ("04-02", "Día del Veterano y de los Caídos en la Guerra de Malvinas"),
    ("05-01", "Día del Trabajador"),
    ("05-25", "Día de la Revolución de Mayo"),
    ("06-20", "Paso a la Inmortalidad del Gral. Manuel Belgrano"),
    ("07-09", "Día de la Independencia"),
    ("12-08", "Inmaculada Concepción de María"),
    ("12-25", "Navidad"),
]

def _upsert(date, name, kind, source="sistema", update_existing=True):
    """Crea o actualiza un feriado. Nunca toca los cargados a mano. Devuelve True si lo creó."""
    existing = Holiday.objects.filter(date=date).first()
    if existing and (existing.source == "manual" or not update_existing):
        return False
    optional = kind in (K.PUENTE, K.NO_LABORABLE)
    if existing:
        if (existing.name, existing.kind, existing.source) != (name, kind, source):
            existing.name, existing.kind, existing.source = name, kind, source
            existing.is_working_day_optional = optional
            existing.save()
        return False
    Holiday.objects.create(date=date, name=name, kind=kind, source=source, is_working_day_optional=optional)
    return True


def load_local(year):
    """Precarga los feriados conocidos del año si todavía no hay ninguno cargado para ese año
    (lista curada o, si no hay, solo los de fecha fija). Después se mantienen con la actualización automática."""
    if Holiday.objects.filter(date__year=year).exists():
        return 0, 0
    data = HOLIDAYS.get(year)
    if data is None:
        data = [(f"{year}-{md}", name, K.INAMOVIBLE) for md, name in FIXED]
    created = sum(_upsert(datetime.date.fromisoformat(d), n, k) for d, n, k in data)
    return created, len(data) - created


def import_from_api(year, timeout=10):
    """Importación manual (botón «Importar feriados»): usa la misma lógica que la actualización automática."""
    from .sync import sync_year

    result = sync_year(year, timeout=timeout)
    return result.created, result.updated
