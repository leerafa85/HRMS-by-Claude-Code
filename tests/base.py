import datetime
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.core.management.commands.datos_demo import make_cuil
from apps.core.models import Role, User
from apps.empleados.models import Employee, SalaryAdjustment


class HRTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("inicializar", stdout=StringIO())
        cls.admin = User.objects.create_superuser("admin", "admin@test.com", "Admin1234!")
        cls.boss = cls.make_employee("1", "Jefa", "Equipo", 20111111, hire=datetime.date(2015, 3, 1))
        cls.emp = cls.make_employee("2", "Juan", "Pérez", 30222222, hire=datetime.date(2022, 1, 10), manager=cls.boss)
        cls.other = cls.make_employee("3", "Otra", "Persona", 33333333, hire=datetime.date(2020, 5, 5))
        cls.emp_user = cls.make_user("juan", cls.emp, "Empleado")
        cls.boss_user = cls.make_user("jefa", cls.boss, "Líder de equipo")
        cls.other_user = cls.make_user("otra", cls.other, "Empleado")

    @classmethod
    def make_employee(cls, number, first, last, dni, hire, manager=None, salary=None):
        e = Employee.objects.create(file_number=number, first_name=first, last_name=last, dni=str(dni),
                                    cuil=make_cuil(dni), hire_date=hire, manager=manager)
        if salary:
            SalaryAdjustment.objects.create(employee=e, effective_date=hire, new_salary=Decimal(salary))
        return e

    @classmethod
    def make_user(cls, username, employee, role_name=None):
        u = User.objects.create_user(username, password="Clave-Segura-123")
        if role_name:
            u.roles.add(Role.objects.get(name=role_name))
        employee.user = u
        employee.save(update_fields=["user"])
        return u
