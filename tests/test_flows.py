import datetime
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse

from apps.asistencia.models import Overtime, Tardiness
from apps.empleados.models import Employee, EmployeeDocument, SalaryAdjustment
from apps.licencias.models import LeaveBalance, LeaveRequest, LeaveType
from apps.licencias.services import generate_vacation_balances
from apps.reclutamiento.models import Application, Candidate, JobOpening

from .base import HRTestCase

FUTURE = datetime.date.today() + datetime.timedelta(days=60)


class PermissionTests(HRTestCase):
    def test_login_required(self):
        r = self.client.get(reverse("empleados:empleado_list"))
        self.assertEqual(r.status_code, 302)
        self.assertIn(reverse("login"), r["Location"])

    def test_employee_role_cannot_see_files(self):
        self.client.force_login(self.emp_user)
        self.assertEqual(self.client.get(reverse("empleados:empleado_list")).status_code, 403)
        self.assertEqual(self.client.get(reverse("empleados:salario_list")).status_code, 403)
        self.assertEqual(self.client.get(reverse("core:usuario_list")).status_code, 403)
        self.assertEqual(self.client.get(reverse("empleados:mi_legajo")).status_code, 200)
        self.assertEqual(self.client.get(reverse("empleados:directorio")).status_code, 200)

    def test_admin_sees_everything(self):
        self.client.force_login(self.admin)
        for name in ["empleados:empleado_list", "empleados:salario_list", "core:usuario_list", "reportes:index",
                     "licencias:saldo_list", "asistencia:resumen", "reclutamiento:busqueda_list"]:
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)

    def test_role_levels(self):
        self.assertTrue(self.boss_user.can("asistencia", 2))
        self.assertFalse(self.boss_user.can("salarios", 1))
        self.assertTrue(self.admin.can("salarios", 3))

    def test_non_superuser_cannot_edit_superuser(self):
        from apps.core.models import Role

        self.other_user.roles.add(Role.objects.get(name="Administrador RRHH"))
        self.client.force_login(self.other_user)
        r = self.client.get(reverse("core:usuario_update", args=[self.admin.pk]))
        self.assertEqual(r.status_code, 403)


class LeaveFlowTests(HRTestCase):
    def setUp(self):
        self.vac = LeaveType.objects.get(code="vacaciones")
        generate_vacation_balances(FUTURE.year)

    def test_self_service_request_and_manager_approval(self):
        self.client.force_login(self.emp_user)
        r = self.client.post(reverse("licencias:mis_licencias"), {
            "leave_type": self.vac.pk, "start_date": FUTURE, "end_date": FUTURE + datetime.timedelta(days=6),
        })
        self.assertEqual(r.status_code, 302, getattr(r, "context", {}) and r.context["form"].errors)
        req = LeaveRequest.objects.get(employee=self.emp)
        self.assertEqual(req.status, "pendiente")
        self.assertEqual(req.days, 7)

        # Otro empleado no puede aprobarla
        self.client.force_login(self.other_user)
        self.assertEqual(self.client.post(reverse("licencias:solicitud_review", args=[req.pk]), {"accion": "aprobar"}).status_code, 403)

        # La jefa directa sí
        self.client.force_login(self.boss_user)
        self.client.post(reverse("licencias:solicitud_review", args=[req.pk]), {"accion": "aprobar"})
        req.refresh_from_db()
        self.assertEqual(req.status, "aprobada")
        bal = LeaveBalance.objects.get(employee=self.emp, leave_type=self.vac, year=FUTURE.year)
        self.assertEqual(bal.available, bal.total - 7)

    def test_insufficient_balance(self):
        req = LeaveRequest(employee=self.emp, leave_type=self.vac, start_date=FUTURE,
                           end_date=FUTURE + datetime.timedelta(days=30))
        with self.assertRaisesMessage(Exception, "Saldo insuficiente"):
            req.full_clean()

    def test_overlap_rejected(self):
        LeaveRequest.objects.create(employee=self.emp, leave_type=self.vac, start_date=FUTURE,
                                    end_date=FUTURE + datetime.timedelta(days=6))
        req = LeaveRequest(employee=self.emp, leave_type=self.vac, start_date=FUTURE + datetime.timedelta(days=3),
                           end_date=FUTURE + datetime.timedelta(days=8))
        with self.assertRaisesMessage(Exception, "superpone"):
            req.full_clean()

    def test_days_per_event_limit(self):
        marriage = LeaveType.objects.get(code="matrimonio")
        req = LeaveRequest(employee=self.emp, leave_type=marriage, start_date=FUTURE,
                           end_date=FUTURE + datetime.timedelta(days=11))
        with self.assertRaisesMessage(Exception, "como máximo"):
            req.full_clean()

    def test_annual_cap_exam(self):
        exam = LeaveType.objects.get(code="examen")
        start = datetime.date(FUTURE.year, 1, 5)
        for i in range(5):
            LeaveRequest.objects.create(employee=self.emp, leave_type=exam, status="aprobada",
                                        start_date=start + datetime.timedelta(days=10 * i),
                                        end_date=start + datetime.timedelta(days=10 * i + 1))
        req = LeaveRequest(employee=self.emp, leave_type=exam, start_date=start + datetime.timedelta(days=100),
                           end_date=start + datetime.timedelta(days=100))
        with self.assertRaisesMessage(Exception, "tope anual"):
            req.full_clean()

    def test_carry_over_capped_to_one_third(self):
        generate_vacation_balances(FUTURE.year + 1, carry_over=True, cap_third=True)
        bal = LeaveBalance.objects.get(employee=self.emp, leave_type=self.vac, year=FUTURE.year + 1)
        prev = LeaveBalance.objects.get(employee=self.emp, leave_type=self.vac, year=FUTURE.year)
        self.assertEqual(bal.carried_over, (prev.entitled / 3).quantize(Decimal("0.1")))


