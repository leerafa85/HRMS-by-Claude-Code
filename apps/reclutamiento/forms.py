from django import forms

from apps.core.forms import DATE, DATETIME, BaseForm, BaseModelForm
from apps.empleados.models import Department, Location, Position

from .models import Application, Candidate, Interview, JobOpening


class JobOpeningForm(BaseModelForm):
    class Meta:
        model = JobOpening
        exclude = ["created_by"]
        widgets = {"closing_date": DATE}


class CandidateForm(BaseModelForm):
    job = forms.ModelChoiceField(
        label="Postular a la búsqueda", queryset=JobOpening.objects.exclude(status__in=["cerrada", "cancelada"]),
        required=False,
    )

    class Meta:
        model = Candidate
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields.pop("job")


class ApplicationForm(BaseModelForm):
    class Meta:
        model = Application
        fields = ["job", "candidate", "stage", "rating", "offer_salary", "offer_start_date", "discard_reason", "notes"]
        widgets = {"offer_start_date": DATE}


class InterviewForm(BaseModelForm):
    class Meta:
        model = Interview
        fields = ["scheduled_at", "mode", "location_or_link", "interviewer", "score", "feedback", "result"]
        widgets = {"scheduled_at": DATETIME}


class HireForm(BaseForm):
    file_number = forms.CharField(label="Legajo")
    dni = forms.CharField(label="DNI")
    cuil = forms.CharField(label="CUIL")
    hire_date = forms.DateField(label="Fecha de ingreso", widget=DATE)
    department = forms.ModelChoiceField(label="Área", queryset=Department.objects.all(), required=False)
    position = forms.ModelChoiceField(label="Puesto", queryset=Position.objects.all(), required=False)
    location = forms.ModelChoiceField(label="Sede", queryset=Location.objects.all(), required=False)
    salary = forms.DecimalField(label="Salario base inicial ($)", required=False, max_digits=14, decimal_places=2)
    onboarding_template = forms.ModelChoiceField(label="Iniciar onboarding con la plantilla", queryset=None, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.onboarding.models import ChecklistTemplate, Kind

        self.fields["onboarding_template"].queryset = ChecklistTemplate.objects.filter(kind=Kind.ONBOARDING, active=True)


class PublicApplicationForm(BaseModelForm):
    class Meta:
        model = Candidate
        fields = ["first_name", "last_name", "email", "phone", "city", "linkedin", "resume", "consent"]

    website = forms.CharField(required=False, widget=forms.HiddenInput)  # honeypot anti-spam

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["resume"].required = True
        self.fields["consent"].required = True
        self.fields["consent"].label = (
            "Acepto que mis datos sean tratados para procesos de selección (Ley 25.326 de Protección de Datos Personales)"
        )

    def clean_website(self):
        if self.cleaned_data.get("website"):
            raise forms.ValidationError("Solicitud inválida.")
        return ""
