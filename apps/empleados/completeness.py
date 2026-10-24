"""Datos clave del legajo que conviene completar.

Para cambiar qué se pide o si es obligatorio/recomendado, editá la lista RULES:
(clave, texto, nivel, función que devuelve True si falta el dato).
"""

from .models import EmployeeDocument, PaymentMethod

OBLIGATORIO = "obligatorio"
RECOMENDADO = "recomendado"


def _no_salary(e, ctx):
    return e.pk not in ctx["with_salary"]


def _no_emergency(e, ctx):
    return e.pk not in ctx["with_emergency"]


def _no_doc(category):
    def check(e, ctx):
        return (e.pk, category) not in ctx["docs"]
    return check


RULES = [
    # Obligatorios: necesarios para pagar el sueldo, contactar a la persona o cumplir obligaciones legales.
    ("nacimiento", "Fecha de nacimiento", OBLIGATORIO, lambda e, c: not e.birth_date),
    ("domicilio", "Domicilio", OBLIGATORIO, lambda e, c: not (e.address and e.city)),
    ("telefono", "Teléfono o celular", OBLIGATORIO, lambda e, c: not (e.mobile or e.phone)),
    ("email", "Email (laboral o personal)", OBLIGATORIO, lambda e, c: not (e.work_email or e.personal_email)),
    ("area_puesto", "Área y puesto", OBLIGATORIO, lambda e, c: not (e.department_id and e.position_id)),
    ("salario", "Salario cargado", OBLIGATORIO, _no_salary),
    ("forma_pago", "Forma de pago del sueldo", OBLIGATORIO, lambda e, c: not e.payment_method),
    ("datos_bancarios", "Banco y CBU/CVU (cobra por transferencia)", OBLIGATORIO,
     lambda e, c: e.payment_method == PaymentMethod.TRANSFERENCIA and not (e.bank and e.cbu)),
    ("acreditacion", "Días de acreditación del sueldo", OBLIGATORIO, lambda e, c: not e.pay_day_from),
    ("obra_social", "Obra social", OBLIGATORIO, lambda e, c: not e.health_insurance),
    ("emergencia", "Contacto de emergencia", OBLIGATORIO, _no_emergency),
    # Recomendados: mejoran la gestión, pero no frenan la operación.
    ("dni_doc", "Copia del DNI en documentos", RECOMENDADO, _no_doc(EmployeeDocument.Category.DNI)),
    ("alta_doc", "Constancia de alta temprana en documentos", RECOMENDADO, _no_doc(EmployeeDocument.Category.ALTA)),
    ("jefe", "Jefe directo", RECOMENDADO, lambda e, c: not e.manager_id and e.pk not in c["heads"]),
    ("estado_civil", "Estado civil", RECOMENDADO, lambda e, c: not e.marital_status),
    ("esquema_ajuste", "Esquema de ajuste salarial", RECOMENDADO, lambda e, c: e.pk not in c["with_plan"]),
    ("usuario", "Usuario del sistema (autogestión)", RECOMENDADO, lambda e, c: not e.user_id),
]


def _context(employees):
    from .models import Department, EmergencyContact, Employee, SalaryAdjustment, SalaryAdjustmentPlan

    ids = [e.pk for e in employees]
    return {
        "with_salary": set(SalaryAdjustment.objects.filter(employee_id__in=ids).values_list("employee_id", flat=True)),
        "with_emergency": set(EmergencyContact.objects.filter(employee_id__in=ids).values_list("employee_id", flat=True)),
        "with_plan": set(SalaryAdjustmentPlan.objects.filter(employee_id__in=ids, active=True)
                         .values_list("employee_id", flat=True)),
        "docs": set(EmployeeDocument.objects.filter(employee_id__in=ids).values_list("employee_id", "category")),
        # Sin jefe directo es razonable para quien encabeza un área o tiene gente a cargo.
        "heads": set(Department.objects.exclude(head__isnull=True).values_list("head_id", flat=True))
        | set(Employee.objects.exclude(manager__isnull=True).values_list("manager_id", flat=True)),
    }


def missing_fields(employees):
    """Devuelve [(empleado, [(clave, texto, nivel)])] solo de quienes tienen datos faltantes."""
    employees = list(employees)
    ctx = _context(employees)
    out = []
    for e in employees:
        missing = [(key, label, level) for key, label, level, check in RULES if check(e, ctx)]
        if missing:
            missing.sort(key=lambda m: m[2] != OBLIGATORIO)
            out.append((e, missing))
    out.sort(key=lambda item: (-sum(m[2] == OBLIGATORIO for m in item[1]), item[0].last_name))
    return out
