import datetime
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.empleados.models import Department
from apps.evaluaciones.models import Goal, GoalPlan, period_label

from .base import HRTestCase


def goals_data(rows, initial=0):
    data = {"goals-TOTAL_FORMS": str(len(rows)), "goals-INITIAL_FORMS": str(initial), "goals-MIN_NUM_FORMS": "0",
            "goals-MAX_NUM_FORMS": "1000"}
    for i, row in enumerate(rows):
        for k, v in row.items():
            data[f"goals-{i}-{k}"] = v
    return data


class GoalPlanTests(HRTestCase):
    def setUp(self):
        self.dept = Department.objects.create(name="Ventas")
        self.emp.department = self.dept
        self.emp.save()
        self.client.force_login(self.admin)

    def test_labels_and_dates(self):
        p = GoalPlan(period_type="trimestral", year=2026, period_number=4, scope="personal", employee=self.emp)
        self.assertEqual(p.period_label, "4.º trimestre 2026")
        self.assertEqual((p.start_date, p.end_date), (datetime.date(2026, 10, 1), datetime.date(2026, 12, 31)))
        self.assertEqual(period_label("semestral", 2026, 1), "1.er semestre 2026")
        self.assertEqual(period_label("mensual", 2026, 2), "Febrero 2026")
        self.assertEqual(GoalPlan(period_type="anual", year=2026, period_number=1).end_date, datetime.date(2026, 12, 31))

    def test_validation(self):
        with self.assertRaises(ValidationError):
            GoalPlan(period_type="trimestral", year=2026, period_number=5, scope="personal", employee=self.emp).full_clean()
        with self.assertRaises(ValidationError):
            GoalPlan(period_type="mensual", year=2026, period_number=1, scope="equipo").full_clean()
        GoalPlan.objects.create(period_type="mensual", year=2026, period_number=1, scope="personal", employee=self.emp)
        with self.assertRaises(ValidationError):
            GoalPlan(period_type="mensual", year=2026, period_number=1, scope="personal", employee=self.emp).full_clean()

    def test_full_flow(self):
        r = self.client.post(reverse("evaluaciones:plan_create") + "?tipo=semestral", {
            "period_type": "semestral", "year": 2026, "period_number": 2, "scope": "equipo", "department": self.dept.pk})
        self.assertEqual(r.status_code, 302)
        plan = GoalPlan.objects.get()
        url = reverse("evaluaciones:plan_detail", args=[plan.pk])
        self.assertContains(self.client.get(url), "Agregar meta")
        r = self.client.post(url, goals_data([
            {"objective": "Vender más", "responsible": self.emp.pk, "done": "on", "score": "9", "how_achieved": "Ofertas"},
            {"objective": "Capacitar al equipo", "score": "6.5", "observations": "Faltó un módulo"},
            {"objective": "", "score": ""},  # fila vacía: se ignora
        ]))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(plan.goals.count(), 2)
        self.assertEqual(plan.done_goals, 1)
        self.assertEqual(plan.progress, 50)
        self.assertEqual(plan.average_score, Decimal("7.75"))
        r = self.client.post(url, goals_data([{"objective": "X", "score": "11"}]))
        self.assertEqual(r.status_code, 200)  # evaluación fuera de rango

        g = plan.goals.first()
        self.client.post(url, goals_data([{"id": g.pk, "plan": plan.pk, "objective": g.objective, "DELETE": "on"}], initial=1))
        self.assertEqual(plan.goals.count(), 1)

        lst = self.client.get(reverse("evaluaciones:plan_list", args=["semestral"]))
        self.assertContains(lst, "Ventas")
        self.assertContains(lst, "50 %" if plan.progress == 50 else "0 %")
        self.assertEqual(self.client.get(url, {"formato": "pdf"})["Content-Type"], "application/pdf")
        self.assertContains(self.client.get(url, {"formato": "imprimir"}), "Cómo lo cumplió")

        self.client.post(reverse("evaluaciones:plan_duplicate", args=[plan.pk]))
        nxt = GoalPlan.objects.get(year=2027, period_number=1)
        self.assertEqual(nxt.goals.count(), 1)
        self.assertFalse(nxt.goals.first().done)

    def test_permissions_and_employee_view(self):
        plan = GoalPlan.objects.create(period_type="mensual", year=2026, period_number=10, scope="personal", employee=self.emp)
        Goal.objects.create(plan=plan, objective="Meta propia")
        other = GoalPlan.objects.create(period_type="mensual", year=2026, period_number=10, scope="personal",
                                        employee=self.other)
        self.client.force_login(self.emp_user)
        r = self.client.get(reverse("evaluaciones:plan_detail", args=[plan.pk]))
        self.assertContains(r, "Meta propia")
        self.assertNotContains(r, "Guardar metas")  # solo lectura
        self.assertEqual(self.client.post(reverse("evaluaciones:plan_detail", args=[plan.pk]), {}).status_code, 403)
        self.assertEqual(self.client.get(reverse("evaluaciones:plan_detail", args=[other.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse("evaluaciones:plan_list", args=["mensual"])).status_code, 403)
        self.assertContains(self.client.get(reverse("empleados:mi_legajo")), "Evaluaciones")
        self.client.force_login(self.boss_user)  # Líder de equipo: puede editar
        self.assertContains(self.client.get(reverse("evaluaciones:plan_detail", args=[plan.pk])), "Guardar metas")
