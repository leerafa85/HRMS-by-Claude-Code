import datetime
import os

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.forms import inlineformset_factory
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.generic import DetailView

from apps.core.crud import (
    Column,
    HRCreateView,
    HRDeleteView,
    HRListView,
    HRUpdateView,
    ModuleRequiredMixin,
)
from apps.core.dates import month_label, payment_month, worked_month_text
from apps.core.formatting import format_ars
from apps.core.models import AuditLog
from apps.core.modules import Level, Module
from apps.reportes.excel import excel_response

from . import ajustes
from .forms import (
    BulkPlanForm,
    BulkSalaryForm,
    DepartmentForm,
    DocumentForm,
    EmergencyContactForm,
    EmployeeForm,
    ExtraCostForm,
    ExtraCostFormSet,
    FamilyMemberForm,
    IPCForm,
    LocationForm,
    MultiDocumentUploadForm,
    PositionForm,
    SalaryAdjustmentForm,
    SalaryPlanForm,
    TerminationForm,
)
from .models import (
    Department,
    EmergencyContact,
    Employee,
    EmployeeDocument,
    FamilyMember,
    IPCValue,
    Location,
    Position,
    SalaryAdjustment,
    SalaryAdjustmentPlan,
    SalaryExtraCost,
)

STATUS_BADGES = {"activo": "success", "prueba": "info", "licencia": "warning", "baja": "secondary"}

# ---------------------------------------------------------------- Empleados


class EmployeeList(HRListView):
    model = Employee
    module = Module.EMPLEADOS
    url_prefix = "empleados:empleado"
    title = "Empleados"
    create_label = "Nuevo empleado"
    template_name = "empleados/employee_list.html"
    search_fields = ["first_name", "last_name", "file_number", "dni", "cuil", "work_email"]
    columns = [
        Column("Legajo", "file_number"),
        Column("Apellido y nombre", lambda e: str(e), link=True),
        Column("CUIL", "cuil"),
        Column("Área", "department"),
        Column("Puesto", "position"),
        Column("Ingreso", "hire_date"),
        Column("Antigüedad", "seniority_display"),
        Column("Estado", "status", badge=STATUS_BADGES),
    ]
    filters = [
        ("estado", "status", "Estado", Employee.Status.choices),
        ("area", "department_id", "Área", lambda: [(d.pk, d.name) for d in Department.objects.all()]),
        ("sede", "location_id", "Sede", lambda: [(s.pk, s.name) for s in Location.objects.all()]),
    ]

    def get_queryset(self):
        qs = super().get_queryset().select_related("department", "position")
        if not self.request.GET.get("estado"):
            qs = qs.exclude(status=Employee.Status.DESVINCULADO)
        return qs


@login_required
def employee_export(request):
    if not request.user.can(Module.EMPLEADOS):
        raise PermissionDenied
    can_salary = request.user.can(Module.SALARIOS)
    headers = ["Legajo", "Apellido", "Nombre", "DNI", "CUIL", "Nacimiento", "Email laboral", "Celular", "Área",
               "Puesto", "Sede", "Jefe directo", "Ingreso", "Antigüedad", "Modalidad", "CCT", "Categoría",
               "Obra social", "Estado", "Egreso"]
    if can_salary:
        from apps.core.dates import month_label

        worked = month_label(datetime.date.today())
        headers += [f"Salario base vigente (mes trabajado {worked})", "Costos adicionales",
                    f"Total con adicionales vigente (mes trabajado {worked})"]
    rows = []
    for e in Employee.objects.select_related("department", "position", "location", "manager"):
        row = [e.file_number, e.last_name, e.first_name, e.dni, e.cuil, e.birth_date, e.work_email, e.mobile,
               str(e.department or ""), str(e.position or ""), str(e.location or ""), str(e.manager or ""),
               e.hire_date, e.seniority_display, e.get_contract_type_display(), e.union_agreement, e.category,
               e.health_insurance, e.get_status_display(), e.termination_date]
        if can_salary:
            adj = e.current_adjustment
            row += [adj.new_salary, adj.extras_total, adj.gross_salary] if adj else [None, None, None]
        rows.append(row)
    return excel_response("empleados", "Empleados", headers, rows)


class EmployeeCreate(HRCreateView):
    model = Employee
    form_class = EmployeeForm
    module = Module.EMPLEADOS
    url_prefix = "empleados:empleado"
    template_name = "empleados/employee_form.html"
    title = "Alta de empleado"

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["can_salary"] = self.request.user.can(Module.SALARIOS, Level.EDITAR)
        return kw

    def form_valid(self, form):
        response = super().form_valid(form)
        salary = form.cleaned_data.get("initial_salary")
        if salary:
            SalaryAdjustment.objects.create(
                employee=self.object, effective_date=self.object.hire_date, new_salary=salary,
                reason=SalaryAdjustment.Reason.INGRESO, created_by=self.request.user,
            )
        return response


