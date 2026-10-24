import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from apps.core.crud import Column, HRCreateView, HRDeleteView, HRListView, HRUpdateView
from apps.core.formatting import format_number
from apps.core.models import AuditLog
from apps.core.modules import Level, Module
from apps.empleados.models import Department, Employee
from apps.reportes.documents import Document, Note, Section, Table, document_response, wants_document

from .forms import GoalFormSet, PlanForm
from .models import SCORE_MAX, GoalPlan, PeriodType, current_period_number, period_choices

TITLES = {
    PeriodType.MENSUAL: "Metas mensuales",
    PeriodType.TRIMESTRAL: "Metas trimestrales",
    PeriodType.SEMESTRAL: "Metas semestrales",
    PeriodType.ANUAL: "Metas anuales",
}


def _ptype(kwargs):
    ptype = kwargs.get("tipo")
    if ptype not in PeriodType.values:
        raise Http404
    return PeriodType(ptype)


def _score(v):
    return format_number(v, 2) if v is not None else "—"


class PlanList(HRListView):
    model = GoalPlan
    module = Module.EVALUACIONES
    url_prefix = "evaluaciones:plan"
    template_name = "evaluaciones/plan_list.html"
    printable = True
    search_fields = ["employee__first_name", "employee__last_name", "department__name"]
    columns = [
        Column("Período", "period_label"),
        Column("Metas de", "scope"),
        Column("Equipo / persona", "target_name", link=True),
        Column("Metas", "total_goals"),
        Column("Cumplidas", lambda p: f"{p.done_goals} de {p.total_goals}"),
        Column("Avance", lambda p: f"{p.progress} %"),
        Column("Evaluación promedio", lambda p: _score(p.average_score)),
        Column("Estado", "get_status_display", badge={"abierto": "info", "cerrado": "success"}, badge_key="status"),
    ]

    def dispatch(self, request, *args, **kwargs):
        self.ptype = _ptype(kwargs)
        self.title = TITLES[self.ptype]
        self.filters = [
            ("anio", "year", "Año", [(y, y) for y in range(datetime.date.today().year + 1, 2019, -1)]),
            ("periodo", "period_number", "Período", period_choices(self.ptype)),
            ("de", "scope", "Metas de", GoalPlan.Scope.choices),
            ("area", "department_id", "Equipo", lambda: [(d.pk, d.name) for d in Department.objects.all()]),
            ("persona", "employee_id", "Persona",
             lambda: [(e.pk, str(e)) for e in Employee.objects.exclude(status=Employee.Status.DESVINCULADO)]),
        ]
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return super().get_queryset().filter(period_type=self.ptype).select_related(
            "department", "employee").prefetch_related("goals")

    def print_footer(self, qs):
        plans = list(qs)
        total = sum(p.total_goals for p in plans)
        done = sum(p.done_goals for p in plans)
        return ["Total", f"{len(plans)} planes", "", total, f"{done} de {total}",
                f"{round(done * 100 / total) if total else 0} %", "", ""]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["ptype"] = self.ptype
        ctx["types"] = [(t, TITLES[t]) for t in PeriodType]
        if ctx.get("create_url"):
            ctx["create_url"] += f"?tipo={self.ptype}"
        ctx["create_label"] = "Nuevo plan de metas"
        return ctx


class PlanCreate(HRCreateView):
    model = GoalPlan
    form_class = PlanForm
    module = Module.EVALUACIONES
    url_prefix = "evaluaciones:plan"
    template_name = "evaluaciones/plan_form.html"
    title = "Nuevo plan de metas"

    def get_initial(self):
        ptype = self.request.GET.get("tipo", PeriodType.MENSUAL)
        if ptype not in PeriodType.values:
            ptype = PeriodType.MENSUAL
        initial = {"period_type": ptype, "year": datetime.date.today().year,
                   "period_number": current_period_number(ptype)}
        if self.request.GET.get("persona"):
            initial.update(scope=GoalPlan.Scope.PERSONAL, employee=self.request.GET["persona"])
        if self.request.GET.get("area"):
            initial.update(scope=GoalPlan.Scope.EQUIPO, department=self.request.GET["area"])
        return initial

    def get_success_url(self):
        return reverse("evaluaciones:plan_detail", args=[self.object.pk])


class PlanUpdate(HRUpdateView):
    model = GoalPlan
    form_class = PlanForm
    module = Module.EVALUACIONES
    url_prefix = "evaluaciones:plan"
    template_name = "evaluaciones/plan_form.html"
    title = "Editar datos del plan"

    def get_success_url(self):
        return reverse("evaluaciones:plan_detail", args=[self.object.pk])


class PlanDelete(HRDeleteView):
    model = GoalPlan
    module = Module.EVALUACIONES
    url_prefix = "evaluaciones:plan"

    def get_success_url(self):
        return reverse("evaluaciones:plan_list", args=[self.object.period_type])


