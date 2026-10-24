import datetime
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.core import home
from apps.empleados.completeness import missing_fields
from apps.empleados.models import SalaryAdjustment
from apps.licencias.models import LeaveRequest, LeaveType
from apps.pagos.models import FinalSettlement, SalaryAdvance, business_days_after

from .base import HRTestCase

TODAY = datetime.date.today()
D = datetime.date


class EmployeePaymentDataTests(HRTestCase):
    def test_transfer_requires_bank_and_cbu(self):
        self.emp.payment_method = "transferencia"
        with self.assertRaises(ValidationError) as cm:
            self.emp.full_clean()
        self.assertIn("cbu", cm.exception.message_dict)
        self.assertIn("bank", cm.exception.message_dict)

    def test_pay_window_validation_and_next_window(self):
        self.emp.pay_day_from, self.emp.pay_day_to = 10, 5
        with self.assertRaises(ValidationError):
            self.emp.full_clean()
        self.emp.pay_day_from, self.emp.pay_day_to = 1, 5
        self.assertEqual(self.emp.next_pay_window(D(2026, 10, 3)), (D(2026, 10, 1), D(2026, 10, 5)))
        self.assertEqual(self.emp.next_pay_window(D(2026, 10, 20)), (D(2026, 11, 1), D(2026, 11, 5)))
        self.emp.pay_day_from, self.emp.pay_day_to = 25, 31
        self.assertEqual(self.emp.next_pay_window(D(2026, 2, 3)), (D(2026, 2, 25), D(2026, 2, 28)))


class AdvanceTests(HRTestCase):
    def setUp(self):
        self.client.force_login(self.admin)

    def test_create_defaults_and_states(self):
        r = self.client.post(reverse("pagos:adelanto_create"), {
            "employee": self.emp.pk, "date": "2026-10-10", "amount": "50000", "reason": "Urgencia",
            "payment_method": "efectivo"})
        self.assertEqual(r.status_code, 302)
        adv = SalaryAdvance.objects.get()
        self.assertEqual(adv.discount_period, D(2026, 10, 1))
        self.assertEqual(adv.status, "pendiente_pago")
        self.client.post(reverse("pagos:adelanto_pagado", args=[adv.pk]))
        adv.refresh_from_db()
        self.assertEqual(adv.status, "a_descontar")
        self.client.post(reverse("pagos:adelanto_descontar"), {"period": "2026-10"})
        adv.refresh_from_db()
        self.assertEqual(adv.status, "descontado")
        self.assertIsNotNone(adv.discounted_on)

    def test_list_filters_pdf_and_reports(self):
        SalaryAdvance.objects.create(employee=self.emp, date=D(2026, 10, 1), amount=Decimal("1000"), reason="A",
                                     discount_period=D(2026, 10, 1))
        SalaryAdvance.objects.create(employee=self.other, date=D(2026, 10, 2), amount=Decimal("2000"), reason="B",
                                     paid_date=D(2026, 10, 2), discount_period=D(2026, 10, 1))
        r = self.client.get(reverse("pagos:adelanto_list"), {"estado": "a_descontar"})
        self.assertEqual([row["obj"].employee for row in r.context["rows"]], [self.other])
        self.assertEqual(self.client.get(reverse("pagos:adelanto_list"), {"formato": "pdf"})["Content-Type"],
                         "application/pdf")
        r = self.client.get(reverse("pagos:adelanto_informe"), {"desde": "2026-01-01", "hasta": "2026-12-31"})
        self.assertContains(r, "Informe general")
        self.assertContains(r, "$ 3.000,00")
        r = self.client.get(reverse("pagos:adelanto_informe"), {"empleado": self.emp.pk, "desde": "2026-01-01",
                                                                 "hasta": "2026-12-31"})
        self.assertContains(r, "Pendiente de pago (1)")
        self.assertEqual(self.client.get(reverse("pagos:adelanto_informe"), {"empleado": self.emp.pk, "formato": "pdf"})
                         .status_code, 200)

    def test_monthly_summary_includes_advances(self):
        SalaryAdvance.objects.create(employee=self.emp, date=D(2026, 10, 1), amount=Decimal("1234"), reason="A",
                                     paid_date=D(2026, 10, 1), discount_period=D(2026, 10, 1))
        r = self.client.get(reverse("asistencia:resumen"), {"mes": 10, "anio": 2026})
        self.assertContains(r, "$ 1.234,00")

    def test_employee_role_cannot_manage(self):
        self.client.force_login(self.emp_user)
        self.assertEqual(self.client.get(reverse("pagos:adelanto_list")).status_code, 403)


