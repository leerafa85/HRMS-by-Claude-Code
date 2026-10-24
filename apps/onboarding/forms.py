from django import forms
from django.forms import inlineformset_factory

from apps.core.forms import DATE, BaseForm, BaseModelForm
from apps.empleados.models import Employee

from .models import ChecklistTask, ChecklistTemplate, TemplateTask


class TemplateForm(BaseModelForm):
    class Meta:
        model = ChecklistTemplate
        fields = "__all__"


class TemplateTaskForm(BaseModelForm):
    class Meta:
        model = TemplateTask
        fields = ["order", "title", "responsible", "default_assignee", "due_offset_days", "description"]
        widgets = {"description": forms.Textarea(attrs={"rows": 1})}


TemplateTaskFormSet = inlineformset_factory(
    ChecklistTemplate, TemplateTask, form=TemplateTaskForm, extra=3, can_delete=True
)


class StartChecklistForm(BaseForm):
    employee = forms.ModelChoiceField(label="Empleado", queryset=Employee.objects.all())
    template = forms.ModelChoiceField(label="Plantilla", queryset=ChecklistTemplate.objects.filter(active=True))
    start_date = forms.DateField(label="Fecha de referencia (ingreso / egreso)", widget=DATE)


class TaskForm(BaseModelForm):
    class Meta:
        model = ChecklistTask
        fields = ["title", "responsible", "assignee", "due_date", "description"]
        widgets = {"due_date": DATE}
