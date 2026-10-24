from apps.core.forms import DATE, TIME, BaseModelForm
from apps.empleados.models import Employee

from .models import Absence, Overtime, Tardiness


class _EmployeeQSMixin:
    def __init__(self, *args, employees=None, **kwargs):
        super().__init__(*args, **kwargs)
        qs = employees if employees is not None else Employee.objects.all()
        self.fields["employee"].queryset = qs.exclude(status=Employee.Status.DESVINCULADO)


class AbsenceForm(_EmployeeQSMixin, BaseModelForm):
    class Meta:
        model = Absence
        fields = ["employee", "date", "reason", "justified", "paid", "notified", "attachment", "notes"]
        widgets = {"date": DATE}


class TardinessForm(_EmployeeQSMixin, BaseModelForm):
    class Meta:
        model = Tardiness
        fields = ["employee", "date", "scheduled_time", "arrival_time", "justified", "notes"]
        widgets = {"date": DATE, "scheduled_time": TIME, "arrival_time": TIME}
        help_texts = {"scheduled_time": "Vacío = hora de entrada del legajo o de la empresa."}


class OvertimeForm(_EmployeeQSMixin, BaseModelForm):
    class Meta:
        model = Overtime
        fields = ["employee", "date", "start_time", "end_time", "hours", "rate", "compensation", "reason"]
        widgets = {"date": DATE, "start_time": TIME, "end_time": TIME}