class SettlementTests(HRTestCase):
    def setUp(self):
        self.client.force_login(self.admin)

    def test_due_date_four_business_days(self):
        # Egreso viernes 03/07/2026 → 4 hábiles: lun 6, mar 7, mié 8, jue 9 (feriado) → vie 10 también es puente
        due = business_days_after(D(2026, 7, 3), 4)
        self.assertEqual(due, D(2026, 7, 13))

    def test_create_with_items_and_pending_advances(self):
        SalaryAdvance.objects.create(employee=self.emp, date=D(2026, 9, 1), amount=Decimal("100000"), reason="A",
                                     paid_date=D(2026, 9, 1), discount_period=D(2026, 9, 1))
        r = self.client.get(reverse("pagos:liquidacion_create"), {"empleado": self.emp.pk})
        self.assertContains(r, 'value="Adelantos de sueldo pendientes"')
        data = {"employee": self.emp.pk, "reason": "renuncia", "termination_date": "2026-10-15", "status": "confirmada",
                "payment_method": "transferencia", "descontar_adelantos": "1",
                "items-TOTAL_FORMS": "3", "items-INITIAL_FORMS": "0", "items-MIN_NUM_FORMS": "0",
                "items-MAX_NUM_FORMS": "1000",
                "items-0-concept": "Adelantos de sueldo pendientes", "items-0-kind": "descuento", "items-0-amount": "100000",
                "items-1-concept": "Vacaciones no gozadas", "items-1-kind": "haber", "items-1-amount": "500000",
                "items-2-concept": "SAC proporcional", "items-2-kind": "haber", "items-2-amount": "300000"}
        r = self.client.post(reverse("pagos:liquidacion_create"), data)
        self.assertEqual(r.status_code, 302)
        s = FinalSettlement.objects.get()
        self.assertEqual(s.total_earnings, Decimal("800000"))
        self.assertEqual(s.total_to_pay, Decimal("700000"))
        self.assertIsNotNone(s.due_date)
        self.assertEqual(SalaryAdvance.objects.get().status, "descontado")

        url = reverse("pagos:liquidacion_pago", args=[s.pk])
        self.client.post(url, {"date": "2026-10-20", "amount": "300000", "method": "transferencia"})
        s.refresh_from_db()
        self.assertEqual(s.status, "parcial")
        self.assertEqual(s.balance, Decimal("400000"))
        self.client.post(url, {"date": "2026-10-21", "amount": "400000", "method": "transferencia"})
        s.refresh_from_db()
        self.assertEqual(s.status, "pagada")
        self.client.post(reverse("pagos:liquidacion_estado", args=[s.pk]), {"status": "reclamo", "note": "Intimación"})
        s.refresh_from_db()
        self.assertIn("Intimación", s.notes)
        r = self.client.get(reverse("pagos:liquidacion_detail", args=[s.pk]), {"formato": "pdf"})
        self.assertEqual(r["Content-Type"], "application/pdf")
        self.assertContains(self.client.get(reverse("pagos:liquidacion_list")), "Pérez, Juan")


class HomeTests(HRTestCase):
    def test_agenda_news_requests_and_incomplete(self):
        self.emp.pay_day_from, self.emp.pay_day_to = 1, 5
        self.emp.save()
        SalaryAdvance.objects.create(employee=self.emp, date=TODAY, amount=Decimal("5000"), reason="X",
                                     discount_period=TODAY.replace(day=1))
        items = home.agenda(self.admin, TODAY)
        titles = " ".join(i.title for i in items)
        self.assertIn("Acreditación de sueldos", titles)
        self.assertIn("Pagar adelanto a Juan Pérez", titles)

        news = home.weekly_news(self.admin, TODAY)
        self.assertIn("Adelantos de sueldo", [g["title"] for g in news["groups"]])

        vac = LeaveType.objects.get(code="enfermedad")
        LeaveRequest.objects.create(employee=self.emp, leave_type=vac, start_date=TODAY, end_date=TODAY)
        req = home.staff_requests(self.admin, None)
        self.assertEqual(len(req["pending"]), 1)
        self.assertEqual(len(home.staff_requests(self.other_user, self.other)["pending"]), 0)

        found = dict((e.pk, [m[0] for m in missing]) for e, missing in missing_fields([self.emp]))
        self.assertIn("salario", found[self.emp.pk])
        self.assertIn("forma_pago", found[self.emp.pk])
        self.assertNotIn("acreditacion", found[self.emp.pk])
        SalaryAdjustment.objects.create(employee=self.emp, effective_date=TODAY, new_salary=Decimal(1))
        found = dict((e.pk, [m[0] for m in missing]) for e, missing in missing_fields([self.emp]))
        self.assertNotIn("salario", found[self.emp.pk])

        self.client.force_login(self.admin)
        r = self.client.get(reverse("dashboard"))
        for text in ["Fechas a tener en cuenta", "Novedades de la semana", "Sin confirmar", "Datos de legajo incompletos"]:
            self.assertContains(r, text)
        self.assertEqual(self.client.get(reverse("empleados:legajos_incompletos")).status_code, 200)


class PermissionMigrationTests(HRTestCase):
    def test_existing_roles_get_pagos_module(self):
        from apps.core.models import Role

        role = Role.objects.get(name="Liquidación de sueldos")
        self.assertEqual(role.level_for("pagos"), 3)