class EmployeeUpdate(HRUpdateView):
    model = Employee
    form_class = EmployeeForm
    module = Module.EMPLEADOS
    url_prefix = "empleados:empleado"
    template_name = "empleados/employee_form.html"


class EmployeeDelete(HRDeleteView):
    model = Employee
    module = Module.EMPLEADOS
    url_prefix = "empleados:empleado"


def employee_context(employee, user, self_view=False):
    """Datos para la ficha del legajo, filtrados según los permisos del usuario."""
    from apps.licencias.models import LeaveBalance

    own = getattr(user, "employee", None)
    is_self = bool(own and own.pk == employee.pk)
    is_manager = bool(own and employee.manager_id == own.pk)
    can = {
        "salary": user.can(Module.SALARIOS) or is_self,
        "documents": user.can(Module.DOCUMENTOS) or is_self,
        "documents_edit": user.can(Module.DOCUMENTOS, Level.EDITAR),
        "leave": user.can(Module.LICENCIAS) or is_self or is_manager,
        "attendance": user.can(Module.ASISTENCIA) or is_self or is_manager,
        "edit": user.can(Module.EMPLEADOS, Level.EDITAR),
        "admin": user.can(Module.EMPLEADOS, Level.ADMINISTRAR),
        "salary_edit": user.can(Module.SALARIOS, Level.EDITAR),
        "onboarding": user.can(Module.ONBOARDING),
        "evaluations": user.can(Module.EVALUACIONES) or is_self or is_manager,
        "evaluations_edit": user.can(Module.EVALUACIONES, Level.EDITAR),
        "payments": user.can(Module.PAGOS) or is_self,
        "payments_edit": user.can(Module.PAGOS, Level.EDITAR),
        "sensitive": user.can(Module.EMPLEADOS) or is_self,
    }
    ctx = {"employee": employee, "perm": can, "is_self": is_self, "self_view": self_view, "today": datetime.date.today()}
    if can["edit"] and not self_view:
        from .completeness import missing_fields

        found = missing_fields([employee])
        ctx["missing"] = found[0][1] if found else []
    if can["documents"]:
        docs = employee.documents.all()
        if not user.can(Module.DOCUMENTOS):
            docs = docs.filter(visible_to_employee=True)
        ctx["documents"] = docs
        ctx["upload_form"] = MultiDocumentUploadForm() if can["documents_edit"] else None
    if can["salary"]:
        ctx["salaries"] = employee.salary_adjustments.prefetch_related("extra_costs")
        ctx["salary_row"] = ajustes.compute(employee)
    if can["leave"]:
        ctx["balances"] = LeaveBalance.objects.filter(employee=employee).select_related("leave_type").order_by("-year")
        ctx["leave_requests"] = employee.leave_requests.select_related("leave_type")[:20]
    if can["attendance"]:
        year_start = datetime.date(datetime.date.today().year, 1, 1)
        ctx["absences"] = employee.absences.filter(date__gte=year_start)
        ctx["tardies"] = employee.tardies.filter(date__gte=year_start)
        ctx["overtimes"] = employee.overtimes.filter(date__gte=year_start)
    if can["payments"]:
        from apps.pagos.models import SalaryAdvance

        ctx["advances"] = employee.advances.all()[:24]
        ctx["advances_pending"] = SalaryAdvance.total(SalaryAdvance.pending_discount(employee=employee))
        ctx["settlements"] = employee.settlements.prefetch_related("items", "payments") if user.can(Module.PAGOS) else []
    if can["evaluations"]:
        from apps.evaluaciones.views import plans_for_employee

        ctx["goal_plans"] = plans_for_employee(employee).select_related("department", "employee")[:30]
    if can["onboarding"]:
        ctx["checklists"] = employee.checklists.prefetch_related("tasks")
    return ctx


class EmployeeDetail(ModuleRequiredMixin, DetailView):
    model = Employee
    module = Module.EMPLEADOS
    template_name = "empleados/employee_detail.html"

    def get_queryset(self):
        return super().get_queryset().select_related("department", "position", "location", "manager", "user")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(employee_context(self.object, self.request.user))
        return ctx


@login_required
def my_profile(request):
    employee = getattr(request.user, "employee", None)
    if not employee:
        messages.info(request, "Tu usuario no está vinculado a un legajo. Pedile a RRHH que lo vincule.")
        return redirect("dashboard")
    ctx = employee_context(employee, request.user, self_view=True)
    return render(request, "empleados/employee_detail.html", ctx)


