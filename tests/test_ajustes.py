import datetime
from decimal import Decimal
from unittest import mock

from django.urls import reverse

from apps.empleados import ajustes
from apps.empleados.models import IPCValue, SalaryAdjustment, SalaryAdjustmentPlan, add_months

from .base import HRTestCase


class AddMonthsTests(HRTestCase):
    def test_end_of_month(self):
        self.assertEqual(add_months(datetime.date(2026, 1, 31), 1), datetime.date(2026, 2, 28))
        self.assertEqual(add_months(datetime.date(2026, 11, 15), 3), datetime.date(2027, 2, 15))
        self.assertEqual(add_months(datetime.date(2026, 3, 1), -3), datetime.date(2025, 12, 1))


class PlanScheduleTests(HRTestCase):
    def setUp(self):
        # emp ingresó el 10/01/2022
        SalaryAdjustment.objects.create(employee=self.emp, effective_date=datetime.date(2026, 4, 1),
                                        new_salary=Decimal("1000000"))

    def plan(self, **kw):
        return SalaryAdjustmentPlan.objects.create(employee=self.emp, **kw)

    def test_calendar_quarterly_from_january(self):
        p = self.plan(frequency_months=3, reference="calendario", start_month=1, method="porcentaje", percent=5)
        self.assertEqual(p.next_date(), datetime.date(2026, 7, 1))

    def test_calendar_monthly(self):
        p = self.plan(frequency_months=1, reference="calendario", method="porcentaje", percent=5)
        self.assertEqual(p.next_date(), datetime.date(2026, 5, 1))

    def test_calendar_semester_from_march(self):
        p = self.plan(frequency_months=6, reference="calendario", start_month=3, method="porcentaje", percent=5)
        self.assertEqual(p.next_date(), datetime.date(2026, 9, 1))

    def test_from_hire_date_annual(self):
        p = self.plan(frequency_months=12, reference="ingreso", method="porcentaje", percent=5)
        self.assertEqual(p.next_date(), datetime.date(2027, 1, 10))

    def test_from_hire_date_quarterly(self):
        p = self.plan(frequency_months=3, reference="ingreso", method="porcentaje", percent=5)
        self.assertEqual(p.next_date(), datetime.date(2026, 4, 10))

    def test_fixed_percent_and_amount(self):
        p = self.plan(frequency_months=3, method="porcentaje", percent=Decimal("10"))
        new, pct, missing = p.estimate(Decimal("1000000"), datetime.date(2026, 7, 1))
        self.assertEqual(new, Decimal("1100000.00"))
        p.method, p.amount = "monto", Decimal("50000")
        new, pct, _ = p.estimate(Decimal("1000000"), datetime.date(2026, 7, 1))
        self.assertEqual(new, Decimal("1050000.00"))
        self.assertEqual(pct, Decimal("5"))

    def test_ipc_compounded_with_lag(self):
        p = self.plan(frequency_months=3, method="ipc", ipc_lag_months=1)
        # Ajuste 01/07 con 1 mes de rezago: marzo, abril y mayo
        self.assertEqual(p.ipc_months(datetime.date(2026, 7, 1)),
                         [datetime.date(2026, 3, 1), datetime.date(2026, 4, 1), datetime.date(2026, 5, 1)])
        new, _, missing = p.estimate(Decimal("1000000"), datetime.date(2026, 7, 1))
        self.assertEqual(len(missing), 3)
        for m, v in [(3, "2"), (4, "3"), (5, "1")]:
            IPCValue.objects.create(month=datetime.date(2026, m, 15), variation=Decimal(v))
        new, pct, missing = p.estimate(Decimal("1000000"), datetime.date(2026, 7, 1))
        self.assertEqual(missing, [])
        self.assertEqual(new, Decimal("1061106.00"))  # 1,02 * 1,03 * 1,01

    def test_apply_creates_adjustment_and_moves_next_date(self):
        self.plan(frequency_months=3, reference="calendario", method="porcentaje", percent=Decimal("10"))
        row = ajustes.compute(self.emp)
        adj = ajustes.apply(row, self.admin)
        self.assertEqual(adj.effective_date, datetime.date(2026, 7, 1))
        self.assertEqual(adj.new_salary, Decimal("1100000.00"))
        self.assertEqual(ajustes.compute(self.emp).next_date, datetime.date(2026, 10, 1))

    def test_apply_blocked_without_ipc(self):
        self.plan(frequency_months=3, method="ipc")
        row = ajustes.compute(self.emp)
        self.assertFalse(row.can_apply)
        with self.assertRaises(ValueError):
            ajustes.apply(row, self.admin)

    def test_status_overdue(self):
        self.plan(frequency_months=3, reference="calendario", method="porcentaje", percent=5)
        with mock.patch("apps.empleados.ajustes.datetime") as dt:
            dt.date.today.return_value = datetime.date(2026, 8, 1)
            row = ajustes.compute(self.emp)
            self.assertEqual(row.days_left, -31)
            self.assertEqual(row.status, "vencido")


class UpcomingViewTests(HRTestCase):
    def test_page_and_apply_selected(self):
        SalaryAdjustment.objects.create(employee=self.emp, effective_date=datetime.date(2026, 4, 1), new_salary=Decimal("1000"))
        SalaryAdjustmentPlan.objects.create(employee=self.emp, frequency_months=3, method="porcentaje", percent=Decimal("10"))
        self.client.force_login(self.admin)
        url = reverse("empleados:proximos_ajustes")
        r = self.client.get(url)
        self.assertContains(r, self.emp.last_name)
        self.assertContains(r, "Sin esquema")
        self.client.post(url, {"empleado": [self.emp.pk]})
        self.assertEqual(self.emp.salary_adjustments.count(), 2)
        self.assertEqual(self.client.get(url, {"exportar": 1}).status_code, 200)

    def test_plan_form_and_permissions(self):
        self.client.force_login(self.emp_user)
        self.assertEqual(self.client.get(reverse("empleados:proximos_ajustes")).status_code, 403)
        self.client.force_login(self.admin)
        url = reverse("empleados:esquema_edit", args=[self.emp.pk])
        r = self.client.post(url, {"frequency_months": 3, "reference": "calendario", "start_month": 1,
                                   "method": "porcentaje", "ipc_extra_percent": 0, "ipc_lag_months": 1, "active": "on"})
        self.assertEqual(r.status_code, 200)  # falta el porcentaje
        r = self.client.post(url, {"frequency_months": 3, "reference": "calendario", "start_month": 1,
                                   "method": "porcentaje", "percent": "8", "ipc_extra_percent": 0, "ipc_lag_months": 1,
                                   "active": "on"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.emp.salary_plan.percent, Decimal("8"))

    def test_bulk_assign(self):
        self.client.force_login(self.admin)
        r = self.client.post(reverse("empleados:esquema_masivo"), {
            "frequency_months": 12, "reference": "ingreso", "start_month": 1, "method": "ipc",
            "ipc_extra_percent": 0, "ipc_lag_months": 1, "active": "on", "only_without_plan": "on"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(SalaryAdjustmentPlan.objects.count(), 3)

    def test_ipc_month_input(self):
        self.client.force_login(self.admin)
        r = self.client.post(reverse("empleados:ipc_create"), {"month": "2026-09", "variation": "2.1", "source": "INDEC"})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(IPCValue.objects.filter(month=datetime.date(2026, 9, 1)).exists())
