from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from apps.core.crud import Column, HRDeleteView, HRListView
from apps.core.models import AuditLog
from apps.core.modules import Level, Module

from .forms import StartChecklistForm, TaskForm, TemplateForm, TemplateTaskFormSet
from .models import ChecklistTask, ChecklistTemplate, EmployeeChecklist


class ChecklistList(HRListView):
    model = EmployeeChecklist
    module = Module.ONBOARDING
    url_prefix = "onboarding:checklist"
    title = "Onboarding y offboarding"
    create_label = "Iniciar checklist"
    template_name = "onboarding/checklist_list.html"
    search_fields = ["employee__first_name", "employee__last_name", "name"]
    extra_actions = [("Plantillas", "onboarding:plantilla_list", "files")]
    columns = [
        Column("Empleado", "employee", link=True),
        Column("Checklist", "name"),
        Column("Tipo", "kind", badge={"onboarding": "success", "offboarding": "danger"}),
        Column("Fecha", "start_date"),
        Column("Avance", lambda c: f"{c.progress} %"),
    ]
    filters = [("tipo", "kind", "Tipo", [("onboarding", "Onboarding"), ("offboarding", "Offboarding")])]

    def get_queryset(self):
        return super().get_queryset().select_related("employee").prefetch_related("tasks")


@login_required
def checklist_start(request):
    if not request.user.can(Module.ONBOARDING, Level.EDITAR):
        raise PermissionDenied
    form = StartChecklistForm(request.POST or None, initial={"employee": request.GET.get("empleado")})
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        cl = EmployeeChecklist.from_template(d["template"], d["employee"], d["start_date"], request.user)
        AuditLog.log(request.user, AuditLog.Action.CREATE, cl)
        messages.success(request, "Checklist iniciado.")
        return redirect("onboarding:checklist_detail", pk=cl.pk)
    return render(request, "crud/form.html", {"form": form, "title": "Iniciar onboarding / offboarding",
                                              "cancel_url": reverse("onboarding:checklist_list")})


def _can_see(user, checklist):
    return user.can(Module.ONBOARDING) or checklist.tasks.filter(assignee=user).exists()


@login_required
def checklist_detail(request, pk):
    cl = get_object_or_404(EmployeeChecklist.objects.select_related("employee"), pk=pk)
    if not _can_see(request.user, cl):
        raise PermissionDenied
    can_edit = request.user.can(Module.ONBOARDING, Level.EDITAR)
    form = TaskForm(request.POST or None)
    if request.method == "POST" and can_edit and form.is_valid():
        t = form.save(commit=False)
        t.checklist = cl
        t.order = cl.tasks.count() + 1
        t.save()
        messages.success(request, "Tarea agregada.")
        return redirect("onboarding:checklist_detail", pk=pk)
    return render(request, "onboarding/checklist_detail.html", {
        "cl": cl, "tasks": cl.tasks.select_related("assignee", "done_by"), "form": form, "can_edit": can_edit,
        "can_admin": request.user.can(Module.ONBOARDING, Level.ADMINISTRAR),
    })


@login_required
def task_toggle(request, pk):
    task = get_object_or_404(ChecklistTask.objects.select_related("checklist"), pk=pk)
    if request.method != "POST" or not (
        request.user.can(Module.ONBOARDING, Level.EDITAR) or task.assignee_id == request.user.pk
    ):
        raise PermissionDenied
    task.toggle(request.user)
    nxt = request.POST.get("next", "")
    return redirect(nxt if nxt.startswith("/") and not nxt.startswith("//") else reverse("onboarding:checklist_detail", args=[task.checklist_id]))


@login_required
def task_delete(request, pk):
    task = get_object_or_404(ChecklistTask, pk=pk)
    if request.method != "POST" or not request.user.can(Module.ONBOARDING, Level.EDITAR):
        raise PermissionDenied
    cl_id = task.checklist_id
    task.delete()
    return redirect("onboarding:checklist_detail", pk=cl_id)


class ChecklistDelete(HRDeleteView):
    model = EmployeeChecklist
    module = Module.ONBOARDING
    url_prefix = "onboarding:checklist"


@login_required
def my_tasks(request):
    tasks = ChecklistTask.objects.filter(assignee=request.user).select_related("checklist__employee").order_by("done", "due_date")
    return render(request, "onboarding/my_tasks.html", {"tasks": tasks})


# ---------------------------------------------------------------- Plantillas


class TemplateList(HRListView):
    model = ChecklistTemplate
    module = Module.ONBOARDING
    url_prefix = "onboarding:plantilla"
    title = "Plantillas de onboarding / offboarding"
    create_label = "Nueva plantilla"
    columns = [
        Column("Nombre", "name"), Column("Tipo", "kind"), Column("Tareas", lambda t: t.tasks.count()),
        Column("Activa", "active"),
    ]


@login_required
def template_edit(request, pk=None):
    if not request.user.can(Module.ONBOARDING, Level.EDITAR):
        raise PermissionDenied
    tpl = get_object_or_404(ChecklistTemplate, pk=pk) if pk else ChecklistTemplate()
    form = TemplateForm(request.POST or None, instance=tpl)
    formset = TemplateTaskFormSet(request.POST or None, instance=tpl)
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        with transaction.atomic():
            tpl = form.save()
            formset.instance = tpl
            formset.save()
        messages.success(request, "Plantilla guardada.")
        return redirect("onboarding:plantilla_list")
    return render(request, "onboarding/template_form.html", {"form": form, "formset": formset, "tpl": tpl})


class TemplateDelete(HRDeleteView):
    model = ChecklistTemplate
    module = Module.ONBOARDING
    url_prefix = "onboarding:plantilla"