@login_required
def team_member(request, pk):
    """Ficha reducida de un colaborador para su jefe directo."""
    own = getattr(request.user, "employee", None)
    employee = get_object_or_404(Employee, pk=pk)
    if request.user.can(Module.EMPLEADOS):
        return redirect("empleados:empleado_detail", pk=pk)
    if not own or employee.manager_id != own.pk:
        raise PermissionDenied
    return render(request, "empleados/employee_detail.html", employee_context(employee, request.user))


@login_required
def my_team(request):
    own = getattr(request.user, "employee", None)
    if not own:
        raise PermissionDenied
    from apps.licencias.models import LeaveRequest

    team = own.reports.exclude(status=Employee.Status.DESVINCULADO).select_related("position", "department")
    today = datetime.date.today()
    pending = LeaveRequest.objects.filter(employee__in=team, status=LeaveRequest.Status.PENDIENTE).select_related(
        "employee", "leave_type"
    )
    upcoming = LeaveRequest.objects.filter(
        employee__in=team, status=LeaveRequest.Status.APROBADA, end_date__gte=today
    ).select_related("employee", "leave_type").order_by("start_date")[:20]
    return render(request, "empleados/my_team.html", {"team": team, "pending": pending, "upcoming": upcoming})


@login_required
def employee_terminate(request, pk):
    if not request.user.can(Module.EMPLEADOS, Level.ADMINISTRAR):
        raise PermissionDenied
    employee = get_object_or_404(Employee, pk=pk)
    form = TerminationForm(request.POST or None, initial={"termination_date": datetime.date.today()})
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            employee.termination_date = form.cleaned_data["termination_date"]
            employee.termination_reason = form.cleaned_data["termination_reason"]
            employee.termination_notes = form.cleaned_data["termination_notes"]
            employee.status = Employee.Status.DESVINCULADO
            employee.save()
            if form.cleaned_data["deactivate_user"] and employee.user:
                employee.user.is_active = False
                employee.user.save(update_fields=["is_active"])
            Employee.objects.filter(manager=employee).update(manager=employee.manager)
            template = form.cleaned_data.get("offboarding_template")
            if template:
                from apps.onboarding.models import EmployeeChecklist

                EmployeeChecklist.from_template(template, employee, employee.termination_date, request.user)
        AuditLog.log(request.user, AuditLog.Action.UPDATE, employee, f"Baja de {employee}")
        messages.success(request, f"{employee.full_name} fue dado/a de baja.")
        return redirect("empleados:empleado_detail", pk=pk)
    return render(request, "empleados/terminate.html", {
        "form": form, "employee": employee, "title": f"Baja de {employee.full_name}",
        "cancel_url": reverse("empleados:empleado_detail", args=[pk]), "submit_label": "Registrar baja",
    })


@login_required
def employee_reactivate(request, pk):
    if not request.user.can(Module.EMPLEADOS, Level.ADMINISTRAR) or request.method != "POST":
        raise PermissionDenied
    employee = get_object_or_404(Employee, pk=pk)
    employee.status = Employee.Status.ACTIVO
    employee.termination_date = None
    employee.termination_reason = ""
    employee.save()
    AuditLog.log(request.user, AuditLog.Action.UPDATE, employee, f"Reingreso de {employee}")
    messages.success(request, "Empleado reactivado. Revisá la fecha de ingreso y antigüedad reconocida.")
    return redirect("empleados:empleado_update", pk=pk)


@login_required
def directory(request):
    q = request.GET.get("q", "").strip()
    qs = Employee.objects.exclude(status=Employee.Status.DESVINCULADO).select_related("department", "position", "location")
    if q:
        qs = qs.filter(
            Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(department__name__icontains=q)
            | Q(position__name__icontains=q)
        )
    dept = request.GET.get("area")
    if dept:
        qs = qs.filter(department_id=dept)
    return render(request, "empleados/directory.html", {
        "employees": qs, "q": q, "departments": Department.objects.all(), "area": dept,
    })


@login_required
def org_chart(request):
    active = list(
        Employee.objects.exclude(status=Employee.Status.DESVINCULADO).select_related("position", "department")
    )
    by_manager = {}
    ids = {e.pk for e in active}
    for e in active:
        key = e.manager_id if e.manager_id in ids else None
        by_manager.setdefault(key, []).append(e)

    def build(manager_id, depth=0):
        if depth > 20:
            return []
        return [{"employee": e, "children": build(e.pk, depth + 1)} for e in by_manager.get(manager_id, [])]

    return render(request, "empleados/org_chart.html", {"tree": build(None)})


# ---------------------------------------------------------------- Sub-registros del legajo


def _can_edit_employee(user):
    if not user.can(Module.EMPLEADOS, Level.EDITAR):
        raise PermissionDenied


