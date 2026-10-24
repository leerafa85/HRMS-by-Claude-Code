import datetime
import os

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
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
from apps.core.models import AuditLog
from apps.core.modules import Level, Module
from apps.reportes.excel import excel_response

from .forms import (
    BulkSalaryForm,
    DepartmentForm,
    DocumentForm,
    EmergencyContactForm,
    EmployeeForm,
    FamilyMemberForm,
    LocationForm,
    MultiDocumentUploadForm,
    PositionForm,
    SalaryAdjustmentForm,
    TerminationForm,
)
from .models import (
    Department,
    EmergencyContact,
    Employee,
    EmployeeDocument,
    FamilyMember,
    Location,
    Position,
    SalaryAdjustment,
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
        headers.append("Salario bruto vigente")
    rows = []
    for e in Employee.objects.select_related("department", "position", "location", "manager"):
        row = [e.file_number, e.last_name, e.first_name, e.dni, e.cuil, e.birth_date, e.work_email, e.mobile,
               str(e.department or ""), str(e.position or ""), str(e.location or ""), str(e.manager or ""),
               e.hire_date, e.seniority_display, e.get_contract_type_display(), e.union_agreement, e.category,
               e.health_insurance, e.get_status_display(), e.termination_date]
        if can_salary:
            row.append(e.current_salary)
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
        "sensitive": user.can(Module.EMPLEADOS) or is_self,
    }
    ctx = {"employee": employee, "perm": can, "is_self": is_self, "self_view": self_view}
    if can["documents"]:
        docs = employee.documents.all()
        if not user.can(Module.DOCUMENTOS):
            docs = docs.filter(visible_to_employee=True)
        ctx["documents"] = docs
        ctx["upload_form"] = MultiDocumentUploadForm() if can["documents_edit"] else None
    if can["salary"]:
        ctx["salaries"] = employee.salary_adjustments.all()
    if can["leave"]:
        ctx["balances"] = LeaveBalance.objects.filter(employee=employee).select_related("leave_type").order_by("-year")
        ctx["leave_requests"] = employee.leave_requests.select_related("leave_type")[:20]
    if can["attendance"]:
        year_start = datetime.date(datetime.date.today().year, 1, 1)
        ctx["absences"] = employee.absences.filter(date__gte=year_start)
        ctx["tardies"] = employee.tardies.filter(date__gte=year_start)
        ctx["overtimes"] = employee.overtimes.filter(date__gte=year_start)
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
        Column("Vigencia", "effective_date"),
        Column("Anterior", "previous_salary", kind="money"),
        Column("Nuevo", "new_salary", kind="money"),
        Column("Variación %", lambda a: f"{a.variation_pct:.2f} %".replace(".", ",") if a.variation_pct is not None else "—"),
        Column("Motivo", "reason"),
        Column("Registrado por", "created_by"),
    ]
    filters = [
        ("motivo", "reason", "Motivo", SalaryAdjustment.Reason.choices),
        ("empleado", "employee_id", "Empleado", lambda: [(e.pk, str(e)) for e in Employee.objects.all()]),
    ]

    def get_queryset(self):
        return super().get_queryset().select_related("employee", "created_by")


class SalaryCreate(HRCreateView):
    model = SalaryAdjustment
    form_class = SalaryAdjustmentForm
    module = Module.SALARIOS
    url_prefix = "empleados:salario"
    title = "Nuevo ajuste salarial"

    def get_initial(self):
        return {"employee": self.request.GET.get("empleado"), "effective_date": datetime.date.today().replace(day=1)}

    def get_success_url(self):
        return self.url_for("list")


class SalaryUpdate(HRUpdateView):
    model = SalaryAdjustment
    form_class = SalaryAdjustmentForm
    module = Module.SALARIOS
    url_prefix = "empleados:salario"

    def get_success_url(self):
        return self.url_for("list")


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
            current = e.current_salary
            if current:
                preview.append((e, current, (current * factor).quantize(Decimal("0.01"))))
        if "confirmar" in request.POST:
            with transaction.atomic():
                for e, current, new in preview:
                    adj = SalaryAdjustment(
                        employee=e, effective_date=data["effective_date"], previous_salary=current, new_salary=new,
                        reason=data["reason"], notes=data["notes"] or f"Ajuste masivo {data['percent']} %",
                        created_by=request.user,
                    )
                    if data["attachment"]:
                        adj.attachment = data["attachment"]
                    adj.save()
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
