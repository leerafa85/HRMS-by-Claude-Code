import datetime
from decimal import Decimal

from django.urls import reverse

from apps.core.dates import month_label, payment_month, worked_month_text
from apps.empleados.models import SalaryAdjustment

from .base import HRTestCase

D = datetime.date


class WorkedMonthTests(HRTestCase):
    def test_helpers(self):
        self.assertEqual(payment_month(D(2026, 11, 1)), D(2026, 12, 1))
        self.assertEqual(payment_month(D(2026, 12, 15)), D(2027, 1, 1))
        self.assertEqual(month_label(D(2026, 11, 1)), "Noviembre 2026")
        self.emp.pay_day_from, self.emp.pay_day_to = 1, 5
        self.assertEqual(worked_month_text(D(2026, 11, 1), self.emp),
                         "mes trabajado Noviembre 2026 · se abona en Diciembre 2026 (días 1 al 5)")

    def test_salary_screens_show_worked_and_payment_month(self):
        self.emp.pay_day_from, self.emp.pay_day_to = 1, 5
        self.emp.save()
        adj = SalaryAdjustment.objects.create(employee=self.emp, effective_date=D(2026, 11, 1), new_salary=Decimal("1000"))
        self.assertEqual(adj.worked_month, "Noviembre 2026")
        self.assertEqual(adj.paid_in, "Diciembre 2026 (días 1 al 5)")
        self.client.force_login(self.admin)
        r = self.client.get(reverse("empleados:salario_list"))
        self.assertContains(r, "Mes trabajado")
        self.assertContains(r, "Diciembre 2026 (días 1 al 5)")
        r = self.client.get(reverse("empleados:empleado_detail", args=[self.emp.pk]))
        self.assertContains(r, "Se abona en")
        self.assertContains(r, "Noviembre 2026")
        r = self.client.get(reverse("empleados:salario_create"), {"empleado": self.emp.pk})
        self.assertContains(r, "mes trabajado")
        self.assertContains(r, "1 al 5")
        r = self.client.get(reverse("asistencia:resumen"), {"mes": 11, "anio": 2026})
        self.assertContains(r, "se abona en Diciembre 2026")
