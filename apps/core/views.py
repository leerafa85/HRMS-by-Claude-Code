import datetime
import mimetypes
import os

from django.apps import apps
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, Q
from django.http import FileResponse, Http404
from django.shortcuts import redirect, render
from django.utils._os import safe_join
from django.views.generic import ListView

from . import home
from .crud import (
    Column,
    HRCreateView,
    HRDeleteView,
    HRListView,
    HRUpdateView,
    ModuleRequiredMixin,
)
from .dates import next_occurrence
from .forms_admin import CompanySettingsForm, ProfileForm, RoleForm, UserForm
from .models import AuditLog, CompanySettings, Role, User
from .modules import Level, Module

# ---------------------------------------------------------------- Dashboard


@login_required
def dashboard(request):
    from apps.anuncios.models import Announcement
    from apps.empleados.models import Employee, EmployeeDocument
    from apps.licencias.models import Holiday, LeaveBalance, LeaveRequest, LeaveType
    from apps.onboarding.models import ChecklistTask
    from apps.reclutamiento.models import Interview, JobOpening

    user = request.user
    today = datetime.date.today()
    employee = getattr(user, "employee", None)
    active = Employee.objects.exclude(status=Employee.Status.DESVINCULADO)
    ctx = {"today": today}

    on_leave = LeaveRequest.objects.filter(
        status=LeaveRequest.Status.APROBADA, start_date__lte=today, end_date__gte=today
    ).select_related("employee", "leave_type")
    ctx["on_leave_today"] = on_leave

    if user.can(Module.EMPLEADOS):
        first_of_month = today.replace(day=1)
        ctx["stats"] = {
            "headcount": active.count(),
            "hires_month": Employee.objects.filter(hire_date__gte=first_of_month, hire_date__lte=today).count(),
            "exits_month": Employee.objects.filter(termination_date__gte=first_of_month, termination_date__lte=today).count(),
            "trial": active.filter(status=Employee.Status.PRUEBA).count(),
        }
        from apps.empleados.completeness import OBLIGATORIO, missing_fields

        incomplete = missing_fields(active.select_related("user"))
        ctx["incomplete"] = incomplete[:6]
        ctx["incomplete_count"] = len(incomplete)
        ctx["incomplete_required"] = sum(1 for _e, m in incomplete if any(x[2] == OBLIGATORIO for x in m))

    ctx["agenda"] = home.agenda(user, today)[:14]
    ctx["news"] = home.weekly_news(user, today)
    ctx["staff_requests"] = home.staff_requests(user, employee)

    if user.can(Module.DOCUMENTOS):
        ctx["expiring_docs"] = EmployeeDocument.objects.filter(
            expiry_date__lte=today + datetime.timedelta(days=30), employee__in=active
        ).select_related("employee").order_by("expiry_date")[:8]

    # Celebraciones (visibles para todos, como en Freshteam)
    upcoming = []
    for e in active.only("first_name", "last_name", "birth_date", "hire_date", "seniority_date", "photo"):
        if e.birth_date:
            nxt = next_occurrence(e.birth_date, today)
            if (nxt - today).days <= 30:
                upcoming.append({"employee": e, "date": nxt, "kind": "cumple"})
        nxt = next_occurrence(e.seniority_start, today)
        years = nxt.year - e.seniority_start.year
        if years > 0 and (nxt - today).days <= 30:
            upcoming.append({"employee": e, "date": nxt, "kind": "aniversario", "years": years})
    ctx["celebrations"] = sorted(upcoming, key=lambda c: c["date"])[:10]

    ctx["holidays"] = Holiday.objects.filter(date__gte=today).order_by("date")[:5]
    ctx["announcements"] = Announcement.visible_for(user)[:5]

    if user.can(Module.RECLUTAMIENTO):
        ctx["open_jobs"] = JobOpening.objects.filter(status=JobOpening.Status.ABIERTA).annotate(
            n=Count("applications")
        )[:5]
        ctx["interviews"] = Interview.objects.filter(
            scheduled_at__date__gte=today, result=Interview.Result.PENDIENTE
        ).select_related("application__candidate", "application__job")[:5]

    ctx["my_tasks"] = ChecklistTask.objects.filter(assignee=user, done=False).select_related(
        "checklist__employee"
    ).order_by("due_date")[:8]

    if employee:
        vac = LeaveType.objects.filter(kind=LeaveType.Kind.VACACIONES).first()
        ctx["my_vacation"] = (
            LeaveBalance.objects.filter(employee=employee, leave_type=vac, year__lte=today.year).order_by("-year").first()
            if vac else None
        )
        ctx["my_requests"] = employee.leave_requests.select_related("leave_type")[:5]
    return render(request, "core/dashboard.html", ctx)


