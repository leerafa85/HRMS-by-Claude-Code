"""Reportes de RRHH. Cada reporte devuelve encabezados, filas y (opcional) datos de gráfico,
y puede exportarse a Excel con ?exportar=1."""

import datetime
from collections import Counter, OrderedDict
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q, Sum
from django.http import Http404
from django.shortcuts import render

from apps.asistencia.models import Absence, Overtime, Tardiness
from apps.core.dates import MESES
from apps.core.formatting import format_ars
from apps.core.modules import Module
from apps.empleados.models import Employee
from apps.licencias.models import LeaveBalance, LeaveRequest, LeaveType

from .excel import excel_response


def _active():
    return Employee.objects.exclude(status=Employee.Status.DESVINCULADO)


def _year(request):
    try:
        return int(request.GET.get("anio", datetime.date.today().year))
    except ValueError:
        return datetime.date.today().year


def headcount(request):
    group = request.GET.get("por", "department")
    labels = {"department": "Área", "location": "Sede", "contract_type": "Modalidad", "position": "Puesto",
              "gender": "Género", "union_agreement": "Convenio"}
    if group not in labels:
        group = "department"
    counter = Counter()
    for e in _active().select_related("department", "location", "position"):
        if group in ("contract_type", "gender"):
            key = getattr(e, f"get_{group}_display")() or "Sin dato"
        else:
            key = str(getattr(e, group) or "Sin asignar")
        counter[key] += 1
    total = sum(counter.values()) or 1
    rows = [[k, v, f"{v * 100 / total:.1f} %".replace(".", ",")] for k, v in counter.most_common()]
    return {
        "headers": [labels[group], "Empleados", "%"],
        "rows": rows,
        "chart": {"type": "doughnut", "labels": [r[0] for r in rows], "values": [r[1] for r in rows]},
        "options": {"por": labels},
        "summary": f"Dotación activa: {sum(counter.values())}",
    }


def turnover(request):
    year = _year(request)
    rows = []
    hires_total = exits_total = 0
    for m in range(1, 13):
        first = datetime.date(year, m, 1)
        last = (first.replace(day=28) + datetime.timedelta(days=4)).replace(day=1) - datetime.timedelta(days=1)
        hires = Employee.objects.filter(hire_date__range=(first, last)).count()
        exits = Employee.objects.filter(termination_date__range=(first, last)).count()
        hc_end = Employee.objects.filter(hire_date__lte=last).filter(
            Q(termination_date__isnull=True) | Q(termination_date__gt=last)
        ).count()
        rate = exits * 100 / hc_end if hc_end else 0
        hires_total += hires
        exits_total += exits
        rows.append([MESES[m - 1], hires, exits, hc_end, f"{rate:.1f} %".replace(".", ",")])
    reasons = Employee.objects.filter(termination_date__year=year).values("termination_reason").annotate(n=Count("id"))
    reason_txt = ", ".join(
        f"{dict(Employee.TerminationReason.choices).get(r['termination_reason'], 'Sin motivo')}: {r['n']}" for r in reasons
    )
    return {
        "headers": ["Mes", "Altas", "Bajas", "Dotación a fin de mes", "Rotación mensual"],
        "rows": rows,
        "chart": {"type": "bar", "labels": MESES, "series": [
            {"label": "Altas", "values": [r[1] for r in rows]}, {"label": "Bajas", "values": [r[2] for r in rows]}]},
        "summary": f"Año {year}: {hires_total} altas, {exits_total} bajas. Motivos de egreso: {reason_txt or '—'}",
        "year_filter": True,
    }


def absenteeism(request):
    year = _year(request)
    types = list(LeaveType.objects.filter(active=True).exclude(kind=LeaveType.Kind.VACACIONES))
    data = OrderedDict((m, {"abs": 0, **{t.pk: Decimal(0) for t in types}}) for m in range(1, 13))
    for r in Absence.objects.filter(date__year=year).values("date__month").annotate(n=Count("id")):
        data[r["date__month"]]["abs"] = r["n"]
    for lr in LeaveRequest.objects.filter(status=LeaveRequest.Status.APROBADA, start_date__year=year, leave_type__in=types):
        data[lr.start_date.month][lr.leave_type_id] += lr.days
    rows = [[MESES[m - 1], d["abs"], *[d[t.pk] for t in types]] for m, d in data.items()]
    return {
        "headers": ["Mes", "Inasistencias", *[t.name for t in types]],
        "rows": rows,
        "chart": {"type": "bar", "labels": MESES, "series": [{"label": "Inasistencias", "values": [r[1] for r in rows]}]},
        "summary": "Días de licencia aprobados (excepto vacaciones) e inasistencias registradas por mes.",
        "year_filter": True,
    }


def tardiness(request):
    year = _year(request)
    qs = (Tardiness.objects.filter(date__year=year).values("employee__file_number", "employee__last_name",
                                                            "employee__first_name")
          .annotate(n=Count("id"), mins=Sum("minutes_late"), injust=Count("id", filter=Q(justified=False)))
          .order_by("-n"))
    rows = [[r["employee__file_number"], f"{r['employee__last_name']}, {r['employee__first_name']}", r["n"],
             r["injust"], r["mins"]] for r in qs]
    return {"headers": ["Legajo", "Empleado", "Llegadas tarde", "Injustificadas", "Minutos totales"], "rows": rows,
            "year_filter": True}


