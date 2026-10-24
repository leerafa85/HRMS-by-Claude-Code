import os
import uuid

from django.utils import timezone
from django.utils.deconstruct import deconstructible


@deconstructible
class UploadTo:
    """Guarda los archivos con nombre aleatorio para no exponer nombres originales."""

    def __init__(self, folder):
        self.folder = folder

    def __call__(self, instance, filename):
        ext = os.path.splitext(filename)[1].lower()
        return f"{self.folder}/{timezone.now():%Y/%m}/{uuid.uuid4().hex}{ext}"

    def __eq__(self, other):
        return isinstance(other, UploadTo) and other.folder == self.folder
