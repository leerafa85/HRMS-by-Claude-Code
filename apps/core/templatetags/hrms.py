from django import template

from apps.core.formatting import format_ars, format_number
from apps.core.modules import Level

register = template.Library()


@register.filter
def ars(value):
    return format_ars(value)


@register.filter
def num(value, decimals=2):
    return format_number(value, int(decimals))


@register.filter
def can_view(user, module):
    return user.is_authenticated and user.can(module, Level.VER)


@register.filter
def can_edit(user, module):
    return user.is_authenticated and user.can(module, Level.EDITAR)


@register.filter
def can_admin(user, module):
    return user.is_authenticated and user.can(module, Level.ADMINISTRAR)


@register.filter
def get_item(d, key):
    return d.get(key) if hasattr(d, "get") else None


@register.simple_tag(takes_context=True)
def qs_replace(context, **kwargs):
    params = context["request"].GET.copy()
    for k, v in kwargs.items():
        params[k] = v
    return params.urlencode()


@register.inclusion_tag("partials/field.html")
def field(bound_field, col="col-md-6"):
    return {"field": bound_field, "col": col}


@register.filter
def widget_type(bound_field):
    return bound_field.field.widget.__class__.__name__.lower()