def _subrecord_view(request, employee_pk, form_class, model, pk=None, title=""):
    _can_edit_employee(request.user)
    employee = get_object_or_404(Employee, pk=employee_pk)
    instance = get_object_or_404(model, pk=pk, employee=employee) if pk else None
    form = form_class(request.POST or None, instance=instance)
    if request.method == "POST":
        if "eliminar" in request.POST and instance:
            instance.delete()
            messages.success(request, "Registro eliminado.")
            return redirect(reverse("empleados:empleado_detail", args=[employee.pk]) + "#familia")
        if form.is_valid():
            obj = form.save(commit=False)
            obj.employee = employee
            obj.save()
            AuditLog.log(request.user, AuditLog.Action.UPDATE, employee, f"{title}: {obj}")
            messages.success(request, "Datos guardados.")
            return redirect(reverse("empleados:empleado_detail", args=[employee.pk]) + "#familia")
    return render(request, "crud/form.html", {
        "form": form, "title": f"{title} · {employee.full_name}",
        "cancel_url": reverse("empleados:empleado_detail", args=[employee.pk]),
        "delete_inline": bool(instance),
    })


@login_required
def family_member_edit(request, employee_pk, pk=None):
    return _subrecord_view(request, employee_pk, FamilyMemberForm, FamilyMember, pk, "Grupo familiar")


@login_required
def emergency_contact_edit(request, employee_pk, pk=None):
    return _subrecord_view(request, employee_pk, EmergencyContactForm, EmergencyContact, pk, "Contacto de emergencia")


# ---------------------------------------------------------------- Documentos


class DocumentList(HRListView):
    model = EmployeeDocument
    module = Module.DOCUMENTOS
    url_prefix = "empleados:documento"
    title = "Documentos de legajos"
    create_label = "Subir documento"
    template_name = "empleados/document_list.html"
    columns = [
        Column("Empleado", "employee"),
        Column("Documento", "title"),
        Column("Categoría", "category"),
        Column("Vencimiento", "expiry_date"),
        Column("Visible al empleado", "visible_to_employee"),
        Column("Cargado", "created_at"),
        Column("Por", "created_by"),
    ]
    search_fields = ["title", "employee__first_name", "employee__last_name", "employee__file_number"]
    filters = [
        ("categoria", "category", "Categoría", EmployeeDocument.Category.choices),
        ("empleado", "employee_id", "Empleado", lambda: [(e.pk, str(e)) for e in Employee.objects.all()]),
    ]

    def get_queryset(self):
        qs = super().get_queryset().select_related("employee", "created_by")
        if self.request.GET.get("vencimiento") == "1":
            qs = qs.filter(expiry_date__lte=datetime.date.today() + datetime.timedelta(days=30))
        return qs


class DocumentCreate(HRCreateView):
    model = EmployeeDocument
    form_class = DocumentForm
    module = Module.DOCUMENTOS
    url_prefix = "empleados:documento"
    title = "Subir documento"

    def get_initial(self):
        return {"employee": self.request.GET.get("empleado")}

    def get_success_url(self):
        return reverse("empleados:empleado_detail", args=[self.object.employee_id]) + "#documentos"


class DocumentUpdate(HRUpdateView):
    model = EmployeeDocument
    form_class = DocumentForm
    module = Module.DOCUMENTOS
    url_prefix = "empleados:documento"

    def get_success_url(self):
        return reverse("empleados:empleado_detail", args=[self.object.employee_id]) + "#documentos"


class DocumentDelete(HRDeleteView):
    model = EmployeeDocument
    module = Module.DOCUMENTOS
    url_prefix = "empleados:documento"

    def form_valid(self, form):
        self.object = self.get_object()
        self.success_url = reverse("empleados:empleado_detail", args=[self.object.employee_id]) + "#documentos"
        from apps.reclutamiento.models import Candidate

        name = self.object.file.name
        response = super().form_valid(form)
        if not Candidate.objects.filter(resume=name).exists() and not EmployeeDocument.objects.filter(file=name).exists():
            self.object.file.storage.delete(name)
        return response


@login_required
def document_multi_upload(request, employee_pk):
    if not request.user.can(Module.DOCUMENTOS, Level.EDITAR) or request.method != "POST":
        raise PermissionDenied
    employee = get_object_or_404(Employee, pk=employee_pk)
    form = MultiDocumentUploadForm(request.POST, request.FILES)
    if form.is_valid():
        for f in form.cleaned_data["files"]:
            doc = EmployeeDocument.objects.create(
                employee=employee,
                category=form.cleaned_data["category"],
                title=os.path.splitext(f.name)[0][:150],
                file=f,
                expiry_date=form.cleaned_data["expiry_date"],
                visible_to_employee=form.cleaned_data["visible_to_employee"],
                created_by=request.user,
            )
            AuditLog.log(request.user, AuditLog.Action.CREATE, doc)
        messages.success(request, f"Se subieron {len(form.cleaned_data['files'])} documento(s).")
    else:
        for errs in form.errors.values():
            for e in errs:
                messages.error(request, e)
    return redirect(reverse("empleados:empleado_detail", args=[employee.pk]) + "#documentos")


