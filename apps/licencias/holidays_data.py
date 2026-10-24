"""Feriados nacionales de Argentina.

La lista 2026 se armó a partir del calendario oficial difundido por el Gobierno
nacional (Ley 27.399 y decreto de días no laborables con fines turísticos).
Verificá siempre contra https://www.argentina.gob.ar/interior/feriados, ya que el
Poder Ejecutivo puede agregar o mover fechas durante el año.
"""

import datetime
import json
import urllib.request

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

API_KINDS = {"inamovible": K.INAMOVIBLE, "trasladable": K.TRASLADABLE, "puente": K.PUENTE}


def _upsert(date, name, kind):
    obj, created = Holiday.objects.update_or_create(
        date=date, defaults={"name": name, "kind": kind, "is_working_day_optional": kind in (K.PUENTE, K.NO_LABORABLE)}
    )
    return created


def load_local(year):
    """Carga los feriados conocidos del año (lista curada o, si no hay, solo los de fecha fija)."""
    data = HOLIDAYS.get(year)
    if data is None:
        data = [(f"{year}-{md}", name, K.INAMOVIBLE) for md, name in FIXED]
    created = sum(_upsert(datetime.date.fromisoformat(d), n, k) for d, n, k in data)
    return created, len(data) - created


def import_from_api(year, timeout=10):
    url = f"https://api.argentinadatos.com/v1/feriados/{year}"
    req = urllib.request.Request(url, headers={"User-Agent": "HRMS/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        items = json.loads(resp.read().decode("utf-8"))
    created = 0
    for it in items:
        kind = API_KINDS.get(it.get("tipo", ""), K.NO_LABORABLE)
        created += _upsert(datetime.date.fromisoformat(it["fecha"]), it.get("nombre", "Feriado"), kind)
    return created, len(items) - created
