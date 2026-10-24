import datetime

from django import forms
from django.forms import inlineformset_factory

from apps.core.forms import BaseModelForm
from apps.empleados.models import Employee

from .models import Goal, GoalPlan, PeriodType, current_period_number, period_choices


class PlanForm(BaseModelForm):
    class Meta:
        model = GoalPlan
        fields = ["period_type", "year", "period_number", "scope", "department", "employee", "evaluator", "status", "notes"]
        widgets = {"scope": forms.RadioSelect, "notes": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        ptype = (self.data.get("period_type") or self.initial.get("period_type")
                 or self.instance.period_type or PeriodType.MENSUAL)
        if ptype not in PeriodType.values:
            ptype = PeriodType.MENSUAL
        self.fields["period_number"] = forms.TypedChoiceField(
            label="Período", choices=period_choices(ptype), coerce=int,
            initial=self.initial.get("period_number") or current_period_number(ptype),
            widget=forms.Select(attrs={"class": "form-select"}),
        )
        self.fields["year"].initial = self.fields["year"].initial or datetime.date.today().year
        self.fields["employee"].queryset = Employee.objects.exclude(status=Employee.Status.DESVINCULADO)
        self.fields["department"].required = False
        self.fields["employee"].required = False
        if not self.instance.pk:
            self.fields.pop("status")


class GoalForm(BaseModelForm):
    class Meta:
        model = Goal
        fields = ["objective", "responsible", "done", "score", "how_achieved", "observations"]
        widgets = {
            "objective": forms.Textarea(attrs={"rows": 2, "placeholder": "Objetivo a cumplir"}),
            "how_achieved": forms.Textarea(attrs={"rows": 2}),
            "observations": forms.Textarea(attrs={"rows": 2}),
            "score": forms.NumberInput(attrs={"step": "0.5", "min": "1", "max": "10", "placeholder": "1-10"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["responsible"].queryset = Employee.objects.exclude(status=Employee.Status.DESVINCULADO)
        for name in ("objective", "how_achieved", "observations", "score"):
            self.fields[name].widget.attrs["class"] += " form-control-sm"
        self.fields["responsible"].widget.attrs["class"] += " form-select-sm"

    def has_changed(self):
        # Una fila nueva cuenta solo si se escribió el objetivo.
        if self.is_bound and self.instance.pk is None:
            return bool(str(self.data.get(self.add_prefix("objective"), "")).strip())
        return super().has_changed()


GoalFormSet = inlineformset_factory(GoalPlan, Goal, form=GoalForm, extra=0, can_delete=True)