class AttendanceTests(HRTestCase):
    def test_tardiness_minutes(self):
        t = Tardiness.objects.create(employee=self.emp, date=datetime.date(2026, 10, 20), arrival_time=datetime.time(9, 25))
        self.assertEqual(t.minutes_late, 25)

    def test_overtime_100_on_holiday(self):
        ot = Overtime.objects.create(employee=self.emp, date=datetime.date(2026, 7, 9), hours=Decimal(2))
        self.assertEqual(ot.rate, 100)

    def test_overtime_hours_from_times(self):
        ot = Overtime(employee=self.emp, date=datetime.date(2026, 10, 21), start_time=datetime.time(18),
                      end_time=datetime.time(20, 30))
        ot.full_clean()
        self.assertEqual(ot.hours, Decimal("2.50"))

    def test_summary_export(self):
        self.client.force_login(self.admin)
        r = self.client.get(reverse("asistencia:resumen"), {"mes": 10, "anio": 2026, "exportar": 1})
        self.assertEqual(r.status_code, 200)
        self.assertIn("spreadsheetml", r["Content-Type"])


@override_settings(MEDIA_ROOT="/tmp/hrms-test-media")
class DocumentTests(HRTestCase):
    def test_upload_and_access_control(self):
        self.client.force_login(self.admin)
        f = SimpleUploadedFile("dni.pdf", b"%PDF-1.4 test", content_type="application/pdf")
        r = self.client.post(reverse("empleados:documento_multi", args=[self.emp.pk]),
                             {"files": [f], "category": "dni", "visible_to_employee": "on"})
        self.assertEqual(r.status_code, 302)
        doc = EmployeeDocument.objects.get(employee=self.emp)
        url = doc.file.url
        self.assertEqual(self.client.get(url).status_code, 200)

        self.client.force_login(self.emp_user)  # dueño
        self.assertEqual(self.client.get(url).status_code, 200)
        self.client.force_login(self.other_user)  # otro empleado
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)

        doc.visible_to_employee = False
        doc.save()
        self.client.force_login(self.emp_user)
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_rejects_dangerous_extension(self):
        self.client.force_login(self.admin)
        f = SimpleUploadedFile("malo.html", b"<script>alert(1)</script>", content_type="text/html")
        self.client.post(reverse("empleados:documento_multi", args=[self.emp.pk]), {"files": [f], "category": "otro"})
        self.assertFalse(EmployeeDocument.objects.exists())


