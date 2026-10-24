"""Actualización automática de feriados nacionales.

Corre en el servidor, sin intervención del usuario:
- Se dispara sola (en segundo plano) al usarse el sistema si pasaron 7 días desde la última
  actualización exitosa, o 6 horas desde un intento fallido. No depende de que el hosting
  tenga tareas programadas.
- También puede ejecutarse desde un cron con `python manage.py actualizar_feriados`.

Fuentes (en orden): API de ArgentinaDatos y, si falla, Nager.Date. Los feriados cargados a
mano en el sistema nunca se modifican ni se borran.
"""

import datetime
import json
import logging
import threading
import urllib.request
from dataclasses import dataclass, field

from django.conf import settings
from django.db import close_old_connections, transaction
from django.db.models import Q
from django.utils import timezone

from .holidays_data import _upsert
from .models import Holiday

logger = logging.getLogger("hrms.feriados")

TASK_KEY = "feriados"
SYNC_EVERY = datetime.timedelta(days=7)
RETRY_AFTER_ERROR = datetime.timedelta(hours=6)
LOCK_TIMEOUT = datetime.timedelta(minutes=30)
K = Holiday.Kind

KIND_WORDS = {
    "inamovible": K.INAMOVIBLE,
    "trasladable": K.TRASLADABLE,
    "puente": K.PUENTE,
    "no_laborable": K.NO_LABORABLE,
    "no laborable": K.NO_LABORABLE,
}


@dataclass
class YearResult:
    year: int
    source: str = ""
    created: int = 0
    updated: int = 0
    removed: int = 0
    errors: list = field(default_factory=list)

    @property
    def ok(self):
        return bool(self.source)


def _get_json(url, timeout):
    req = urllib.request.Request(url, headers={"User-Agent": "HRMS/1.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _parse_date(value, year):
    try:
        d = datetime.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None
    return d if d.year == year else None


def fetch_argentinadatos(year, timeout=10):
    items = _get_json(f"https://api.argentinadatos.com/v1/feriados/{year}", timeout)
    out = []
    for it in items if isinstance(items, list) else []:
        d = _parse_date(it.get("fecha") or it.get("date"), year)
        if not d:
            continue
        kind = KIND_WORDS.get(str(it.get("tipo") or it.get("type") or "").strip().lower(), K.NO_LABORABLE)
        out.append((d, (it.get("nombre") or it.get("motivo") or it.get("name") or "Feriado")[:150], kind))
    return out


def fetch_nager(year, timeout=10):
    items = _get_json(f"https://date.nager.at/api/v3/PublicHolidays/{year}/AR", timeout)
    out = []
    for it in items if isinstance(items, list) else []:
        d = _parse_date(it.get("date"), year)
        if d:
            out.append((d, (it.get("localName") or it.get("name") or "Feriado")[:150], K.INAMOVIBLE))
    return out


SOURCES = [("ArgentinaDatos", fetch_argentinadatos, True), ("Nager.Date", fetch_nager, False)]


def sync_year(year, timeout=10):
    """Descarga y aplica los feriados de un año. Devuelve YearResult."""
    result = YearResult(year)
    for name, fetch, authoritative in SOURCES:
        try:
            items = fetch(year, timeout)
        except Exception as e:  # red caída, API fuera de servicio, formato inesperado
            result.errors.append(f"{name}: {e}")
            continue
        if not items:
            result.errors.append(f"{name}: sin datos para {year}")
            continue
        with transaction.atomic():
            dates = set()
            for d, holiday_name, kind in items:
                dates.add(d)
                if _upsert(d, holiday_name, kind, source="api", update_existing=authoritative):
                    result.created += 1
                else:
                    result.updated += 1
            # Solo la fuente principal (completa, con trasladables y puentes) puede quitar fechas
            # que ya no figuran, por ejemplo un feriado trasladado por decreto. Nunca los manuales.
            if authoritative and len(items) >= 8:
                stale = Holiday.objects.filter(date__year=year, source__in=["api", "sistema"]).exclude(date__in=dates)
                result.removed = stale.count()
                stale.delete()
        result.source = name
        return result
    return result


def years_to_sync(today=None):
    today = today or timezone.localdate()
    return [today.year, today.year + 1]


def _task():
    from apps.core.models import SystemTask

    return SystemTask.objects.get_or_create(key=TASK_KEY)[0]


def is_due(task=None, now=None):
    task = task or _task()
    now = now or timezone.now()
    if not task.last_success:
        return not task.last_attempt or now - task.last_attempt >= RETRY_AFTER_ERROR
    if now - task.last_success >= SYNC_EVERY:
        return not task.last_error or now - task.last_attempt >= RETRY_AFTER_ERROR
    return False


def _acquire_lock(now):
    from apps.core.models import SystemTask

    _task()
    return SystemTask.objects.filter(key=TASK_KEY).filter(
        Q(running_since__isnull=True) | Q(running_since__lt=now - LOCK_TIMEOUT)
    ).update(running_since=now) == 1


def run_sync(force=False):
    """Ejecuta la actualización si corresponde (o siempre, con force). Devuelve lista de YearResult o None."""
    from apps.core.models import SystemTask

    now = timezone.now()
    if not force and not is_due(now=now):
        return None
    if not _acquire_lock(now):
        return None
    results = []
    try:
        for year in years_to_sync():
            results.append(sync_year(year))
        current = results[0]
        errors = [e for r in results for e in r.errors if not r.ok]
        summary = ", ".join(
            f"{r.year}: {r.source} (+{r.created}, act. {r.updated}, −{r.removed})" if r.ok else f"{r.year}: sin datos"
            for r in results
        )
        fields = {"last_attempt": now, "detail": summary[:250], "running_since": None}
        if current.ok:
            fields.update(last_success=timezone.now(), last_error="")
        else:
            fields["last_error"] = "; ".join(errors)[:2000] or "Sin respuesta de las fuentes."
        SystemTask.objects.filter(key=TASK_KEY).update(**fields)
        logger.info("Feriados actualizados: %s", summary)
    except Exception as e:
        SystemTask.objects.filter(key=TASK_KEY).update(last_attempt=now, last_error=str(e)[:2000], running_since=None)
        logger.exception("Error actualizando feriados")
    return results


_check_lock = threading.Lock()
_next_check = None


def maybe_sync_in_background():
    """Llamado en cada request: como mucho cada 10 minutos consulta si toca actualizar y, si toca,
    lanza la actualización en un hilo para no demorar al usuario."""
    global _next_check
    if not getattr(settings, "HRMS_HOLIDAY_AUTO_SYNC", True):
        return
    now = timezone.now()
    with _check_lock:
        if _next_check and now < _next_check:
            return
        _next_check = now + datetime.timedelta(minutes=10)
    try:
        if not is_due(now=now):
            return
    except Exception:  # base de datos sin migrar, etc.
        return

    def worker():
        try:
            run_sync()
        finally:
            close_old_connections()

    threading.Thread(target=worker, name="hrms-feriados", daemon=True).start()


def last_update():
    from apps.core.models import SystemTask

    return SystemTask.objects.filter(key=TASK_KEY).first()
