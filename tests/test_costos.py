import datetime
from decimal import Decimal

from django.urls import reverse

from apps.empleados import ajustes
from apps.empleados.models import SalaryAdjustment, SalaryAdjustmentPlan

from .base import HRTestCase


def extras_data(rows, total=None, initial=0):
    data = {"extras-TOTAL_FORMS": str(total if total is not None else len(rows)), "extras-INITIAL_FORMS": str(initial),
            "extras-MIN_NUM_FORMS": "0", "extras-MAX_NUM_FORMS": "1000"}
    for i, row in enumerate(rows):
        for k, v in row.items():
            data[f"extras-{i}-{k}"] = v
    return data


class ExtraCostTests(HRTestCase):
    def setUp(self):
        self.client.force_login(self.admin)

    def base(self, **kw):
        return {"employee": self.emp.pk, "effective_date": "2026-09-01", "reason": "acuerdo", "new_salary": "1000000", **kw}

    def test_create_with_several_extras_and_gross(self):
        r = self.client.post(reverse("empleados:salario_create"), {
            **self.base(), **extras_data([{"concept": "Acuerdo", "amount": "100000"},
                                          {"concept": "Viáticos", "amount": "50000"},
                                          {"concept": "", "amount": ""}])})
        self.assertEqual(r.status_code, 302)
        adj = SalaryAdjustment.objects.get(employee=self.emp)
        self.assertEqual(adj.extra_costs.count(), 2)
        self.assertEqual(adj.extras_total, Decimal("150000"))
        self.assertEqual(adj.gross_salary, Decimal("1150000"))
        self.assertEqual(self.emp.current_gross_salary, Decimal("1150000"))

    def test_invalid_extra_row(self):
        r = self.client.post(reverse("empleados:salario_create"), {
            **self.base(), **extras_data([{"concept": "Sin importe", "amount": ""}])})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(SalaryAdjustment.objects.exists())

    def test_extras_carried_over_on_new_adjustment(self):
        prev = SalaryAdjustment.objects.create(employee=self.emp, effective_date=datetime.date(2026, 1, 1),
                                               new_salary=Decimal("900000"))
        prev.extra_costs.create(concept="Acuerdo", amount=Decimal("100000"))
        r = self.client.get(reverse("empleados:salario_create"), {"empleado": self.emp.pk})
        self.assertContains(r, 'value="Acuerdo"')
        self.assertContains(r, "Se copiaron los costos adicionales")
        # Se envía tal cual vino (sin modificar) y se guarda igual
        self.client.post(reverse("empleados:salario_create"), {
            **self.base(), **extras_data([{"concept": "Acuerdo", "amount": "100000.00"}])})
        new = self.emp.salary_adjustments.first()
        self.assertEqual(new.gross_salary, Decimal("1100000"))

    def test_update_remove_extra(self):
        adj = SalaryAdjustment.objects.create(employee=self.emp, effective_date=datetime.date(2026, 1, 1),
                                              new_salary=Decimal("900000"))
        c = adj.extra_costs.create(concept="Acuerdo", amount=Decimal("100000"))
        r = self.client.post(reverse("empleados:salario_update", args=[adj.pk]), {
            **self.base(effective_date="2026-01-01", new_salary="900000"),
            **extras_data([{"id": c.pk, "adjustment": adj.pk, "concept": "Acuerdo", "amount": "100000", "DELETE": "on"}],
                          initial=1)})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(adj.extra_costs.count(), 0)

    def test_bulk_and_scheduled_keep_extras(self):
        adj = SalaryAdjustment.objects.create(employee=self.emp, effective_date=datetime.date(2026, 1, 1),
                                              new_salary=Decimal("1000000"))
        adj.extra_costs.create(concept="Acuerdo", amount=Decimal("100000"))
        self.client.post(reverse("empleados:salario_masivo"), {
            "percent": "10", "effective_date": "2026-04-01", "reason": "paritaria", "confirmar": "1"})
        last = self.emp.salary_adjustments.first()
        self.assertEqual(last.new_salary, Decimal("1100000.00"))
        self.assertEqual(last.gross_salary, Decimal("1200000.00"))  # el % no afecta los costos adicionales

        SalaryAdjustmentPlan.objects.create(employee=self.emp, frequency_months=3, method="monto", amount=Decimal("50000"))
        row = ajustes.compute(self.emp)
        self.assertEqual(row.gross_new, Decimal("1250000.00"))
        applied = ajustes.apply(row, self.admin)
        self.assertEqual(applied.gross_salary, Decimal("1250000.00"))

    def test_screens_show_net_and_gross(self):
        adj = SalaryAdjustment.objects.create(employee=self.emp, effective_date=datetime.date(2026, 1, 1),
                                              new_salary=Decimal("1000000"))
        adj.extra_costs.create(concept="Acuerdo de permanencia", amount=Decimal("100000"))
        r = self.client.get(reverse("empleados:salario_list"))
        self.assertContains(r, "Total con adicionales")
        self.assertContains(r, "Salario base")
        self.assertContains(r, "$ 1.100.000,00")
        r = self.client.get(reverse("empleados:empleado_detail", args=[self.emp.pk]))
        self.assertContains(r, "Total con adicionales vigente")
        self.assertContains(r, "Salario base vigente")
        self.assertNotContains(r, "bruto")
        self.assertContains(r, "Acuerdo de permanencia")
        self.assertEqual(self.client.get(reverse("reportes:report", args=["masa-salarial"])).status_code, 200)
