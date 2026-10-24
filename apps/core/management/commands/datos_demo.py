"""Genera datos ficticios para probar el sistema. NO usar en producción con datos reales."""

import datetime
import random
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction


def make_cuil(dni, prefix="20"):
    base = f"{prefix}{int(dni):08d}"
    weights = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2]
    check = 11 - sum(int(d) * w for d, w in zip(base, weights, strict=True)) % 11
    if check == 10:  # en ese caso se usa el prefijo 23
        return make_cuil(dni, "23")
    return base + str({11: 0}.get(check, check))


PEOPLE = [
    ("Laura", "Gómez", "F", "Dirección", "Gerente General", None, 2008),
    ("Martín", "Fernández", "M", "Recursos Humanos", "Jefe de RRHH", 0, 2014),
    ("Sofía", "Rodríguez", "F", "Recursos Humanos", "Analista de RRHH", 1, 2021),
    ("Diego", "López", "M", "Administración", "Jefe de Administración", 0, 2012),
    ("Valentina", "Martínez", "F", "Administración", "Analista contable", 3, 2019),
    ("Lucas", "García", "M", "Comercial", "Jefe Comercial", 0, 2016),
    ("Camila", "Pérez", "F", "Comercial", "Vendedora", 5, 2022),
    ("Juan Pablo", "Sánchez", "M", "Comercial", "Vendedor", 5, 2024),
    ("Florencia", "Romero", "F", "Operaciones", "Jefa de Operaciones", 0, 2010),
    ("Matías", "Díaz", "M", "Operaciones", "Operario", 8, 2018),
    ("Agustina", "Álvarez", "F", "Operaciones", "Operaria", 8, 2023),
    ("Nicolás", "Torres", "M", "Sistemas", "Desarrollador", 0, 2020),
]


