import datetime
from decimal import Decimal

from django.urls import reverse

from apps.asistencia.models import Absence, Overtime, Tardiness
from apps.licencias.models import LeaveRequest, LeaveType

from .base import HRTestCase

D = datetime.date(2026, 3, 10)


class AttendanceDocumentsTests(HRTestCase):
    def setUp(self):
        Absence.objects.create(employee=self.emp, date=D, reason="personal", justified=True, notes="Turno médico")
        Absence.objects.create(employee=self.emp, date=D + datetime.timedelta(days=1), reason="sin_aviso")
        Tardiness.objects.create(employee=self.emp, date=D, arrival_time=datetime.time(9, 20))
        Tardiness.objects.create(employee=self.emp, date=D + datetime.timedelta(days=2), arrival_time=datetime.time(9, 10),
                                 justified=True)
        Overtime.objects.create(employee=self.emp, date=D, hours=Decimal("2"), status="aprobada", approved_by=self.admin)
        Overtime.objects.create(employee=self.emp, date=datetime.date(2026, 3, 15), hours=Decimal("3"))  # domingo
        LeaveRequest.objects.create(employee=self.emp, leave_type=LeaveType.objects.get(code="enfermedad"),
                                    start_date=D + datetime.timedelta(days=5), end_date=D + datetime.timedelta(days=7),
                                    status="aprobada")
        self.client.force_login(self.admin)

    def assert_pdf(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF"))

    def test_lists_pdf_and_print(self):
        for name in ["asistencia:inasistencia_list", "asistencia:tardanza_list", "asistencia:horaextra_list"]:
            url = reverse(name)
            self.assert_pdf(self.client.get(url, {"formato": "pdf", "anio": 2026}))
            r = self.client.get(url, {"formato": "imprimir", "empleado": self.emp.pk})
            self.assertContains(r, "window.print()")
            self.assertContains(r, "Total")
            self.assertContains(r, "Empleado: Pérez, Juan")
            self.assertContains(self.client.get(url), "formato=pdf")

    def test_print_footer_totals(self):
        r = self.client.get(reverse("asistencia:tardanza_list"), {"formato": "imprimir"})
        self.assertContains(r, "30 min")
        r = self.client.get(reverse("asistencia:horaextra_list"), {"formato": "imprimir"})
        self.assertContains(r, "5,00 h")
        self.assertContains(r, "Aprobadas: 2,00 h")

    def test_monthly_summary_pdf(self):
        url = reverse("asistencia:resumen")
        self.assert_pdf(self.client.get(url, {"mes": 3, "anio": 2026, "formato": "pdf"}))
        self.assertContains(self.client.get(url, {"mes": 3, "anio": 2026, "formato": "imprimir"}), "Marzo 2026")

    def test_employee_summary_subtotals_and_total(self):
        url = reverse("asistencia:resumen_empleado")
        r = self.client.get(url, {"empleado": self.emp.pk, "desde": "2026-01-01", "hasta": "2026-12-31"})
        self.assertContains(r, "Inasistencias (2)")
        self.assertContains(r, "1 justificadas")
        self.assertContains(r, "Llegadas tarde (2)")
        self.assertContains(r, "30 min")
        self.assertContains(r, "Horas extras (2)")
        self.assertContains(r, "1 aprobadas · 1 pendientes")
        self.assertContains(r, "3,0 días aprobados")
        self.assertContains(r, "Total general")
        doc = r.context["doc"]
        total_row = doc.blocks[-1].footer
        self.assertEqual(total_row[1], 7)  # 2 + 2 + 2 + 1
        self.assert_pdf(self.client.get(url, {"empleado": self.emp.pk, "formato": "pdf"}))
        self.assertContains(self.client.get(url, {"empleado": self.emp.pk, "formato": "imprimir"}), "Total general")

    def test_employee_summary_permissions(self):
        url = reverse("asistencia:resumen_empleado")
        self.client.force_login(self.emp_user)  # solo su propio resumen
        self.assertContains(self.client.get(url), "Inasistencias (2)")
        self.assertEqual(self.client.get(url, {"empleado": self.other.pk}).status_code, 404)
        self.client.force_login(self.boss_user)  # rol con acceso al módulo Asistencia
        self.assertEqual(self.client.get(url, {"empleado": self.emp.pk}).status_code, 200)
