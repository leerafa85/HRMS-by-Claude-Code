import os

from django.conf import settings
from django.core.exceptions import ValidationError

DOCUMENT_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".webp", ".doc", ".docx", ".xls", ".xlsx", ".odt", ".ods", ".txt"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def _check_size(f):
    limit = settings.HRMS_MAX_UPLOAD_MB * 1024 * 1024
    if f.size and f.size > limit:
        raise ValidationError(f"El archivo supera el máximo de {settings.HRMS_MAX_UPLOAD_MB} MB.")


def validate_document(f):
    ext = os.path.splitext(f.name)[1].lower()
    if ext not in DOCUMENT_EXTENSIONS:
        raise ValidationError(
            "Tipo de archivo no permitido. Formatos aceptados: " + ", ".join(sorted(DOCUMENT_EXTENSIONS))
        )
    _check_size(f)


def validate_image(f):
    ext = os.path.splitext(f.name)[1].lower()
    if ext not in IMAGE_EXTENSIONS:
        raise ValidationError("La imagen debe ser JPG, PNG o WEBP.")
    _check_size(f)


def validate_cuil(value):
    """Valida CUIT/CUIL con dígito verificador (acepta con o sin guiones)."""
    digits = "".join(c for c in value if c.isdigit())
    if len(digits) != 11:
        raise ValidationError("El CUIL/CUIT debe tener 11 dígitos.")
    weights = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2]
    total = sum(int(d) * w for d, w in zip(digits[:10], weights, strict=True))
    check = 11 - (total % 11)
    check = {11: 0, 10: 9}.get(check, check)
    if check != int(digits[10]):
        raise ValidationError("El CUIL/CUIT no es válido (dígito verificador incorrecto).")


def validate_cbu(value):
    digits = "".join(c for c in value if c.isdigit())
    if len(digits) != 22:
        raise ValidationError("El CBU/CVU debe tener 22 dígitos.")