def overtime(request):
    year = _year(request)
    qs = (Overtime.objects.filter(date__year=year, status=Overtime.Status.APROBADA)
          .values("employee__file_number", "employee__last_name", "employee__first_name")
          .annotate(h50=Sum("hours", filter=Q(rate=50, compensation="pago")),
                    h100=Sum("hours", filter=Q(rate=100, compensation="pago")),
                    banco=Sum("hours", filter=Q(compensation="banco")))
          .order_by("employee__last_name"))
    rows = [[r["employee__file_number"], f"{r['employee__last_name']}, {r['employee__first_name']}",
             r["h50"] or 0, r["h100"] or 0, r["banco"] or 0] for r in qs]
    return {"headers": ["Legajo", "Empleado", "Horas al 50 %", "Horas al 100 %", "Horas a banco"], "rows": rows,
            "year_filter": True, "summary": "Solo horas extras aprobadas."}


def vacations(request):
    year = _year(request)
    vt = LeaveType.objects.filter(kind=LeaveType.Kind.VACACIONES).first()
    rows = []
    for b in LeaveBalance.objects.filter(leave_type=vt, year=year).select_related("employee"):
        rows.append([b.employee.file_number, str(b.employee), b.employee.seniority_years(datetime.date(year, 12, 31)),
                     b.entitled, b.carried_over + b.adjustment, b.used, b.pending, b.available])
    return {"headers": ["Legajo", "Empleado", "Antigüedad al 31/12", "Corresponden", "Arrastre/ajuste", "Gozados",
                        "Pendientes", "Disponibles"],
            "rows": rows, "year_filter": True,
            "summary": "Si no aparecen datos, generá los saldos del período en Tiempo libre → Saldos."}


def payroll_mass(request):
    if not request.user.can(Module.SALARIOS):
        raise PermissionDenied
    by_dept = OrderedDict()
    for e in _active().select_related("department"):
        sal = e.current_salary
        key = str(e.department or "Sin área")
        d = by_dept.setdefault(key, {"n": 0, "total": Decimal(0), "sin": 0})
        d["n"] += 1
        if sal:
            d["total"] += sal
        else:
            d["sin"] += 1
    rows = [[k, v["n"], v["total"], (v["total"] / (v["n"] - v["sin"])) if v["n"] - v["sin"] else Decimal(0), v["sin"]]
            for k, v in by_dept.items()]
    total = sum((r[2] for r in rows), Decimal(0))
    return {"headers": ["Área", "Empleados", "Masa salarial bruta", "Promedio", "Sin salario cargado"], "rows": rows,
            "money_cols": [2, 3], "summary": f"Masa salarial bruta mensual total: {format_ars(total)}",
            "chart": {"type": "bar", "labels": [r[0] for r in rows],
                      "series": [{"label": "Masa salarial", "values": [float(r[2]) for r in rows]}]}}


def demographics(request):
    bands_age = Counter()
    bands_sen = Counter()
    for e in _active():
        a = e.age
        if a is None:
            bands_age["Sin dato"] += 1
        else:
            bands_age["< 25" if a < 25 else "25-34" if a < 35 else "35-44" if a < 45 else "45-54" if a < 55 else "55+"] += 1
        s = e.seniority_years()
        bands_sen["< 1 año" if s < 1 else "1-4 años" if s < 5 else "5-9 años" if s < 10 else "10-19 años" if s < 20 else "20+ años"] += 1
    rows = [["Edad", k, v] for k, v in sorted(bands_age.items())] + [["Antigüedad", k, v] for k, v in sorted(bands_sen.items())]
    return {"headers": ["Dimensión", "Rango", "Empleados"], "rows": rows}


REPORTS = OrderedDict([
    ("dotacion", ("Dotación", "Empleados activos por área, sede, modalidad, género o convenio.", headcount, Module.EMPLEADOS)),
    ("rotacion", ("Altas, bajas y rotación", "Movimientos mensuales de personal y motivos de egreso.", turnover, Module.EMPLEADOS)),
    ("demografia", ("Edad y antigüedad", "Distribución de la dotación por rangos.", demographics, Module.EMPLEADOS)),
    ("ausentismo", ("Ausentismo", "Inasistencias y días de licencia por mes.", absenteeism, Module.ASISTENCIA)),
    ("tardanzas", ("Llegadas tarde", "Ranking anual de tardanzas por empleado.", tardiness, Module.ASISTENCIA)),
    ("horas-extras", ("Horas extras", "Horas extras aprobadas por empleado y recargo.", overtime, Module.ASISTENCIA)),
    ("vacaciones", ("Vacaciones", "Saldos de vacaciones por empleado.", vacations, Module.LICENCIAS)),
    ("masa-salarial", ("Masa salarial", "Salarios brutos vigentes por área (en pesos).", payroll_mass, Module.SALARIOS)),
])


@login_required
def index(request):
    if not request.user.can(Module.REPORTES):
        raise PermissionDenied
    items = [{"slug": k, "title": v[0], "desc": v[1]} for k, v in REPORTS.items() if request.user.can(v[3])]
    return render(request, "reportes/index.html", {"reports": items})


@login_required
def report(request, slug):
    if slug not in REPORTS:
        raise Http404
    title, desc, fn, module = REPORTS[slug]
    if not (request.user.can(Module.REPORTES) and request.user.can(module)):
        raise PermissionDenied
    data = fn(request)
    if request.GET.get("exportar"):
        return excel_response(slug, title, data["headers"], data["rows"], data.get("money_cols"))
    money = set(data.get("money_cols") or [])
    display_rows = [[format_ars(v) if i in money else v for i, v in enumerate(r)] for r in data["rows"]]
    return render(request, "reportes/report.html", {
        "title": title, "desc": desc, "data": data, "rows": display_rows, "slug": slug,
        "year": _year(request), "years": range(datetime.date.today().year + 1, datetime.date.today().year - 8, -1),
    })
