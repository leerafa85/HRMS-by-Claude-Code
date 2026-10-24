import datetime
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from apps.core.formatting import format_ars
from apps.core.validators import validate_cuil
from apps.licencias import lct

from .base import HRTestCase


class FormattingTests(SimpleTestCase):
    def test_pesos(self):
        self.assertEqual(format_ars(Decimal("1234567.891")), "$ 1.234.567,89")
        self.assertEqual(format_ars(0), "$ 0,00")
        self.assertEqual(format_ars(-1500), "-$ 1.500,00")
        self.assertEqual(format_ars(None), "—")

    def test_cuil(self):
        validate_cuil("20-11111111-2")
        with self.assertRaises(ValidationError):
            validate_cuil("20-11111111-3")
        with self.assertRaises(ValidationError):
            validate_cuil("123")


class LCTTests(SimpleTestCase):
    def test_vacation_scale_art_150(self):
        self.assertEqual([lct.vacation_days_for_seniority(y) for y in (0, 4, 5, 9, 10, 19, 20, 30)],
                         [14, 14, 21, 21, 28, 28, 35, 35])

    def test_business_days_skip_weekend_and_holidays(self):
        # Lunes 2026-02-16 y martes 17 son Carnaval
        start, end = datetime.date(2026, 2, 13), datetime.date(2026, 2, 20)
        holidays = {datetime.date(2026, 2, 16), datetime.date(2026, 2, 17)}
        self.assertEqual(lct.count_days(start, end, business_days=True, holidays=holidays), 4)
        self.assertEqual(lct.count_days(start, end), 8)

    def test_overtime_rate(self):
        self.assertEqual(lct.overtime_rate(datetime.date(2026, 10, 21)), 50)  # miércoles
        self.assertEqual(lct.overtime_rate(datetime.date(2026, 10, 25)), 100)  # domingo
        self.assertEqual(lct.overtime_rate(datetime.date(2026, 10, 24), datetime.time(14)), 100)  # sábado tarde
        self.assertEqual(lct.overtime_rate(datetime.date(2026, 10, 24), datetime.time(9)), 50)  # sábado mañana
        self.assertEqual(lct.overtime_rate(datetime.date(2026, 10, 21), is_holiday=True), 100)

    def test_sick_leave_art_208(self):
        self.assertEqual(lct.sick_leave_months(3, False), 3)
        self.assertEqual(lct.sick_leave_months(6, True), 12)


class EntitlementTests(HRTestCase):
    def test_entitlement_by_seniority(self):
        self.assertEqual(lct.vacation_entitlement(self.boss, 2026), 28)  # 11 años al 31/12/2026
        self.assertEqual(lct.vacation_entitlement(self.emp, 2026), 14)

    def test_entitlement_art_153_partial_year(self):
        late = self.make_employee("9", "Nuevo", "Ingreso", 40999999, hire=datetime.date(2026, 10, 1))
        days = lct.vacation_entitlement(late, 2026)
        self.assertLess(days, 14)
        self.assertEqual(days, 3)  # ~65 días hábiles / 20

    def test_holidays_seeded(self):
        from apps.licencias.models import Holiday

        self.assertTrue(Holiday.objects.filter(date=datetime.date(2026, 7, 9)).exists())
        self.assertEqual(Holiday.objects.filter(date__year=2026).count(), 19)
