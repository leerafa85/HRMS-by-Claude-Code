from django.core.management.base import BaseCommand

from apps.licencias.sync import last_update, run_sync


class Command(BaseCommand):
    help = "Actualiza los feriados nacionales (año actual y siguiente). Pensado para ejecutarse desde un cron."

    def add_arguments(self, parser):
        parser.add_argument("--forzar", action="store_true", help="Actualizar aunque no hayan pasado 7 días.")

    def handle(self, *args, **options):
        results = run_sync(force=options["forzar"])
        if results is None:
            task = last_update()
            when = task.last_success.strftime("%d/%m/%Y %H:%M") if task and task.last_success else "nunca"
            self.stdout.write(f"No corresponde actualizar todavía (última actualización: {when}). Usá --forzar.")
            return
        for r in results:
            if r.ok:
                self.stdout.write(self.style.SUCCESS(
                    f"{r.year}: {r.source} · {r.created} nuevos, {r.updated} revisados, {r.removed} quitados"))
            else:
                self.stdout.write(self.style.WARNING(f"{r.year}: sin datos ({'; '.join(r.errors)})"))