# ---------------------------------------------------------------- Salarios


class SalaryList(HRListView):
    model = SalaryAdjustment
    module = Module.SALARIOS
    url_prefix = "empleados:salario"
    title = "Ajustes salariales"
    create_label = "Nuevo ajuste"
    search_fields = ["employee__first_name", "employee__last_name", "employee__file_number"]
    extra_actions = [("Ajuste masivo / paritaria", "empleados:salario_masivo", "people-fill", Level.ADMINISTRAR)]
    columns = [
        Column("Empleado", "employee", link=True),
        Column("Vigencia desde", "effective_date"),
        Column("Mes trabajado", "worked_month"),
        Column("Se abona en", "paid_in"),
        Column("Base anterior", "previous_salary", kind="money"),
        Column("Salario base", "new_salary", kind="money"),
        Column("Costos adicionales", lambda a: "; ".join(f"{c.concept}: {format_ars(c.amount)}" for c in a.extra_costs.all()) or "—"),
        Column("Total con adicionales", "gross_salary", kind="money"),
        Column("Variación %", lambda a: f"{a.variation_pct:.2f} %".replace(".", ",") if a.variation_pct is not None else "—"),
        Column("Motivo", "reason"),
        Column("Registrado por", "created_by"),
    ]
    filters = [
        ("motivo", "reason", "Motivo", SalaryAdjustment.Reason.choices),
        ("empleado", "employee_id", "Empleado", lambda: [(e.pk, str(e)) for e in Employee.objects.all()]),
    ]

    def get_queryset(self):
        return super().get_queryset().select_related("employee", "created_by").prefetch_related("extra_costs")


class _SalaryFormMixin:
    """Formulario de salario base + costos adicionales (uno o varios)."""

    model = SalaryAdjustment
    form_class = SalaryAdjustmentForm
    module = Module.SALARIOS
    url_prefix = "empleados:salario"
    template_name = "empleados/salary_form.html"

    def get_success_url(self):
        nxt = self.request.GET.get("next", "")
        if nxt.startswith("/") and not nxt.startswith("//"):
            return nxt
        return self.url_for("list")

    def previous_extras(self):
        return []

    def get_formset(self):
        instance = self.object or SalaryAdjustment()
        if self.request.method == "POST":
            return ExtraCostFormSet(self.request.POST, instance=instance, prefix="extras")
        initial = self.previous_extras()
        factory = inlineformset_factory(SalaryAdjustment, SalaryExtraCost, form=ExtraCostForm,
                                        formset=ExtraCostFormSet, extra=len(initial), can_delete=True)
        return factory(instance=instance, prefix="extras", initial=initial)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.setdefault("formset", self.get_formset())
        ctx["carried_over"] = self.request.method != "POST" and bool(self.previous_extras())
        emp = self.object.employee if self.object else Employee.objects.filter(
            pk=self.request.GET.get("empleado") or 0).first()
        ctx["employee_window"] = f"{emp.pay_day_from} al {emp.pay_day_to}" if emp and emp.pay_day_from else ""
        return ctx

    def form_valid(self, form):
        formset = ExtraCostFormSet(self.request.POST, instance=form.instance, prefix="extras")
        if not formset.is_valid():
            return self.render_to_response(self.get_context_data(form=form, formset=formset))
        with transaction.atomic():
            response = super().form_valid(form)
            formset.instance = self.object
            formset.save()
        return response


class SalaryCreate(_SalaryFormMixin, HRCreateView):
    title = "Nuevo salario / ajuste salarial"

    def get_initial(self):
        return {"employee": self.request.GET.get("empleado"), "effective_date": datetime.date.today().replace(day=1)}

    def previous_extras(self):
        """Al crear un ajuste se proponen los costos adicionales del registro anterior del empleado."""
        emp_id = self.request.GET.get("empleado", "")
        if not emp_id.isdigit():
            return []
        last = SalaryAdjustment.objects.filter(employee_id=emp_id).order_by("-effective_date", "-id").first()
        return [{"concept": c.concept, "amount": c.amount} for c in last.extra_costs.all()] if last else []


class SalaryUpdate(_SalaryFormMixin, HRUpdateView):
    title = "Editar salario / ajuste salarial"


