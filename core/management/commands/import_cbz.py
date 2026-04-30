import io, re, zipfile
from datetime import date
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from core.models import Issue
from core.services import process_cbz_file


class Command(BaseCommand):
    help = "Importa um CBZ para um Issue usando o serviço process_cbz_file"

    def get_issue(self, options):
        issue_id = options.get('issue_id')
        if issue_id:
            try:
                return Issue.objects.get(id=issue_id)
            except Issue.DoesNotExist:
                raise CommandError("Issue não encontrado")
        return None

    def add_arguments(self, parser):
        parser.add_argument('cbz_path', type=str)

        parser.add_argument('--issue-id', type=int)
        parser.add_argument('--magazine', type=str)
        parser.add_argument('--edition', type=str)
        parser.add_argument('--date', type=str)

    def handle(self, *args, **options):
        cbz_path = options['cbz_path']
        path = Path(cbz_path)

        if not path.exists():
            raise CommandError("Arquivo não existe")

        issue = self.get_issue(options)

        def logger(msg: str):
            if msg.startswith("AVISO:"):
                self.stdout.write(self.style.WARNING(msg))
            elif "concluída" in msg.lower() or "criado" in msg.lower():
                self.stdout.write(self.style.SUCCESS(msg))
            else:
                self.stdout.write(msg)

        try:
            with open(path, 'rb') as f:
                process_cbz_file(
                    file_obj=f,
                    filename=path.name,
                    magazine_slug=options.get('magazine'),
                    edition=options.get('edition'),
                    publishing_date=options.get('date'),
                    logger=logger,
                    issue=issue
                )
        except ValueError as e:
            raise CommandError(str(e))