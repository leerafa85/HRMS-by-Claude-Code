"""Vistas CRUD genéricas con control de acceso por módulo y auditoría.

Cada módulo define sus listados declarando columnas en lugar de escribir un
template por entidad, así mantener y extender el sistema es más simple.
"""

import datetime
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import ProtectedError, Q
from django.shortcuts import redirect
from django.urls import NoReverseMatch, reverse
from django.utils.formats import date_format
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    UpdateView,
)

from .formatting import format_ars
from .models import AuditLog
from .modules import Level


class ModuleRequiredMixin(LoginRequiredMixin):
    module = None
    required_level = Level.VER

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if self.module and not request.user.can(self.module, self.required_level):
            raise PermissionDenied("No tenés permisos para acceder a este módulo.")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        if self.module:
            ctx["can_edit"] = user.can(self.module, Level.EDITAR)
            ctx["can_admin"] = user.can(self.module, Level.ADMINISTRAR)
        return ctx


def resolve_attr(obj, path):
    value = obj
    for part in path.split("."):
        if value is None:
            return None
        display = getattr(value, f"get_{part}_display", None)
        value = display() if display else getattr(value, part, None)
        if callable(value) and not hasattr(value, "all"):
            value = value()
    return value


def format_cell(value, kind=None):
    if value is None or value == "":
        return "—"
    if kind == "money":
        return format_ars(value)
    if isinstance(value, bool):
        return "Sí" if value else "No"
    if isinstance(value, datetime.datetime):
        return date_format(value, "d/m/Y H:i")
    if isinstance(value, datetime.date):
        return date_format(value, "d/m/Y")
    if isinstance(value, Decimal):
        return f"{value:.2f}".replace(".", ",")
    if hasattr(value, "all"):
        return ", ".join(str(v) for v in value.all()) or "—"
    return str(value)


class Column:
    def __init__(self, label, attr, kind=None, link=False, badge=None, badge_key=None):
        self.label = label
        self.attr = attr
        self.kind = kind
        self.link = link
        self.badge = badge  # dict valor -> clase de bootstrap
        self.badge_key = badge_key  # atributo con el valor que define el color (si difiere de attr)

    def render(self, obj):
        raw = resolve_attr(obj, self.attr) if isinstance(self.attr, str) else self.attr(obj)
        return format_cell(raw, self.kind)

    def badge_class(self, obj):
        if not self.badge:
            return None
        key = self.badge_key or (self.attr.split(".")[-1] if isinstance(self.attr, str) else None)
        raw = getattr(obj, key, None) if key else None
        return self.badge.get(raw, "secondary")


class UrlNamesMixin:
    """Arma los nombres de URL a partir de `url_prefix` (p.ej. 'empleados:departamento')."""

    url_prefix = None

    def url_for(self, action, obj=None):
        try:
            if obj is None:
                return reverse(f"{self.url_prefix}_{action}")
            return reverse(f"{self.url_prefix}_{action}", args=[obj.pk])
        except NoReverseMatch:
            return None