class SalaryDelete(HRDeleteView):
    model = SalaryAdjustment
    module = Module.SALARIOS
    url_prefix = "empleados:salario"


@login_required
def salary_bulk(request):
    if not request.user.can(Module.SALARIOS, Level.ADMINISTRAR):
        raise PermissionDenied
    form = BulkSalaryForm(request.POST or None, request.FILES or None)
    preview = []
    if request.method == "POST" and form.is_valid():
        from decimal import Decimal

        data = form.cleaned_data
        qs = Employee.objects.exclude(status=Employee.Status.DESVINCULADO)
        if data["department"]:
            qs = qs.filter(department=data["department"])
        if data["union_agreement"]:
            qs = qs.filter(union_agreement__iexact=data["union_agreement"].strip())
        factor = 1 + data["percent"] / Decimal(100)
        for e in qs:
            base = e.current_adjustment
            if base:
                current = base.new_salary
                new = (current * factor).quantize(Decimal("0.01"))
                extras = base.extras_total
                preview.append((e, current, new, extras, new + extras, base))
        if "confirmar" in request.POST:
            with transaction.atomic():
                for e, current, new, _extras, _gross, base in preview:
                    adj = SalaryAdjustment(
                        employee=e, effective_date=data["effective_date"], previous_salary=current, new_salary=new,
                        reason=data["reason"], notes=data["notes"] or f"Ajuste masivo {data['percent']} %",
                        created_by=request.user,
                    )
                    if data["attachment"]:
                        adj.attachment = data["attachment"]
                    adj.save()
                    adj.copy_extra_costs_from(base)
            AuditLog.objects.create(
                user=request.user, action=AuditLog.Action.CREATE, model="ajuste salarial",
                description=f"Ajuste masivo {data['percent']} % a {len(preview)} empleados",
            )
            messages.success(request, f"Se registró el ajuste para {len(preview)} empleados.")
            return redirect("empleados:salario_list")
    return render(request, "empleados/salary_bulk.html", {"form": form, "preview": preview})


# ---------------------------------------------------------------- Configuración (áreas, puestos, sedes)


def _simple_crud(model_cls, form_cls, prefix, title, columns, search):
    attrs = dict(model=model_cls, module=Module.CONFIGURACION, url_prefix=prefix)

    L = type("L", (HRListView,), {**attrs, "title": title, "columns": columns, "search_fields": search})
    C = type("C", (HRCreateView,), {**attrs, "form_class": form_cls, "get_success_url": lambda s: s.url_for("list")})
    U = type("U", (HRUpdateView,), {**attrs, "form_class": form_cls, "get_success_url": lambda s: s.url_for("list")})
    D = type("D", (HRDeleteView,), attrs)
    return L, C, U, D


DepartmentList, DepartmentCreate, DepartmentUpdate, DepartmentDelete = _simple_crud(
    Department, DepartmentForm, "empleados:area", "Áreas / departamentos",
    [Column("Área", "name"), Column("Depende de", "parent"), Column("Responsable", "head"),
     Column("Centro de costo", "cost_center"), Column("Empleados", lambda d: d.employees.exclude(status="baja").count())],
    ["name"],
)
PositionList, PositionCreate, PositionUpdate, PositionDelete = _simple_crud(
    Position, PositionForm, "empleados:puesto", "Puestos",
    [Column("Puesto", "name"), Column("Área", "department"),
     Column("Empleados", lambda p: p.employees.exclude(status="baja").count())],
    ["name"],
)
LocationList, LocationCreate, LocationUpdate, LocationDelete = _simple_crud(
    Location, LocationForm, "empleados:sede", "Sucursales / sedes",
    [Column("Sede", "name"), Column("Domicilio", "address"), Column("Localidad", "city"), Column("Provincia", "province")],
    ["name", "city"],
)


def vcard(request, pk):
    """Descarga de contacto (vCard) desde el directorio."""
    if not request.user.is_authenticated:
        raise PermissionDenied
    e = get_object_or_404(Employee, pk=pk)
    body = (
        "BEGIN:VCARD\nVERSION:3.0\n"
        f"N:{e.last_name};{e.first_name}\nFN:{e.full_name}\n"
        f"TITLE:{e.position or ''}\nEMAIL;TYPE=work:{e.work_email}\nEND:VCARD\n"
    )
    resp = HttpResponse(body, content_type="text/vcard")
    resp["Content-Disposition"] = f'attachment; filename="{e.file_number}.vcf"'
    return resp


# ---------------------------------------------------------------- Esquemas de ajuste y próximos ajustes


