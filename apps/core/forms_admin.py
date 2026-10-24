from django import forms
from django.contrib.auth import password_validation

from apps.empleados.models import Employee

from .forms import BaseModelForm
from .models import CompanySettings, Role, User
from .modules import Level, Module


class UserForm(BaseModelForm):
    password1 = forms.CharField(label="Contraseña", widget=forms.PasswordInput, required=False)
    password2 = forms.CharField(label="Repetir contraseña", widget=forms.PasswordInput, required=False)
    employee = forms.ModelChoiceField(
        label="Legajo vinculado",
        queryset=Employee.objects.none(),
        required=False,
        help_text="Vincular el usuario con su legajo habilita la autogestión (Mi legajo, Mis licencias).",
    )

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email", "is_active", "is_superuser", "roles"]
        widgets = {"roles": forms.CheckboxSelectMultiple}
        labels = {"is_superuser": "Administrador total del sistema", "is_active": "Activo"}
        help_texts = {"username": "Usuario para iniciar sesión.", "is_superuser": "Acceso completo a todos los módulos."}

    def __init__(self, *args, request_user=None, **kwargs):
        super().__init__(*args, **kwargs)
        qs = Employee.objects.filter(user__isnull=True)
        current = getattr(self.instance, "employee", None) if self.instance.pk else None
        if current:
            qs = Employee.objects.filter(pk=current.pk) | qs
            self.fields["employee"].initial = current
        self.fields["employee"].queryset = qs.order_by("last_name")
        if not (request_user and request_user.is_superuser):
            self.fields.pop("is_superuser")
        if not self.instance.pk:
            self.fields["password1"].required = True
            self.fields["password2"].required = True
        else:
            self.fields["password1"].help_text = "Dejar vacío para no cambiarla."

    def clean(self):
        data = super().clean()
        p1, p2 = data.get("password1"), data.get("password2")
        if p1 or p2:
            if p1 != p2:
                self.add_error("password2", "Las contraseñas no coinciden.")
            else:
                try:
                    password_validation.validate_password(p1, self.instance)
                except forms.ValidationError as e:
                    self.add_error("password1", e)
        return data

    def save(self, commit=True):
        user = super().save(commit=False)
        if self.cleaned_data.get("password1"):
            user.set_password(self.cleaned_data["password1"])
        if user.is_superuser:
            user.is_staff = True
        user.save()
        self.save_m2m()
        Employee.objects.filter(user=user).exclude(pk=getattr(self.cleaned_data.get("employee"), "pk", None)).update(
            user=None
        )
        if self.cleaned_data.get("employee"):
            emp = self.cleaned_data["employee"]
            emp.user = user
            emp.save(update_fields=["user"])
        return user


class RoleForm(BaseModelForm):
    class Meta:
        model = Role
        fields = ["name", "description"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for module in Module:
            initial = self.instance.level_for(module) if self.instance.pk else Level.NINGUNO
            self.fields[f"perm_{module.value}"] = forms.TypedChoiceField(
                label=module.label,
                choices=Level.choices,
                coerce=int,
                initial=initial,
                widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
            )

    def permission_fields(self):
        return [self[f"perm_{m.value}"] for m in Module]

    def save(self, commit=True):
        role = super().save(commit=True)
        for module in Module:
            level = self.cleaned_data[f"perm_{module.value}"]
            role.permissions.update_or_create(module=module.value, defaults={"level": level})
        return role


class CompanySettingsForm(BaseModelForm):
    class Meta:
        model = CompanySettings
        fields = "__all__"
        widgets = {"default_start_time": forms.TimeInput(format="%H:%M")}


class ProfileForm(BaseModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "email"]
