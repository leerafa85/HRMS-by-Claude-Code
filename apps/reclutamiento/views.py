from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from apps.core.crud import (
    Column,
    HRCreateView,
    HRDeleteView,
    HRDetailView,
    HRListView,
    HRUpdateView,
)
from apps.core.models import AuditLog
from apps.core.modules import Level, Module
from apps.empleados.forms import next_file_number
from apps.empleados.models import Employee, SalaryAdjustment

from .forms import (
    ApplicationForm,
    CandidateForm,
    HireForm,
    InterviewForm,
    JobOpeningForm,
    PublicApplicationForm,
)
from .models import Application, Candidate, Interview, JobOpening

JOB_BADGES = {"borrador": "secondary", "abierta": "success", "pausa": "warning", "cerrada": "primary", "cancelada": "dark"}

# ---------------------------------------------------------------- Búsquedas


class JobList(HRListView):
    model = JobOpening
    module = Module.RECLUTAMIENTO
    url_prefix = "reclutamiento:busqueda"
    title = "Búsquedas laborales"
    create_label = "Nueva búsqueda"
    search_fields = ["title", "description"]
    columns = [
        Column("Puesto", "title", link=True),
        Column("Área", "department"),
        Column("Sede", "location"),
        Column("Modalidad", "modality"),
        Column("Vacantes", "vacancies"),
        Column("Postulantes", "n_apps"),
        Column("Responsable", "hiring_manager"),
        Column("Estado", "status", badge=JOB_BADGES),
        Column("Publicada", "published"),
    ]
    filters = [("estado", "status", "Estado", JobOpening.Status.choices)]

    def get_queryset(self):
        return super().get_queryset().select_related("department", "location", "hiring_manager").annotate(
            n_apps=Count("applications")
        )


class JobCreate(HRCreateView):
    model = JobOpening
    form_class = JobOpeningForm
    module = Module.RECLUTAMIENTO
    url_prefix = "reclutamiento:busqueda"


class JobUpdate(HRUpdateView):
    model = JobOpening
    form_class = JobOpeningForm
    module = Module.RECLUTAMIENTO
    url_prefix = "reclutamiento:busqueda"


class JobDelete(HRDeleteView):
    model = JobOpening
    module = Module.RECLUTAMIENTO
    url_prefix = "reclutamiento:busqueda"


class JobDetail(HRDetailView):
    """Pipeline tipo kanban de la búsqueda."""

    model = JobOpening
    module = Module.RECLUTAMIENTO
    url_prefix = "reclutamiento:busqueda"
    template_name = "reclutamiento/job_detail.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        apps_qs = self.object.applications.select_related("candidate").annotate(n_int=Count("interviews"))
        ctx["pipeline"] = [
            {"stage": stage, "label": stage.label, "apps": [a for a in apps_qs if a.stage == stage]}
            for stage in Application.PIPELINE
        ]
        ctx["stages"] = Application.Stage.choices
        ctx["public_url"] = self.request.build_absolute_uri(reverse("empleos:detalle", args=[self.object.pk]))
        ctx["existing_candidates"] = Candidate.objects.exclude(applications__job=self.object)[:200]
        return ctx


# ---------------------------------------------------------------- Candidatos


class CandidateList(HRListView):
    model = Candidate
    module = Module.RECLUTAMIENTO
    url_prefix = "reclutamiento:candidato"
    title = "Candidatos"
    create_label = "Nuevo candidato"
    search_fields = ["first_name", "last_name", "email", "tags", "dni"]
    columns = [
        Column("Candidato", lambda c: str(c), link=True),
        Column("Email", "email"),
        Column("Teléfono", "phone"),
        Column("Fuente", "source"),
        Column("Postulaciones", lambda c: ", ".join(f"{a.job} ({a.get_stage_display()})" for a in c.applications.all()) or "—"),
        Column("CV", lambda c: "Sí" if c.resume else "No"),
        Column("Alta", "created_at"),
    ]
    filters = [("fuente", "source", "Fuente", Candidate.Source.choices),
               ("busqueda", "applications__job_id", "Búsqueda", lambda: [(j.pk, j.title) for j in JobOpening.objects.all()]),
               ("etapa", "applications__stage", "Etapa", Application.Stage.choices)]

    def get_queryset(self):
        return super().get_queryset().prefetch_related("applications__job").distinct()