def can_view_plan(user, plan):
    if user.can(Module.EVALUACIONES):
        return True
    own = getattr(user, "employee", None)
    if not own:
        return False
    return plan.employee_id == own.pk or (plan.department_id and plan.department_id == own.department_id) or (
        plan.employee and plan.employee.manager_id == own.pk)


def plan_document(plan):
    team = plan.scope == GoalPlan.Scope.EQUIPO
    goals = list(plan.goals.select_related("responsible"))
    headers = ["#", "Objetivo"] + (["Responsable"] if team else []) + ["Cumplido", "Evaluación", "Cómo lo cumplió",
                                                                         "Observaciones"]
    rows = [[i, g.objective] + ([g.responsible.full_name if g.responsible else ""] if team else [])
            + ["Sí" if g.done else "No", _score(g.score), g.how_achieved, g.observations]
            for i, g in enumerate(goals, 1)]
    footer = ["", "Total"] + ([""] if team else []) + [f"{plan.done_goals} de {plan.total_goals} ({plan.progress} %)",
                                                         f"Promedio {_score(plan.average_score)}", "", ""]
    doc = Document(
        title=f"{TITLES[PeriodType(plan.period_type)]} · {plan.target_name}",
        subtitle=[f"{plan.period_label} ({plan.start_date:%d/%m/%Y} al {plan.end_date:%d/%m/%Y}) · "
                  f"{plan.get_scope_display()} · Estado: {plan.get_status_display()}"
                  + (f" · Evaluador: {plan.evaluator}" if plan.evaluator else "")],
    )
    doc.add(Section("Metas"), Table(headers, rows, footer=footer if goals else None,
                                    empty_text="Todavía no se cargaron metas."))
    if plan.notes:
        doc.add(Note(f"Comentario general: {plan.notes}"))
    doc.add(Note(f"Evaluación numérica de 1 a {SCORE_MAX}. El promedio considera solo las metas evaluadas."))
    return doc


@login_required
def plan_detail(request, pk):
    plan = get_object_or_404(GoalPlan.objects.select_related("department", "employee"), pk=pk)
    if not can_view_plan(request.user, plan):
        raise PermissionDenied
    if wants_document(request):
        return document_response(request, plan_document(plan), f"metas_{plan.period_type}_{plan.pk}")
    can_edit = request.user.can(Module.EVALUACIONES, Level.EDITAR)
    if request.method == "POST":
        if not can_edit:
            raise PermissionDenied
        formset = GoalFormSet(request.POST, instance=plan, prefix="goals")
        if formset.is_valid():
            with transaction.atomic():
                goals = formset.save(commit=False)
                for obj in formset.deleted_objects:
                    obj.delete()
                for g in goals:
                    g.save()
                for i, form in enumerate(f for f in formset.forms if f.instance.pk and f not in formset.deleted_forms):
                    if form.instance.order != i:
                        form.instance.order = i
                        form.instance.save(update_fields=["order"])
            AuditLog.log(request.user, AuditLog.Action.UPDATE, plan, f"Metas actualizadas: {plan}")
            messages.success(request, "Metas guardadas.")
            return redirect("evaluaciones:plan_detail", pk=pk)
        messages.error(request, "Revisá las metas marcadas en rojo.")
    else:
        formset = GoalFormSet(instance=plan, prefix="goals")
    return render(request, "evaluaciones/plan_detail.html", {
        "plan": plan, "formset": formset, "can_edit": can_edit,
        "can_admin": request.user.can(Module.EVALUACIONES, Level.ADMINISTRAR),
        "team": plan.scope == GoalPlan.Scope.EQUIPO, "title": TITLES[PeriodType(plan.period_type)],
        "score_max": SCORE_MAX,
    })


@login_required
def plan_duplicate(request, pk):
    """Crea el plan del período siguiente con los mismos objetivos (sin evaluar)."""
    if request.method != "POST" or not request.user.can(Module.EVALUACIONES, Level.EDITAR):
        raise PermissionDenied
    plan = get_object_or_404(GoalPlan, pk=pk)
    year, number = plan.next_period()
    exists = GoalPlan.objects.filter(period_type=plan.period_type, year=year, period_number=number, scope=plan.scope,
                                     department=plan.department, employee=plan.employee).first()
    if exists:
        messages.warning(request, "Ya existe el plan del período siguiente.")
        return redirect("evaluaciones:plan_detail", pk=exists.pk)
    with transaction.atomic():
        new = GoalPlan.objects.create(period_type=plan.period_type, year=year, period_number=number, scope=plan.scope,
                                      department=plan.department, employee=plan.employee, evaluator=plan.evaluator,
                                      created_by=request.user)
        for g in plan.goals.all():
            new.goals.create(order=g.order, objective=g.objective, responsible=g.responsible)
    messages.success(request, f"Se creó el plan de {new.period_label} con {new.goals.count()} metas para evaluar.")
    return redirect("evaluaciones:plan_detail", pk=new.pk)


def plans_for_employee(employee):
    return GoalPlan.objects.filter(Q(employee=employee) | Q(department_id=employee.department_id, scope="equipo")
                                   if employee.department_id else Q(employee=employee)).prefetch_related("goals")