class SalaryTests(HRTestCase):
    def test_bulk_adjustment(self):
        for e in (self.emp, self.other):
            SalaryAdjustment.objects.create(employee=e, effective_date=datetime.date(2026, 1, 1), new_salary=Decimal("1000000"))
        self.client.force_login(self.admin)
        data = {"percent": "10", "effective_date": "2026-10-01", "reason": "paritaria"}
        r = self.client.post(reverse("empleados:salario_masivo"), data)
        self.assertEqual(len(r.context["preview"]), 2)
        self.assertEqual(SalaryAdjustment.objects.count(), 2)  # vista previa no guarda
        self.client.post(reverse("empleados:salario_masivo"), {**data, "confirmar": "1"})
        self.emp.refresh_from_db()
        self.assertEqual(self.emp.current_salary, Decimal("1100000.00"))
        adj = self.emp.salary_adjustments.first()
        self.assertEqual(adj.previous_salary, Decimal("1000000"))
        self.assertAlmostEqual(float(adj.variation_pct), 10.0)


class EmployeeTests(HRTestCase):
    def test_create_with_initial_salary_and_cuil_check(self):
        self.client.force_login(self.admin)
        base = {"file_number": "50", "first_name": "Ana", "last_name": "Test", "dni": "25555555",
                "nationality": "Argentina", "status": "activo", "hire_date": "2026-10-01",
                "contract_type": "indeterminado", "pay_type": "mensual", "weekly_hours": "45", "initial_salary": "1500000"}
        from apps.core.management.commands.datos_demo import make_cuil

        r = self.client.post(reverse("empleados:empleado_create"), {**base, "cuil": make_cuil(26666666)})
        self.assertEqual(r.status_code, 200)  # CUIL no corresponde al DNI
        r = self.client.post(reverse("empleados:empleado_create"), {**base, "cuil": make_cuil(25555555)})
        self.assertEqual(r.status_code, 302)
        e = Employee.objects.get(file_number="50")
        self.assertEqual(e.current_salary, Decimal("1500000"))

    def test_termination(self):
        self.client.force_login(self.admin)
        r = self.client.post(reverse("empleados:empleado_baja", args=[self.boss.pk]), {
            "termination_date": "2026-10-20", "termination_reason": "renuncia", "deactivate_user": "on"})
        self.assertEqual(r.status_code, 302)
        self.boss.refresh_from_db()
        self.boss_user.refresh_from_db()
        self.emp.refresh_from_db()
        self.assertEqual(self.boss.status, "baja")
        self.assertFalse(self.boss_user.is_active)
        self.assertIsNone(self.emp.manager)  # reasignado al jefe del jefe (ninguno)


@override_settings(MEDIA_ROOT="/tmp/hrms-test-media")
class RecruitmentTests(HRTestCase):
    def test_public_apply_and_hire(self):
        job = JobOpening.objects.create(title="Vendedor", description="x", status="abierta", published=True)
        cv = SimpleUploadedFile("cv.pdf", b"%PDF-1.4", content_type="application/pdf")
        r = self.client.post(reverse("empleos:detalle", args=[job.pk]), {
            "first_name": "Ana", "last_name": "Candidata", "email": "ana@test.com", "resume": cv, "consent": "on"})
        self.assertEqual(r.status_code, 200)
        app = Application.objects.get(job=job)
        self.assertEqual(app.candidate.source, Candidate.Source.PORTAL)

        self.client.force_login(self.admin)
        from apps.core.management.commands.datos_demo import make_cuil

        r = self.client.post(reverse("reclutamiento:postulacion_hire", args=[app.pk]), {
            "file_number": "77", "dni": "27777777", "cuil": make_cuil(27777777), "hire_date": "2026-11-02",
            "salary": "1200000"})
        self.assertEqual(r.status_code, 302)
        emp = Employee.objects.get(file_number="77")
        self.assertEqual(emp.status, "prueba")
        self.assertEqual(emp.current_salary, None)  # vigencia futura
        self.assertTrue(emp.documents.filter(category="cv").exists())
        app.refresh_from_db()
        self.assertEqual(app.stage, "contratado")

    def test_unpublished_job_not_public(self):
        job = JobOpening.objects.create(title="Interna", description="x", status="abierta", published=False)
        self.assertEqual(self.client.get(reverse("empleos:detalle", args=[job.pk])).status_code, 404)
