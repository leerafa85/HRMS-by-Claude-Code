import datetime
from unittest import mock

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.core.models import SystemTask
from apps.licencias import sync
from apps.licencias.holidays_data import load_local
from apps.licencias.models import Holiday

from .base import HRTestCase

Y = timezone.localdate().year
D = datetime.date


def api_items(year):
    return [(D(year, 1, 1), "Año nuevo", "inamovible"), (D(year, 3, 24), "Memoria", "inamovible"),
            (D(year, 4, 2), "Malvinas", "inamovible"), (D(year, 5, 1), "Trabajador", "inamovible"),
            (D(year, 5, 25), "Revolución de Mayo", "inamovible"), (D(year, 6, 15), "Güemes", "trasladable"),
            (D(year, 7, 9), "Independencia", "inamovible"), (D(year, 7, 10), "Puente turístico", "puente"),
            (D(year, 12, 25), "Navidad", "inamovible")]


def fake_argentinadatos(year, timeout=10):
    return api_items(year)


def failing(year, timeout=10):
    raise OSError("sin conexión")


class HolidaySyncTests(TestCase):
    def setUp(self):
        Holiday.objects.create(date=D(Y, 11, 20), name="Soberanía (fecha vieja)", kind="trasladable", source="sistema")
        Holiday.objects.create(date=D(Y, 9, 15), name="Feriado de la empresa", kind="empresa", source="manual")
        Holiday.objects.create(date=D(Y, 12, 25), name="Navidad (mi nombre)", kind="inamovible", source="manual")

    def test_sync_updates_removes_stale_and_keeps_manual(self):
        with mock.patch.object(sync, "SOURCES", [("ArgentinaDatos", fake_argentinadatos, True)]):
            r = sync.sync_year(Y)
        self.assertEqual(r.source, "ArgentinaDatos")
        self.assertTrue(Holiday.objects.filter(date=D(Y, 7, 10), kind="puente", source="api").exists())
        self.assertFalse(Holiday.objects.filter(date=D(Y, 11, 20)).exists())  # ya no figura: se quita
        self.assertTrue(Holiday.objects.filter(date=D(Y, 9, 15)).exists())  # manual: se conserva
        self.assertEqual(Holiday.objects.get(date=D(Y, 12, 25)).name, "Navidad (mi nombre)")  # manual: no se pisa

    def test_fallback_source_only_adds(self):
        def nager(year, timeout=10):
            return [(D(year, 1, 1), "New Year", "inamovible"), (D(year, 11, 20), "Soberanía", "inamovible")]

        with mock.patch.object(sync, "SOURCES", [("A", failing, True), ("Nager.Date", nager, False)]):
            r = sync.sync_year(Y)
        self.assertEqual(r.source, "Nager.Date")
        self.assertTrue(Holiday.objects.filter(date=D(Y, 1, 1)).exists())
        self.assertEqual(Holiday.objects.get(date=D(Y, 11, 20)).kind, "trasladable")  # no se modifica

    def test_run_sync_records_timestamp_and_weekly_schedule(self):
        with mock.patch.object(sync, "SOURCES", [("ArgentinaDatos", fake_argentinadatos, True)]):
            self.assertTrue(sync.is_due())
            sync.run_sync()
        task = SystemTask.objects.get(key="feriados")
        self.assertIsNotNone(task.last_success)
        self.assertIsNone(task.running_since)
        self.assertFalse(sync.is_due())
        self.assertTrue(sync.is_due(now=timezone.now() + datetime.timedelta(days=7, minutes=1)))

    def test_failed_sync_keeps_data_and_retries_later(self):
        before = Holiday.objects.count()
        with mock.patch.object(sync, "SOURCES", [("A", failing, True)]):
            sync.run_sync()
        task = SystemTask.objects.get(key="feriados")
        self.assertIsNone(task.last_success)
        self.assertIn("sin conexión", task.last_error)
        self.assertEqual(Holiday.objects.count(), before)
        self.assertFalse(sync.is_due())
        self.assertTrue(sync.is_due(now=timezone.now() + datetime.timedelta(hours=6, minutes=1)))

    def test_lock_prevents_parallel_runs(self):
        now = timezone.now()
        self.assertTrue(sync._acquire_lock(now))
        self.assertFalse(sync._acquire_lock(now))
        self.assertIsNone(sync.run_sync(force=True))

    def test_seed_does_not_reload_existing_year(self):
        self.assertEqual(load_local(Y), (0, 0))

    @override_settings(HRMS_HOLIDAY_AUTO_SYNC=True)
    def test_background_trigger(self):
        sync._next_check = None
        with mock.patch("apps.licencias.sync.threading.Thread") as thread:
            sync.maybe_sync_in_background()
            thread.assert_called_once()
            sync.maybe_sync_in_background()  # no vuelve a consultar antes de 10 minutos
            thread.assert_called_once()


class FrontTests(HRTestCase):
    def test_holiday_legend_and_manual_edit(self):
        self.client.force_login(self.admin)
        r = self.client.get(reverse("licencias:feriado_list"))
        self.assertContains(r, "Última actualización:")
        self.assertContains(r, "pendiente")
        SystemTask.objects.update_or_create(key="feriados", defaults={"last_success": timezone.now()})
        self.assertNotContains(self.client.get(reverse("licencias:feriado_list")), "pendiente")
        h = Holiday.objects.filter(source="sistema").first()
        self.client.post(reverse("licencias:feriado_update", args=[h.pk]),
                         {"date": h.date.isoformat(), "name": "Editado", "kind": h.kind})
        h.refresh_from_db()
        self.assertEqual(h.source, "manual")

    def test_health_endpoint(self):
        r = self.client.get(reverse("estado"))  # sin iniciar sesión
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "ok")
        self.assertEqual(r["Cache-Control"], "no-store")
        self.assertTrue(SystemTask.objects.filter(key="heartbeat").exists())
        with mock.patch("apps.core.models.SystemTask.objects.filter", side_effect=Exception("db caída")):
            r = self.client.get(reverse("estado"))
        self.assertEqual(r.status_code, 503)

    def test_status_bar_in_layout(self):
        self.assertContains(self.client.get(reverse("login")), 'id="statusBar"')
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse("dashboard")), 'id="sbClock"')


class YearFormatTests(HRTestCase):
    def test_years_without_thousand_separator(self):
        self.client.force_login(self.admin)
        r = self.client.get(reverse("licencias:feriado_list"), {"anio": Y})
        self.assertContains(r, f"?anio={Y - 1}")
        self.assertNotContains(r, f"{Y // 1000}.{Y % 1000:03d}")