# ---------------------------------------------------------------- Perfil


@login_required
def profile(request):
    form = ProfileForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Tus datos se actualizaron.")
        return redirect("core:perfil")
    return render(request, "core/profile.html", {"form": form})


# ---------------------------------------------------------------- Usuarios


class UserList(HRListView):
    model = User
    module = Module.USUARIOS
    url_prefix = "core:usuario"
    title = "Usuarios"
    create_label = "Nuevo usuario"
    search_fields = ["username", "first_name", "last_name", "email"]
    columns = [
        Column("Usuario", "username", link=True),
        Column("Nombre", lambda u: u.get_full_name()),
        Column("Email", "email"),
        Column("Roles", lambda u: "Administrador total" if u.is_superuser else ", ".join(r.name for r in u.roles.all()) or "—"),
        Column("Legajo", lambda u: getattr(u, "employee", None)),
        Column("Activo", "is_active"),
        Column("Último ingreso", "last_login"),
    ]
    filters = [("activo", "is_active", "Estado", [("True", "Activos"), ("False", "Inactivos")])]

    def get_queryset(self):
        return super().get_queryset().prefetch_related("roles").select_related("employee")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        for row in ctx["rows"]:
            u = row["obj"]
            if u == self.request.user or (u.is_superuser and not self.request.user.is_superuser):
                row["delete_url"] = None
                if u != self.request.user:
                    row["update_url"] = None
        return ctx


class _UserFormMixin:
    model = User
    form_class = UserForm
    module = Module.USUARIOS
    url_prefix = "core:usuario"
    template_name = "core/user_form.html"

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["request_user"] = self.request.user
        return kw

    def get_success_url(self):
        return self.url_for("list")


class UserCreate(_UserFormMixin, HRCreateView):
    title = "Nuevo usuario"


class UserUpdate(_UserFormMixin, HRUpdateView):
    title = "Editar usuario"

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if obj.is_superuser and not self.request.user.is_superuser:
            raise PermissionDenied("Solo un administrador total puede modificar a otro administrador total.")
        return obj


class UserDelete(HRDeleteView):
    model = User
    module = Module.USUARIOS
    url_prefix = "core:usuario"

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if obj == self.request.user:
            raise PermissionDenied("No podés eliminar tu propio usuario.")
        if obj.is_superuser and not self.request.user.is_superuser:
            raise PermissionDenied("Solo un administrador total puede eliminar a otro administrador total.")
        return obj


# ---------------------------------------------------------------- Roles


class RoleList(HRListView):
    model = Role
    module = Module.USUARIOS
    url_prefix = "core:rol"
    title = "Roles y permisos"
    create_label = "Nuevo rol"
    search_fields = ["name"]
    columns = [
        Column("Rol", "name", link=True),
        Column("Descripción", "description"),
        Column("Módulos con acceso", lambda r: sum(1 for p in r.permissions.all() if p.level > 0)),
        Column("Usuarios", lambda r: r.users.count()),
    ]

    def get_queryset(self):
        return super().get_queryset().prefetch_related("permissions")


class RoleCreate(HRCreateView):
    model = Role
    form_class = RoleForm
    module = Module.USUARIOS
    url_prefix = "core:rol"
    template_name = "core/role_form.html"
    title = "Nuevo rol"

    def get_success_url(self):
        return self.url_for("list")


class RoleUpdate(HRUpdateView):
    model = Role
    form_class = RoleForm
    module = Module.USUARIOS
    url_prefix = "core:rol"
    template_name = "core/role_form.html"
    title = "Editar rol"

    def get_success_url(self):
        return self.url_for("list")


class RoleDelete(HRDeleteView):
    model = Role
    module = Module.USUARIOS
    url_prefix = "core:rol"


# ---------------------------------------------------------------- Configuración


@login_required
def configuration(request):
    if not request.user.can(Module.CONFIGURACION):
        raise PermissionDenied
    cfg = CompanySettings.get()
    form = CompanySettingsForm(request.POST or None, request.FILES or None, instance=cfg)
    if request.method == "POST":
        if not request.user.can(Module.CONFIGURACION, Level.EDITAR):
            raise PermissionDenied
        if form.is_valid():
            form.save()
            AuditLog.log(request.user, AuditLog.Action.UPDATE, cfg, "Configuración de la empresa")
            messages.success(request, "Configuración guardada.")
            return redirect("core:configuracion")
    return render(request, "core/configuration.html", {"form": form, "can_edit": request.user.can(Module.CONFIGURACION, Level.EDITAR)})


