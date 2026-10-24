import datetime
from unittest import mock

from django.conf import settings
from django.core import mail
from django.urls import reverse

from apps.empleados.models import Employee, SalaryAdjustment
from apps.licencias.models import LeaveRequest, LeaveType
from apps.licencias.services import generate_vacation_balances

from .base import HRTestCase


class AtomicRequestTests(HRTestCase):
    def test_setting_enabled(self):
        self.assertTrue(settings.DATABASES["default"]["ATOMIC_REQUESTS"])

    def test_failure_mid_operation_saves_nothing(self):
        """Alta de empleado + salario inicial: si falla el segundo paso, tampoco queda el empleado."""
        from apps.core.management.commands.datos_demo import make_cuil

        self.client.force_login(self.admin)
        data = {"file_number": "90", "first_name": "Parcial", "last_name": "Test", "dni": "28888888",
                "cuil": make_cuil(28888888), "nationality": "Argentina", "status": "activo", "hire_date": "2026-10-01",
                "contract_type": "indeterminado", "pay_type": "mensual", "weekly_hours": "45", "initial_salary": "1000"}
        with mock.patch.object(SalaryAdjustment.objects, "create", side_effect=RuntimeError("la base se cayó")):
            with self.assertRaises(RuntimeError):
                self.client.post(reverse("empleados:empleado_create"), data)
        self.assertFalse(Employee.objects.filter(file_number="90").exists())

    def test_duplicate_application_does_not_break_request(self):
        from apps.reclutamiento.models import Application, Candidate, JobOpening

        job = JobOpening.objects.create(title="X", description="x")
        cand = Candidate.objects.create(first_name="A", last_name="B", email="a@b.com")
        Application.objects.create(job=job, candidate=cand)
        self.client.force_login(self.admin)
        r = self.client.post(reverse("reclutamiento:postulacion_add"), {"job": job.pk, "candidate": cand.pk})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Application.objects.count(), 1)

    def test_email_sent_only_after_commit(self):
        self.emp.work_email = "juan@test.com"
        self.emp.save()
        generate_vacation_balances(2027)
        vac = LeaveType.objects.get(code="vacaciones")
        req = LeaveRequest.objects.create(employee=self.emp, leave_type=vac, start_date=datetime.date(2027, 2, 1),
                                          end_date=datetime.date(2027, 2, 7))
        self.client.force_login(self.admin)
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            self.client.post(reverse("licencias:solicitud_review", args=[req.pk]), {"accion": "aprobar"})
        self.assertEqual(len(callbacks), 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("aprobada", mail.outbox[0].subject)