@login_required
def salary_plan_edit(request, employee_pk):
    if not request.user.can(Module.SALARIOS, Level.EDITAR):
        raise PermissionDenied
    employee = get_object_or_404(Employee, pk=employee_pk)
    plan = getattr(employee, "salary_plan", None) or SalaryAdjustmentPlan(employee=employee)
    form = SalaryPlanForm(request.POST or None, instance=plan)
    if request.method == "POST":
        if "eliminar" in request.POST and plan.pk:
            plan.delete()
            AuditLog.log(request.user, AuditLog.Action.DELETE, employee, f"Esquema de ajuste eliminado: {employee}")
            messages.success(request, "Esquema de ajuste eliminado.")
            return redirect(reverse("empleados:empleado_detail", args=[employee.pk]) + "#salario")
        if form.is_valid():
            plan = form.save()
            AuditLog.log(request.user, AuditLog.Action.UPDATE, employee, f"Esquema de ajuste: {plan.summary}")
            nxt_date = plan.next_date()
            messages.success(request, f"Esquema guardado. Próximo ajuste: {nxt_date:%d/%m/%Y} ({worked_month_text(nxt_date)}).")
            nxt = request.GET.get("next", "")
            if nxt.startswith("/") and not nxt.startswith("//"):
                return redirect(nxt)
            return redirect(reverse("empleados:empleado_detail", args=[employee.pk]) + "#salario")
    return render(request, "empleados/salary_plan_form.html", {
        "form": form, "employee": employee, "plan": plan,
        "title": f"Esquema de ajuste salarial · {employee.full_name}",
        "cancel_url": reverse("empleados:empleado_detail", args=[employee.pk]) + "#salario",
        "delete_inline": bool(plan.pk),
    })


@login_required
def salary_plan_bulk(request):
    if not request.user.can(Module.SALARIOS, Level.ADMINISTRAR):
        raise PermissionDenied
    form = BulkPlanForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        qs = Employee.objects.exclude(status=Employee.Status.DESVINCULADO)
        if d["department"]:
            qs = qs.filter(department=d["department"])
        if d["union_agreement"]:
            qs = qs.filter(union_agreement__iexact=d["union_agreement"].strip())
        if d["only_without_plan"]:
            qs = qs.filter(salary_plan__isnull=True)
        values = {f: d[f] for f in SalaryPlanForm.Meta.fields}
        count = 0
        with transaction.atomic():
            for e in qs:
                SalaryAdjustmentPlan.objects.update_or_create(employee=e, defaults=values)
                count += 1
        AuditLog.objects.create(user=request.user, action=AuditLog.Action.UPDATE, model="esquema de ajuste salarial",
                                description=f"Esquema asignado masivamente a {count} empleados")
        messages.success(request, f"Esquema asignado a {count} empleado(s).")
        return redirect("empleados:proximos_ajustes")
    return render(request, "empleados/salary_plan_form.html", {
        "form": form, "title": "Asignar esquema de ajuste a varios empleados", "bulk": True,
        "cancel_url": reverse("empleados:proximos_ajustes"),
    })


UPCOMING_STATUS = {
    "vencido": ("Vencido", "danger"),
    "proximo": ("Próximo", "warning"),
    "programado": ("Programado", "success"),
    "sin_salario": ("Sin salario cargado", "secondary"),
    "sin_esquema": ("Sin esquema", "light"),
}


