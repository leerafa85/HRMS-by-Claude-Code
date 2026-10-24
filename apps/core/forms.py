from django import forms


class BootstrapFormMixin:
    """Aplica clases de Bootstrap 5 a todos los widgets."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            w = field.widget
            if isinstance(w, (forms.CheckboxInput, forms.CheckboxSelectMultiple, forms.RadioSelect)):
                w.attrs.setdefault("class", "form-check-input")
            elif isinstance(w, (forms.Select, forms.SelectMultiple)):
                w.attrs.setdefault("class", "form-select")
            elif isinstance(w, forms.HiddenInput):
                pass
            else:
                w.attrs.setdefault("class", "form-control")
            if isinstance(w, forms.DateInput):
                w.input_type = "date"
                w.format = "%Y-%m-%d"
            if isinstance(w, forms.TimeInput):
                w.input_type = "time"
                w.format = "%H:%M"
            if isinstance(w, forms.Textarea):
                w.attrs.setdefault("rows", 3)


class BaseModelForm(BootstrapFormMixin, forms.ModelForm):
    pass


class BaseForm(BootstrapFormMixin, forms.Form):
    pass


DATE = forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"})
DATETIME = forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local"})
TIME = forms.TimeInput(format="%H:%M", attrs={"type": "time"})