class AuditList(ModuleRequiredMixin, ListView):
    model = AuditLog
    module = Module.USUARIOS
    required_level = Level.ADMINISTRAR
    template_name = "core/audit.html"
    paginate_by = 50

    def get_queryset(self):
        qs = super().get_queryset().select_related("user")
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(Q(description__icontains=q) | Q(model__icontains=q) | Q(user__username__icontains=q))
        return qs


# ---------------------------------------------------------------- Archivos protegidos

# (modelo, campo, módulo que habilita la descarga, atributo que apunta al empleado dueño)
PROTECTED_FILES = [
    ("empleados.Employee", "photo", None, None),
    ("empleados.EmployeeDocument", "file", Module.DOCUMENTOS, "employee"),
    ("empleados.SalaryAdjustment", "attachment", Module.SALARIOS, "employee"),
    ("licencias.LeaveRequest", "attachment", Module.LICENCIAS, "employee"),
    ("asistencia.Absence", "attachment", Module.ASISTENCIA, "employee"),
    ("asistencia.Tardiness", "attachment", Module.ASISTENCIA, "employee"),
    ("asistencia.Overtime", "attachment", Module.ASISTENCIA, "employee"),
    ("pagos.SalaryAdvance", "attachment", Module.PAGOS, "employee"),
    ("pagos.FinalSettlement", "attachment", Module.PAGOS, "employee"),
    ("reclutamiento.Candidate", "resume", Module.RECLUTAMIENTO, None),
    ("core.CompanySettings", "logo", None, None),
]


def protected_media(request, path):
    """Entrega archivos subidos solo a usuarios autorizados (el logo es público para el portal de empleos)."""
    allowed = False
    if not request.user.is_authenticated:
        if not CompanySettings.objects.filter(logo=path).exists():
            return redirect_to_login(request.get_full_path())
        allowed = True
    for label, field, module, owner_attr in PROTECTED_FILES if not allowed else []:
        model = apps.get_model(label)
        obj = model.objects.filter(**{field: path}).first()
        if not obj:
            continue
        if module is None or request.user.can(module, Level.VER):
            allowed = True
        elif owner_attr:
            owner = getattr(obj, owner_attr)
            own = getattr(request.user, "employee", None)
            is_owner = own and owner.pk == own.pk
            is_manager = own and owner.manager_id == own.pk and module in (Module.LICENCIAS, Module.ASISTENCIA)
            if label == "empleados.EmployeeDocument" and not obj.visible_to_employee:
                is_owner = False
            allowed = bool(is_owner or is_manager)
        break
    if not allowed:
        raise Http404
    try:
        full = safe_join(settings.MEDIA_ROOT, path)
    except Exception:
        raise Http404
    if not os.path.exists(full):
        raise Http404
    content_type, _ = mimetypes.guess_type(full)
    inline = content_type in ("application/pdf", "image/jpeg", "image/png", "image/webp")
    download = request.GET.get("descargar") == "1"
    return FileResponse(
        open(full, "rb"),
        content_type=content_type or "application/octet-stream",
        as_attachment=download or not inline,
    )


def error_403(request, exception=None):
    return render(request, "errors/403.html", {"message": str(exception or "")}, status=403)


def error_404(request, exception=None):
    return render(request, "errors/404.html", status=404)


def role_matrix(request):
    """Vista auxiliar para mostrar la matriz completa de permisos."""
    if not request.user.is_authenticated or not request.user.can(Module.USUARIOS):
        raise PermissionDenied
    roles = Role.objects.prefetch_related("permissions")
    rows = [
        {"module": m, "levels": [r.level_for(m.value) for r in roles]} for m in Module
    ]
    return render(request, "core/role_matrix.html", {"roles": roles, "rows": rows, "Level": Level})



@transaction.non_atomic_requests
def health(request):
    """Estado del sistema para el indicador del pie de página: verifica lectura y escritura en la base."""
    import time

    from django.db import connection
    from django.http import JsonResponse
    from django.utils import timezone

    started = time.monotonic()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        from .models import SystemTask

        now = timezone.now()
        if not SystemTask.objects.filter(key="heartbeat").update(last_success=now):
            SystemTask.objects.create(key="heartbeat", last_success=now)
    except Exception:
        resp = JsonResponse({"status": "error", "db": False}, status=503)
    else:
        resp = JsonResponse({"status": "ok", "db": True, "db_ms": round((time.monotonic() - started) * 1000)})
    resp["Cache-Control"] = "no-store"
    return resp