@login_required
def upcoming_adjustments(request):
    if not request.user.can(Module.SALARIOS):
        raise PermissionDenied
    employees = Employee.objects.all()
    area = request.GET.get("area", "")
    if area:
        employees = employees.filter(department_id=area)
    rows = ajustes.upcoming(employees)
    status = request.GET.get("estado", "")
    horizon = request.GET.get("dias", "")
    if status:
        rows = [r for r in rows if r.status == status]
    if horizon.isdigit():
        rows = [r for r in rows if r.days_left is not None and r.days_left <= int(horizon)]

    can_apply = request.user.can(Module.SALARIOS, Level.ADMINISTRAR)
    if request.method == "POST":
        if not can_apply:
            raise PermissionDenied
        ids = [int(i) for i in request.POST.getlist("empleado") if i.isdigit()]
        if not ids:
            messages.warning(request, "Seleccioná al menos un empleado.")
            return redirect(request.get_full_path())
        applied, skipped = 0, []
        for row in ajustes.upcoming(Employee.objects.filter(pk__in=ids)):
            if row.can_apply:
                adj = ajustes.apply(row, request.user)
                AuditLog.log(request.user, AuditLog.Action.CREATE, adj, f"Ajuste programado aplicado: {adj}")
                applied += 1
            else:
                skipped.append(row.employee.full_name)
        if applied:
            messages.success(request, f"Se registraron {applied} ajuste(s) salarial(es).")
        if skipped:
            messages.warning(request, "No se aplicaron (falta salario o IPC): " + ", ".join(skipped))
        return redirect(request.get_full_path())

    if request.GET.get("exportar"):
        headers = ["Legajo", "Empleado", "Área", "Esquema", "Último ajuste", "Salario base actual", "Costos adicionales",
                   "Total con adicionales actual", "Próximo ajuste (vigencia)", "Mes trabajado", "Se abona en", "Días restantes", "Base estimada", "Total con adicionales estimado",
                   "Variación %", "Estado", "IPC faltante"]
        data = [[r.employee.file_number, str(r.employee), str(r.employee.department or ""),
                 r.plan.summary if r.plan else "", r.last.effective_date if r.last else None, r.base_salary,
                 r.extras, r.gross_now, r.next_date, month_label(r.next_date), month_label(payment_month(r.next_date)),
                 r.days_left, None if r.missing_ipc else r.new_salary,
                 None if r.missing_ipc else r.gross_new,
                 round(r.pct, 2) if r.pct is not None and not r.missing_ipc else None,
                 UPCOMING_STATUS[r.status][0], r.ipc_missing_text] for r in rows]
        return excel_response("proximos_ajustes", "Próximos ajustes", headers, data)

    counts = {}
    for r in ajustes.upcoming(employees):
        counts[r.status] = counts.get(r.status, 0) + 1
    return render(request, "empleados/upcoming_adjustments.html", {
        "rows": rows, "status_map": UPCOMING_STATUS, "counts": counts, "can_apply": can_apply,
        "can_edit": request.user.can(Module.SALARIOS, Level.EDITAR),
        "departments": Department.objects.all(), "area": area, "estado": status, "dias": horizon,
        "last_ipc": IPCValue.objects.first(),
    })


class IPCList(HRListView):
    model = IPCValue
    module = Module.SALARIOS
    url_prefix = "empleados:ipc"
    title = "IPC mensual (INDEC)"
    create_label = "Cargar mes"
    template_name = "empleados/ipc_list.html"
    paginate_by = 36
    columns = [
        Column("Mes", lambda i: i.month.strftime("%m/%Y")),
        Column("Variación mensual", lambda i: f"{i.variation:.1f} %".replace(".", ",")),
        Column("Fuente", "source"),
    ]


class IPCCreate(HRCreateView):
    model = IPCValue
    form_class = IPCForm
    module = Module.SALARIOS
    url_prefix = "empleados:ipc"
    title = "Cargar IPC mensual"

    def get_success_url(self):
        return self.url_for("list")


class IPCUpdate(HRUpdateView):
    model = IPCValue
    form_class = IPCForm
    module = Module.SALARIOS
    url_prefix = "empleados:ipc"

    def get_success_url(self):
        return self.url_for("list")


class IPCDelete(HRDeleteView):
    model = IPCValue
    module = Module.SALARIOS
    url_prefix = "empleados:ipc"


@login_required
def ipc_import(request):
    """Importación experimental desde la API pública de ArgentinaDatos."""
    if not request.user.can(Module.SALARIOS, Level.EDITAR) or request.method != "POST":
        raise PermissionDenied
    import json
    import urllib.request
    from decimal import Decimal

    url = "https://api.argentinadatos.com/v1/finanzas/indices/inflacion"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "HRMS/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            items = json.loads(resp.read().decode("utf-8"))
        created = 0
        with transaction.atomic():
            for it in items:
                month = datetime.date.fromisoformat(str(it["fecha"])[:10]).replace(day=1)
                if month.year < datetime.date.today().year - 3:
                    continue
                _, was_created = IPCValue.objects.update_or_create(
                    month=month, defaults={"variation": Decimal(str(it["valor"])), "source": "INDEC vía ArgentinaDatos"}
                )
                created += was_created
        messages.success(request, f"IPC importado ({created} meses nuevos). Verificá los valores con el INDEC.")
    except Exception as e:  # red, formato inesperado, etc.
        messages.error(request, f"No se pudo importar el IPC automáticamente ({e}). Cargalo a mano con el dato del INDEC.")
    return redirect("empleados:ipc_list")


@login_required
def incomplete_files(request):
    """Legajos con datos clave sin completar (reglas en empleados/completeness.py)."""
    from .completeness import OBLIGATORIO, RULES, missing_fields

    if not request.user.can(Module.EMPLEADOS):
        raise PermissionDenied
    level = request.GET.get("nivel", "")
    rows = missing_fields(Employee.objects.exclude(status=Employee.Status.DESVINCULADO).select_related("user"))
    if level:
        rows = [(e, [m for m in missing if m[2] == level]) for e, missing in rows]
        rows = [r for r in rows if r[1]]
    return render(request, "empleados/incomplete.html", {
        "rows": rows, "level": level, "rules": RULES, "OBLIGATORIO": OBLIGATORIO,
    })