class CandidateCreate(HRCreateView):
    model = Candidate
    form_class = CandidateForm
    module = Module.RECLUTAMIENTO
    url_prefix = "reclutamiento:candidato"

    def get_initial(self):
        return {"job": self.request.GET.get("busqueda")}

    def form_valid(self, form):
        response = super().form_valid(form)
        job = form.cleaned_data.get("job")
        if job:
            Application.objects.get_or_create(job=job, candidate=self.object)
        return response


class CandidateUpdate(HRUpdateView):
    model = Candidate
    form_class = CandidateForm
    module = Module.RECLUTAMIENTO
    url_prefix = "reclutamiento:candidato"


class CandidateDelete(HRDeleteView):
    model = Candidate
    module = Module.RECLUTAMIENTO
    url_prefix = "reclutamiento:candidato"


class CandidateDetail(HRDetailView):
    model = Candidate
    module = Module.RECLUTAMIENTO
    url_prefix = "reclutamiento:candidato"
    template_name = "reclutamiento/candidate_detail.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["applications"] = self.object.applications.select_related("job").prefetch_related("interviews__interviewer")
        ctx["open_jobs"] = JobOpening.objects.exclude(status__in=["cerrada", "cancelada"]).exclude(
            applications__candidate=self.object
        )
        ctx["stages"] = Application.Stage.choices
        return ctx


# ---------------------------------------------------------------- Postulaciones


def _require(user, level=Level.EDITAR):
    if not user.can(Module.RECLUTAMIENTO, level):
        raise PermissionDenied


@login_required
def application_add(request):
    _require(request.user)
    if request.method != "POST":
        raise PermissionDenied
    job = get_object_or_404(JobOpening, pk=request.POST.get("job"))
    candidate = get_object_or_404(Candidate, pk=request.POST.get("candidate"))
    try:
        Application.objects.create(job=job, candidate=candidate)
        messages.success(request, f"{candidate.full_name} se sumó a «{job}».")
    except IntegrityError:
        messages.warning(request, "El candidato ya está postulado a esa búsqueda.")
    return redirect(request.POST.get("next") or reverse("reclutamiento:busqueda_detail", args=[job.pk]))


@login_required
def application_move(request, pk):
    _require(request.user)
    app = get_object_or_404(Application, pk=pk)
    if request.method != "POST":
        raise PermissionDenied
    stage = request.POST.get("stage")
    if stage in Application.Stage.values:
        app.stage = stage
        if stage == Application.Stage.DESCARTADO and request.POST.get("discard_reason"):
            app.discard_reason = request.POST["discard_reason"][:200]
        app.save()
        AuditLog.log(request.user, AuditLog.Action.UPDATE, app, f"{app} → {app.get_stage_display()}")
    nxt = request.POST.get("next", "")
    return redirect(nxt if nxt.startswith("/") and not nxt.startswith("//") else reverse("reclutamiento:busqueda_detail", args=[app.job_id]))


@login_required
def application_edit(request, pk):
    _require(request.user)
    app = get_object_or_404(Application.objects.select_related("job", "candidate"), pk=pk)
    form = ApplicationForm(request.POST or None, instance=app)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Postulación actualizada.")
        return redirect("reclutamiento:postulacion_detail", pk=pk)
    return render(request, "crud/form.html", {
        "form": form, "title": f"Postulación: {app}", "cancel_url": reverse("reclutamiento:postulacion_detail", args=[pk])
    })


@login_required
def application_detail(request, pk):
    _require(request.user, Level.VER)
    app = get_object_or_404(Application.objects.select_related("job", "candidate"), pk=pk)
    return render(request, "reclutamiento/application_detail.html", {
        "app": app,
        "interviews": app.interviews.select_related("interviewer"),
        "interview_form": InterviewForm(),
        "stages": Application.Stage.choices,
        "can_edit": request.user.can(Module.RECLUTAMIENTO, Level.EDITAR),
    })


@login_required
def interview_edit(request, application_pk, pk=None):
    _require(request.user)
    app = get_object_or_404(Application, pk=application_pk)
    instance = get_object_or_404(Interview, pk=pk, application=app) if pk else None
    form = InterviewForm(request.POST or None, instance=instance)
    if request.method == "POST":
        if "eliminar" in request.POST and instance:
            instance.delete()
            messages.success(request, "Entrevista eliminada.")
            return redirect("reclutamiento:postulacion_detail", pk=app.pk)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.application = app
            obj.save()
            messages.success(request, "Entrevista guardada.")
            return redirect("reclutamiento:postulacion_detail", pk=app.pk)
    return render(request, "crud/form.html", {
        "form": form, "title": f"Entrevista · {app.candidate.full_name}",
        "cancel_url": reverse("reclutamiento:postulacion_detail", args=[app.pk]), "delete_inline": bool(instance),
    })


