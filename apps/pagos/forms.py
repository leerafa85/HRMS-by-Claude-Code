import datetime

from django import forms
from django.forms import inlineformset_factory

from apps.core.forms import DATE, BaseForm, BaseModelForm
from apps.empleados.models import Employee

from .models import SETTLEMENT_CONCEPTS, FinalSettlement, SalaryAdvance, SettlementItem, SettlementPayment


class MonthField(forms.DateField):
    """Campo mes/año (input type=month)."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("input_formats", ["%Y-%m", "%Y-%m-%d"])
        kwargs.setdefault("widget", forms.DateInput(format="%Y-%m"))
        super().__init__(*args, **kwargs)


class SalaryAdvanceForm(BaseModelForm):
    discount_period = MonthField(label="Se descuenta del sueldo de (mes)")

    class Meta:
        model = SalaryAdvance
        fields = ["employee", "date", "amount", "reason", "payment_method", "paid_date", "discount_period",
                  "discounted", "cancelled", "attachment", "notes"]
        widgets = {"date": DATE, "paid_date": DATE, "notes": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["discount_period"].widget.input_type = "month"
        self.fields["discount_period"].widget.format = "%Y-%m"
        self.fields["discount_period"].required = False
        self.fields["discount_period"].help_text = "Vacío = el mes de la fecha del adelanto."
        if not self.instance.pk:
            self.fields["employee"].queryset = Employee.objects.exclude(status=Employee.Status.DESVINCULADO)
            self.fields.pop("discounted")
            self.fields.pop("cancelled")

    def clean(self):
        data = super().clean()
        if not data.get("discount_period") and data.get("date"):
            data["discount_period"] = data["date"].replace(day=1)
            self.instance.discount_period = data["discount_period"]
        return data


class MarkDiscountedForm(BaseForm):
    period = MonthField(label="Período liquidado (mes)", initial=lambda: datetime.date.today().replace(day=1))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["period"].widget.input_type = "month"
        self.fields["period"].widget.format = "%Y-%m"


class FinalSettlementForm(BaseModelForm):
    class Meta:
        model = FinalSettlement
        fields = ["employee", "reason", "termination_date", "notice_date", "due_date", "status", "payment_method",
                  "prepared_by", "attachment", "notes"]
        widgets = {"termination_date": DATE, "notice_date": DATE, "due_date": DATE,
                   "notes": forms.Textarea(attrs={"rows": 3})}


class SettlementItemForm(BaseModelForm):
    class Meta:
        model = SettlementItem
        fields = ["concept", "kind", "amount", "detail"]
        widgets = {"concept": forms.TextInput(attrs={"list": "concepts"})}

    def has_changed(self):
        # Igual que en costos adicionales: una fila nueva cuenta si tiene datos (incluidas las precargadas).
        if self.is_bound and self.instance.pk is None:
            return any(str(self.data.get(self.add_prefix(f), "")).strip() for f in ("concept", "amount"))
        return super().has_changed()

    def clean_amount(self):
        amount = self.cleaned_data.get("amount")
        if amount is not None and amount < 0:
            raise forms.ValidationError("Ingresá el importe en positivo; el tipo indica si suma o descuenta.")
        return amount


SettlementItemFormSet = inlineformset_factory(
    FinalSettlement, SettlementItem, form=SettlementItemForm, extra=0, can_delete=True
)


class SettlementPaymentForm(BaseModelForm):
    class Meta:
        model = SettlementPayment
        fields = ["date", "amount", "method", "reference"]
        widgets = {"date": DATE}

    def clean_amount(self):
        amount = self.cleaned_data["amount"]
        if amount <= 0:
            raise forms.ValidationError("El importe debe ser mayor a cero.")
        return amount


CONCEPTS = SETTLEMENT_CONCEPTS