class Command(BaseCommand):
    help = "Carga datos de demostración (empleados, licencias, asistencia, reclutamiento)."

    @transaction.atomic
    def handle(self, *args, **options):
        from apps.anuncios.models import Announcement
        from apps.asistencia.models import Absence, Overtime, Tardiness
        from apps.core.models import Role, User
        from apps.empleados.models import (
            Department,
            Employee,
            Location,
            Position,
            SalaryAdjustment,
        )
        from apps.licencias.models import LeaveRequest, LeaveType
        from apps.licencias.services import generate_vacation_balances
        from apps.reclutamiento.models import Application, Candidate, JobOpening

        if Employee.objects.exists():
            self.stdout.write(self.style.WARNING("Ya hay empleados cargados; no se generan datos demo."))
            return
        random.seed(42)
        today = datetime.date.today()
        caba = Location.objects.create(name="Casa central", address="Av. Corrientes 1234", city="CABA", province="CABA")
        cba = Location.objects.create(name="Sucursal Córdoba", address="Bv. San Juan 500", city="Córdoba", province="CB")
        depts = {n: Department.objects.create(name=n) for n in {p[3] for p in PEOPLE}}
        employees = []
        for i, (first, last, gender, dept, pos, manager_idx, year) in enumerate(PEOPLE):
            dni = 20_000_000 + i * 1_234_567
            position, _ = Position.objects.get_or_create(name=pos, department=depts[dept])
            e = Employee.objects.create(
                file_number=str(i + 1), first_name=first, last_name=last, gender=gender, dni=str(dni),
                cuil=make_cuil(dni, "27" if gender == "F" else "20"),
                birth_date=datetime.date(1975 + i * 2, (i % 12) + 1, 10 + i),
                hire_date=datetime.date(year, (i % 12) + 1, 1), department=depts[dept], position=position,
                location=cba if dept == "Operaciones" else caba,
                manager=employees[manager_idx] if manager_idx is not None else None,
                work_email=f"{first.split()[0].lower()}.{last.lower()}@empresa-demo.com.ar".replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u"),
                mobile=f"11-5{i:03d}-{1000 + i}", union_agreement="130/75 Comercio" if dept != "Dirección" else "",
                category="Administrativo B" if dept != "Operaciones" else "Maestranza A", health_insurance="OSECAC",
                status=Employee.Status.PRUEBA if year == today.year else Employee.Status.ACTIVO,
            )
            base = Decimal(random.randint(900, 2500) * 1000)
            SalaryAdjustment.objects.create(employee=e, effective_date=datetime.date(today.year, 1, 1), new_salary=base,
                                            reason=SalaryAdjustment.Reason.PARITARIA)
            SalaryAdjustment.objects.create(employee=e, effective_date=datetime.date(today.year, 7, 1),
                                            new_salary=(base * Decimal("1.12")).quantize(Decimal("0.01")),
                                            reason=SalaryAdjustment.Reason.PARITARIA, notes="Paritaria 2.º semestre")
            employees.append(e)
        for d in depts.values():
            head = next((e for e in employees if e.department == d and e.position.name.startswith("Jef")), None)
            if head:
                d.head = head
                d.save()

        from apps.empleados.models import SalaryAdjustmentPlan

        plans = [
            dict(frequency_months=3, reference="calendario", start_month=1, method="ipc"),
            dict(frequency_months=1, reference="calendario", start_month=1, method="porcentaje", percent=Decimal("2.5")),
            dict(frequency_months=6, reference="ingreso", method="monto", amount=Decimal("150000")),
            dict(frequency_months=12, reference="ingreso", method="porcentaje", percent=Decimal("30")),
        ]
        for i, e in enumerate(employees[:-2]):
            SalaryAdjustmentPlan.objects.create(employee=e, **plans[i % len(plans)])

        generate_vacation_balances(today.year)
        vac = LeaveType.objects.get(code="vacaciones")
        sick = LeaveType.objects.get(code="enfermedad")
        LeaveRequest.objects.create(employee=employees[6], leave_type=vac, start_date=today + datetime.timedelta(days=40),
                                    end_date=today + datetime.timedelta(days=46), reason="Viaje familiar")
        LeaveRequest.objects.create(employee=employees[9], leave_type=sick, start_date=today - datetime.timedelta(days=1),
                                    end_date=today + datetime.timedelta(days=1), status=LeaveRequest.Status.APROBADA)
        LeaveRequest.objects.create(employee=employees[4], leave_type=vac, start_date=today - datetime.timedelta(days=60),
                                    end_date=today - datetime.timedelta(days=47), status=LeaveRequest.Status.APROBADA)
        for e in employees[6:11]:
            Tardiness.objects.create(employee=e, date=today - datetime.timedelta(days=random.randint(1, 20)),
                                     arrival_time=datetime.time(9, random.randint(10, 50)))
        Absence.objects.create(employee=employees[7], date=today - datetime.timedelta(days=5),
                               reason=Absence.Reason.SIN_AVISO, justified=False, notified=False)
        Absence.objects.create(employee=employees[10], date=today - datetime.timedelta(days=8),
                               reason=Absence.Reason.TRAMITE, justified=True, paid=True)
        for e in employees[9:11]:
            Overtime.objects.create(employee=e, date=today - datetime.timedelta(days=3), hours=Decimal("2.5"),
                                    reason="Inventario", status=Overtime.Status.APROBADA)
        Overtime.objects.create(employee=employees[11], date=today - datetime.timedelta(days=2), hours=Decimal(3),
                                reason="Pase a producción")

        job = JobOpening.objects.create(
            title="Vendedor/a de salón", department=depts["Comercial"], location=caba, vacancies=2,
            description="Buscamos vendedores/as para atención al público en nuestra casa central.",
            requirements="Secundario completo. Experiencia en ventas de 1 año.", benefits="Obra social, capacitación.",
            salary_min=Decimal(1100000), salary_max=Decimal(1400000), status=JobOpening.Status.ABIERTA, published=True,
        )
        for i, (f, ln) in enumerate([("Ana", "Ruiz"), ("Pedro", "Molina"), ("Carla", "Sosa"), ("Tomás", "Herrera")]):
            c = Candidate.objects.create(first_name=f, last_name=ln, email=f"{f.lower()}.{ln.lower()}@mail-demo.com",
                                         source=random.choice(Candidate.Source.values), consent=True)
            Application.objects.create(job=job, candidate=c, stage=Application.PIPELINE[i])

        Announcement.objects.create(title="¡Bienvenidos al nuevo sistema de RRHH!", pinned=True,
                                    body="Desde ahora podés pedir tus vacaciones y licencias y consultar tu legajo desde acá.")

        emp_role = Role.objects.filter(name="Empleado").first()
        lead_role = Role.objects.filter(name="Líder de equipo").first()
        rrhh_role = Role.objects.filter(name="Analista RRHH").first()
        for idx, username, role in [(1, "rrhh", rrhh_role), (5, "jefe", lead_role), (6, "empleado", emp_role)]:
            u = User.objects.create_user(username=username, password="Demo1234!", first_name=employees[idx].first_name,
                                         last_name=employees[idx].last_name, email=employees[idx].work_email)
            if role:
                u.roles.add(role)
            employees[idx].user = u
            employees[idx].save(update_fields=["user"])
        self.stdout.write(self.style.SUCCESS(
            "Datos demo cargados. Usuarios de prueba (contraseña Demo1234!): rrhh, jefe, empleado."
        ))
