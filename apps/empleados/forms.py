from decimal import Decimal

from django import forms

from apps.core.forms import DATE, TIME, BaseForm, BaseModelForm
from apps.core.validators import validate_document

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
)


class EmployeeForm(BaseModelForm):
    initial_salary = forms.DecimalField(
        label="Salario bruto inicial ($)", required=False, max_digits=14, decimal_places=2,
        help_text="Opcional: registra el primer ajuste salarial (motivo «Salario de ingreso»).",
    )

    FIELDSETS = [
        ("Identificación", ["file_number", "first_name", "last_name", "photo", "dni", "cuil", "birth_date",
                            "gender", "marital_status", "nationality"]),
        ("Contacto", ["work_email", "personal_email", "phone", "mobile", "address", "city", "province", "postal_code"]),
        ("Datos laborales", ["status", "hire_date", "seniority_date", "trial_end_date", "contract_type",
                             "contract_end_date", "pay_type", "department", "position", "location", "manager",
                             "weekly_hours", "start_time", "end_time", "works_saturday"]),
        ("Encuadre convencional y obra social", ["union_agreement", "category", "union", "health_insurance", "health_plan"]),
        ("Datos bancarios", ["bank", "cbu", "bank_alias"]),
        ("Otros", ["notes", "initial_salary"]),
    ]

    class Meta:
        model = Employee
        exclude = ["user", "termination_date", "termination_reason", "termination_notes"]
        widgets = {
            "birth_date": DATE, "hire_date": DATE, "seniority_date": DATE, "trial_end_date": DATE,
            "contract_end_date": DATE, "start_time": TIME, "end_time": TIME,
        }

    def __init__(self, *args, can_salary=False, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk or not can_salary:
            self.fields.pop("initial_salary")
        if self.instance.pk:
            self.fields["manager"].queryset = Employee.objects.exclude(pk=self.instance.pk).exclude(
                status=Employee.Status.DESVINCULADO
            )
        else:
            self.fields["manager"].queryset = Employee.objects.exclude(status=Employee.Status.DESVINCULADO)
            self.fields["status"].choices = [
                c for c in Employee.Status.choices if c[0] != Employee.Status.DESVINCULADO
            ]
            if not self.initial.get("file_number"):
                self.initial["file_number"] = next_file_number()

    def fieldsets(self):
        return [(title, [self[f] for f in names if f in self.fields]) for title, names in self.FIELDSETS]

    def clean_cuil(self):
        return "".join(c for c in self.cleaned_data["cuil"] if c.isdigit())

    def clean_dni(self):
        return "".join(c for c in self.cleaned_data["dni"] if c.isdigit())

    def clean(self):
        data = super().clean()
        if data.get("dni") and data.get("cuil") and data["dni"].zfill(8) != data["cuil"][2:10]:
            self.add_error("cuil", "El CUIL no corresponde al DNI ingresado.")
        if data.get("manager") and self.instance.pk and data["manager"].pk == self.instance.pk:
            self.add_error("manager", "Un empleado no puede ser su propio jefe.")
        return data


def next_file_number():
    numbers = [int(n) for n in Employee.objects.values_list("file_number", flat=True) if str(n).isdigit()]
    return str(max(numbers) + 1 if numbers else 1)


class TerminationForm(BaseForm):
    termination_date = forms.DateField(label="Fecha de egreso", widget=DATE)
    termination_reason = forms.ChoiceField(label="Motivo", choices=Employee.TerminationReason.choices)
    termination_notes = forms.CharField(label="Observaciones", widget=forms.Textarea, required=False)
    deactivate_user = forms.BooleanField(label="Desactivar su usuario del sistema", required=False, initial=True)
    offboarding_template = forms.ModelChoiceField(
        label="Iniciar checklist de offboarding", queryset=None, required=False
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.onboarding.models import ChecklistTemplate, Kind

        self.fields["offboarding_template"].queryset = ChecklistTemplate.objects.filter(
            kind=Kind.OFFBOARDING, active=True
        )


class DepartmentForm(BaseModelForm):
    class Meta:
        model = Department
        fields = "__all__"


class LocationForm(BaseModelForm):
    class Meta:
        model = Location
        fields = "__all__"


class PositionForm(BaseModelForm):
    class Meta:
        model = Position
        fields = "__all__"


class EmergencyContactForm(BaseModelForm):
    class Meta:
        model = EmergencyContact
        exclude = ["employee"]


class FamilyMemberForm(BaseModelForm):
    class Meta:
        model = FamilyMember
        exclude = ["employee"]
        widgets = {"birth_date": DATE}


class DocumentForm(BaseModelForm):
    class Meta:
        model = EmployeeDocument
        fields = ["employee", "category", "title", "file", "issue_date", "expiry_date", "visible_to_employee", "notes"]
        widgets = {"issue_date": DATE, "expiry_date": DATE}


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single = super().clean
        if isinstance(data, (list, tuple)):
            return [single(d, initial) for d in data]
        return [single(data, initial)]


class MultiDocumentUploadForm(BaseForm):
    files = MultipleFileField(label="Archivos", help_text="Podés seleccionar varios archivos a la vez.")
    category = forms.ChoiceField(label="Categoría", choices=EmployeeDocument.Category.choices)
    expiry_date = forms.DateField(label="Vencimiento", widget=DATE, required=False)
    visible_to_employee = forms.BooleanField(label="Visible para el empleado", required=False, initial=True)

    def clean_files(self):
        files = self.cleaned_data["files"]
        for f in files:
            validate_document(f)
        return files


class SalaryAdjustmentForm(BaseModelForm):
    percent = forms.DecimalField(
        label="o aumento porcentual (%)", required=False, max_digits=6, decimal_places=2,
        help_text="Si completás el porcentaje, se calcula el nuevo salario sobre el vigente.",
    )

    class Meta:
        model = SalaryAdjustment
        fields = ["employee", "effective_date", "new_salary", "percent", "reason", "notes", "attachment"]
        widgets = {"effective_date": DATE}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["new_salary"].required = False
        self.fields["employee"].queryset = Employee.objects.exclude(status=Employee.Status.DESVINCULADO)
        self.order_fields(["employee", "effective_date", "new_salary", "percent", "reason", "notes", "attachment"])

    def clean(self):
        data = super().clean()
        pct, new, emp = data.get("percent"), data.get("new_salary"), data.get("employee")
        if pct is not None and not new:
            current = emp.current_salary if emp else None
            if not current:
                self.add_error("percent", "El empleado no tiene salario vigente para aplicar un porcentaje.")
            else:
                data["new_salary"] = (current * (1 + pct / Decimal(100))).quantize(Decimal("0.01"))
                self.instance.new_salary = data["new_salary"]
        if not data.get("new_salary"):
            self.add_error("new_salary", "Indicá el nuevo salario o un porcentaje.")
        elif data["new_salary"] <= 0:
            self.add_error("new_salary", "El salario debe ser mayor a cero.")
        return data


class BulkSalaryForm(BaseForm):
    percent = forms.DecimalField(label="Aumento (%)", max_digits=6, decimal_places=2)
    effective_date = forms.DateField(label="Vigencia desde", widget=DATE)
    reason = forms.ChoiceField(label="Motivo", choices=SalaryAdjustment.Reason.choices, initial="paritaria")
    department = forms.ModelChoiceField(label="Solo área", queryset=Department.objects.all(), required=False)
    union_agreement = forms.CharField(label="Solo convenio (CCT)", required=False, help_text="Texto exacto del convenio.")
    notes = forms.CharField(label="Observaciones", required=False, widget=forms.Textarea)
    attachment = forms.FileField(label="Respaldo (acta paritaria, etc.)", required=False, validators=[validate_document])

    def clean_percent(self):
        pct = self.cleaned_data["percent"]
        if pct <= -100:
            raise forms.ValidationError("Porcentaje inválido.")
        return pct


class SalaryPlanForm(BaseModelForm):
    class Meta:
        model = SalaryAdjustmentPlan
        fields = ["frequency_months", "reference", "start_month", "method", "percent", "amount",
                  "ipc_extra_percent", "ipc_lag_months", "active", "notes"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["ipc_extra_percent"].required = False

    def clean_ipc_extra_percent(self):
        return self.cleaned_data.get("ipc_extra_percent") or 0


class BulkPlanForm(SalaryPlanForm):
    department = forms.ModelChoiceField(label="Aplicar a: área", queryset=Department.objects.all(), required=False)
    union_agreement = forms.CharField(label="Aplicar a: convenio (CCT)", required=False)
    only_without_plan = forms.BooleanField(label="Solo empleados sin esquema", required=False, initial=True)


class IPCForm(BaseModelForm):
    class Meta:
        model = IPCValue
        fields = ["month", "variation", "source"]
        help_texts = {"variation": "Variación mensual publicada por el INDEC. Ej.: 2,7"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["month"].input_formats = ["%Y-%m", "%Y-%m-%d", "%m/%Y"]
        widget = self.fields["month"].widget
        widget.input_type = "month"
        widget.format = "%Y-%m"
