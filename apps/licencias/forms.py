import datetime

from django import forms

from apps.core.forms import DATE, BaseForm, BaseModelForm
from apps.empleados.models import Employee

from .models import Holiday, LeaveBalance, LeaveRequest, LeaveType


class LeaveRequestForm(BaseModelForm):
    """Alta de solicitud. Si `employee` se fija (autogestión), el campo se oculta."""

    class Meta:
        model = LeaveRequest
        fields = ["employee", "leave_type", "start_date", "end_date", "half_day", "period_year", "reason", "attachment"]
        widgets = {"start_date": DATE, "end_date": DATE}

    def __init__(self, *args, employee=None, self_service=False, **kwargs):
        super().__init__(*args, **kwargs)
        types = LeaveType.objects.filter(active=True)
        if self_service:
            types = types.filter(self_service=True)
        self.fields["leave_type"].queryset = types
        self.fields["employee"].queryset = Employee.objects.exclude(status=Employee.Status.DESVINCULADO)
        if employee:
            self.fields.pop("employee")
            self.instance.employee = employee


class ReviewForm(BaseForm):
    comment = forms.CharField(label="Comentario", widget=forms.Textarea, required=False)


class LeaveTypeForm(BaseModelForm):
    class Meta:
        model = LeaveType
        fields = "__all__"
        widgets = {"color": forms.TextInput(attrs={"type": "color"})}


class LeaveBalanceForm(BaseModelForm):
    class Meta:
        model = LeaveBalance
        fields = "__all__"


class GenerateBalancesForm(BaseForm):
    year = forms.IntegerField(label="Período (año)", initial=datetime.date.today().year, min_value=2000, max_value=2100)
    carry_over = forms.BooleanField(
        label="Arrastrar saldo no gozado del período anterior", required=False, initial=True,
        help_text="Requiere acuerdo de partes. Las vacaciones no son compensables en dinero (art. 162 LCT).",
    )
    carry_over_cap = forms.BooleanField(
        label="Limitar el arrastre a un tercio del período (art. 164 LCT)", required=False, initial=True
    )
    overwrite = forms.BooleanField(label="Recalcular días si el saldo ya existe", required=False)


class HolidayForm(BaseModelForm):
    class Meta:
        model = Holiday
        exclude = ["source"]
        widgets = {"date": DATE}

    def save(self, commit=True):
        # Lo que se carga o edita a mano queda protegido de la actualización automática.
        self.instance.source = "manual"
        return super().save(commit)