class HRListView(ModuleRequiredMixin, UrlNamesMixin, ListView):
    template_name = "crud/list.html"
    paginate_by = 25
    columns = []
    search_fields = []
    filters = []  # lista de (param, campo_orm, etiqueta, opciones[(valor, etiqueta)])
    title = ""
    create_label = "Nuevo"
    extra_actions = []  # [(etiqueta, url_name, icono, nivel requerido opcional)]
    printable = False  # habilita PDF e impresión del listado completo filtrado

    def get(self, request, *args, **kwargs):
        if self.printable and request.GET.get("formato") in ("pdf", "imprimir"):
            from apps.reportes.documents import Document, Table, document_response

            qs = self.get_queryset()
            rows = [[col.render(obj) for col in self.columns] for obj in qs]
            title = self.title or self.model._meta.verbose_name_plural.capitalize()
            doc = Document(title=title, subtitle=self.print_subtitle(len(rows)))
            doc.add(Table([c.label for c in self.columns], rows, footer=self.print_footer(qs)))
            return document_response(request, doc, title)
        return super().get(request, *args, **kwargs)

    def print_subtitle(self, count):
        parts = []
        for param, _field, label, options in self.get_filters():
            value = self.request.GET.get(param)
            if value:
                text = next((str(lab) for val, lab in options if str(val) == value), value)
                parts.append(f"{label}: {text}")
        q = self.request.GET.get("q", "").strip()
        if q:
            parts.append(f"Búsqueda: «{q}»")
        lines = ["Filtros: " + " · ".join(parts)] if parts else ["Sin filtros (todos los registros)"]
        lines.append(f"Registros: {count}")
        return lines

    def print_footer(self, queryset):
        """Fila de totales opcional para el PDF/impresión."""
        return None

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.GET.get("q", "").strip()
        if q and self.search_fields:
            cond = Q()
            for f in self.search_fields:
                cond |= Q(**{f"{f}__icontains": q})
            qs = qs.filter(cond)
        for param, field, _label, _opts in self.get_filters():
            val = self.request.GET.get(param)
            if field and val not in (None, ""):  # field=None: filtro que resuelve la vista
                qs = qs.filter(**{field: val})
        return qs

    def get_filters(self):
        return [(p, f, lab, o() if callable(o) else o) for p, f, lab, o in self.filters]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        has_detail = self.url_for("detail", _Dummy) is not None
        rows = []
        for obj in ctx["object_list"]:
            cells = []
            for col in self.columns:
                cells.append({"value": col.render(obj), "badge": col.badge_class(obj), "link": col.link,
                              "nowrap": col.kind == "money"})
            rows.append(
                {
                    "obj": obj,
                    "cells": cells,
                    "detail_url": self.url_for("detail", obj) if has_detail else None,
                    "update_url": self.url_for("update", obj) if ctx.get("can_edit") else None,
                    "delete_url": self.url_for("delete", obj) if ctx.get("can_admin") else None,
                }
            )
        params = self.request.GET.copy()
        params.pop("page", None)
        ctx.update(
            {
                "title": self.title or self.model._meta.verbose_name_plural.capitalize(),
                "columns": self.columns,
                "rows": rows,
                "create_url": self.url_for("create") if ctx.get("can_edit") else None,
                "create_label": self.create_label,
                "export_url": self.url_for("export"),
                "printable": self.printable,
                "search_enabled": bool(self.search_fields),
                "q": self.request.GET.get("q", ""),
                "filter_defs": [
                    {"param": p, "label": lab, "options": o, "value": self.request.GET.get(p, "")}
                    for p, _f, lab, o in self.get_filters()
                ],
                "querystring": params.urlencode(),
                "extra_actions": [
                    (a[0], reverse(a[1]), a[2])
                    for a in self.extra_actions
                    if len(a) < 4 or self.request.user.can(self.module, a[3])
                ],
            }
        )
        return ctx


class _Dummy:
    pk = 0


class AuditFormMixin:
    success_message = "Los datos se guardaron correctamente."

    def form_valid(self, form):
        is_new = form.instance.pk is None
        if is_new and hasattr(form.instance, "created_by_id") and not form.instance.created_by_id:
            form.instance.created_by = self.request.user
        response = super().form_valid(form)
        AuditLog.log(
            self.request.user,
            AuditLog.Action.CREATE if is_new else AuditLog.Action.UPDATE,
            self.object,
        )
        messages.success(self.request, self.success_message)
        return response


class HRCreateView(ModuleRequiredMixin, UrlNamesMixin, AuditFormMixin, CreateView):
    template_name = "crud/form.html"
    required_level = Level.EDITAR
    title = ""

    def get_success_url(self):
        return self.url_for("detail", self.object) or self.url_for("list")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["title"] = self.title or f"Nuevo {self.model._meta.verbose_name}"
        ctx["cancel_url"] = self.url_for("list")
        return ctx


class HRUpdateView(ModuleRequiredMixin, UrlNamesMixin, AuditFormMixin, UpdateView):
    template_name = "crud/form.html"
    required_level = Level.EDITAR
    title = ""

    def get_success_url(self):
        return self.url_for("detail", self.object) or self.url_for("list")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["title"] = self.title or f"Editar {self.model._meta.verbose_name}"
        ctx["cancel_url"] = self.url_for("detail", self.object) or self.url_for("list")
        return ctx


class HRDetailView(ModuleRequiredMixin, UrlNamesMixin, DetailView):
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["update_url"] = self.url_for("update", self.object) if ctx.get("can_edit") else None
        ctx["delete_url"] = self.url_for("delete", self.object) if ctx.get("can_admin") else None
        ctx["list_url"] = self.url_for("list")
        return ctx


class HRDeleteView(ModuleRequiredMixin, UrlNamesMixin, DeleteView):
    template_name = "crud/confirm_delete.html"
    required_level = Level.ADMINISTRAR

    def get_success_url(self):
        return self.success_url or self.url_for("list")

    def form_valid(self, form):
        obj = self.get_object()
        desc = str(obj)
        try:
            response = super().form_valid(form)
        except ProtectedError:
            messages.error(self.request, "No se puede eliminar porque tiene registros asociados.")
            return redirect(self.url_for("list"))
        AuditLog.log(self.request.user, AuditLog.Action.DELETE, obj, desc)
        messages.success(self.request, f"Se eliminó «{desc}».")
        return response

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["cancel_url"] = self.url_for("list")
        return ctx