@login_required
def application_hire(request, pk):
    """Convierte al candidato en empleado (crea el legajo) y opcionalmente inicia el onboarding."""
    _require(request.user)
    if not request.user.can(Module.EMPLEADOS, Level.EDITAR):
        raise PermissionDenied("Necesitás permiso de edición en Legajos para contratar.")
    app = get_object_or_404(Application.objects.select_related("job", "candidate"), pk=pk)
    if app.hired_employee:
        messages.info(request, "Este candidato ya fue contratado.")
        return redirect("empleados:empleado_detail", pk=app.hired_employee_id)
    c = app.candidate
    initial = {
        "file_number": next_file_number(), "dni": c.dni, "hire_date": app.offer_start_date,
        "department": app.job.department_id, "position": app.job.position_id, "location": app.job.location_id,
        "salary": app.offer_salary,
    }
    form = HireForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        emp = Employee(
            file_number=d["file_number"], first_name=c.first_name, last_name=c.last_name, dni=d["dni"],
            cuil="".join(ch for ch in d["cuil"] if ch.isdigit()), hire_date=d["hire_date"],
            personal_email=c.email, mobile=c.phone, city=c.city, department=d["department"],
            position=d["position"], location=d["location"], contract_type=app.job.contract_type,
            status=Employee.Status.PRUEBA,
        )
        try:
            emp.full_clean()
        except Exception as e:
            for msg in getattr(e, "messages", [str(e)]):
                form.add_error(None, msg)
        else:
            with transaction.atomic():
                emp.save()
                if d["salary"] and request.user.can(Module.SALARIOS, Level.EDITAR):
                    SalaryAdjustment.objects.create(
                        employee=emp, effective_date=emp.hire_date, new_salary=d["salary"],
                        reason=SalaryAdjustment.Reason.INGRESO, created_by=request.user,
                    )
                if c.resume:
                    from apps.empleados.models import EmployeeDocument

                    EmployeeDocument.objects.create(
                        employee=emp, category=EmployeeDocument.Category.CV, title="CV (reclutamiento)",
                        file=c.resume.name, created_by=request.user,
                    )
                app.stage = Application.Stage.CONTRATADO
                app.hired_employee = emp
                app.save()
                if d["onboarding_template"]:
                    from apps.onboarding.models import EmployeeChecklist

                    EmployeeChecklist.from_template(d["onboarding_template"], emp, emp.hire_date, request.user)
            AuditLog.log(request.user, AuditLog.Action.CREATE, emp, f"Contratación desde reclutamiento: {emp}")
            messages.success(request, f"Se creó el legajo de {emp.full_name}. Completá los datos faltantes.")
            return redirect("empleados:empleado_update", pk=emp.pk)
    return render(request, "crud/form.html", {
        "form": form, "title": f"Contratar a {c.full_name}",
        "cancel_url": reverse("reclutamiento:postulacion_detail", args=[app.pk]), "submit_label": "Crear legajo",
    })


# ---------------------------------------------------------------- Portal público de empleos


def public_jobs(request):
    jobs = JobOpening.objects.filter(published=True, status=JobOpening.Status.ABIERTA).select_related("location", "department")
    q = request.GET.get("q", "").strip()
    if q:
        jobs = jobs.filter(Q(title__icontains=q) | Q(description__icontains=q))
    return render(request, "reclutamiento/public_list.html", {"jobs": jobs, "q": q})


def public_job_detail(request, pk):
    job = get_object_or_404(JobOpening, pk=pk, published=True, status=JobOpening.Status.ABIERTA)
    form = PublicApplicationForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        # Siempre se crea un registro nuevo: un formulario público no debe poder modificar datos existentes.
        candidate = form.save(commit=False)
        candidate.email = form.cleaned_data["email"].lower()
        candidate.source = Candidate.Source.PORTAL
        if Candidate.objects.filter(email__iexact=candidate.email).exists():
            candidate.notes = "Posible duplicado: ya existía un candidato con este email."
        candidate.save()
        Application.objects.get_or_create(job=job, candidate=candidate)
        return render(request, "reclutamiento/public_thanks.html", {"job": job})
    return render(request, "reclutamiento/public_detail.html", {"job": job, "form": form})
