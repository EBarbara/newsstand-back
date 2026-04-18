import io, re, zipfile
from datetime import date
from pathlib import Path
from typing import TypedDict, Optional

from PIL import Image
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.utils.text import slugify

from core.models import Issue, RenderAsset, Magazine

VALID_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.webp')

MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}

def is_image(filename: str):
    return filename.lower().endswith(VALID_EXTENSIONS)

def natural_sort_key(s: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r'(\d+)', s)]

def parse_cbz_filename(filename: str) -> ParsedCBZ:
    name = filename.replace(".cbz", "")

    # --- magazine (tudo antes de "Vol.")
    magazine_match = re.match(r"^(.*?)\s+Vol\.", name)
    magazine = magazine_match.group(1).strip() if magazine_match else None

    # --- ano do volume
    year_match = re.search(r"Vol\.(\d{4})", name)
    year = int(year_match.group(1)) if year_match else None

    # --- edição (#01)
    edition_match = re.search(r"#(\d+)", name)
    edition = edition_match.group(1).zfill(2) if edition_match else None

    # --- mês e ano textual (August, 1975)
    date_match = re.search(r"\(([^,]+),\s*(\d{4})\)", name)

    publishing_date = None
    if date_match:
        month_name = date_match.group(1).strip().lower()
        year_str = date_match.group(2)

        month = MONTHS.get(month_name)

        if month:
            publishing_date = date(int(year_str), month, 1)

    return {
        "magazine_name": magazine,
        "year": year,
        "edition": edition,
        "publishing_date": publishing_date,
    }


class ParsedCBZ(TypedDict):
    magazine_name: Optional[str]
    year: Optional[int]
    edition: Optional[str]
    publishing_date: Optional[date]


class Command(BaseCommand):
    help = "Importa um CBZ para um Issue"

    def get_or_create_issue(self, options):
        issue_id = options.get('issue_id')
        cbz_path = options.get('cbz_path')

        # --- 1. se veio issue_id, usa direto
        if issue_id:
            return Issue.objects.get(id=issue_id)

        # --- 2. tentar pegar via CLI
        magazine_slug = options.get('magazine')
        edition = options.get('edition')
        publishing_date = options.get('date')

        # --- 3. fallback: parse do filename
        parsed = None
        if not (magazine_slug and edition):
            parsed = parse_cbz_filename(Path(cbz_path).name)

            magazine_name = parsed.get("magazine_name")
            edition = edition or parsed.get("edition")
            publishing_date = publishing_date or parsed.get("publishing_date")

            if magazine_name:
                magazine_slug = slugify(str(magazine_name))

        # --- validação mínima
        if not magazine_slug or not edition:
            raise CommandError(
                "Não foi possível determinar magazine/edition. "
                "Use --magazine e --edition ou forneça um filename válido."
            )

        # --- criar/pegar magazine
        magazine, _ = Magazine.objects.get_or_create(
            slug=magazine_slug,
            defaults={"name": parsed["magazine_name"] if parsed else magazine_slug}
        )

        # --- data
        if publishing_date:
            if isinstance(publishing_date, str):
                publishing_date = date.fromisoformat(publishing_date)
        else:
            publishing_date = date.today()

        # --- criar issue
        issue, created = Issue.objects.get_or_create(
            magazine=magazine,
            edition=edition,
            defaults={"publishing_date": publishing_date},
        )

        if created:
            self.stdout.write(self.style.SUCCESS(f"Issue criado: {issue}"))

        return issue

    def add_arguments(self, parser):
        parser.add_argument('cbz_path', type=str)

        parser.add_argument('--issue-id', type=int)
        parser.add_argument('--magazine', type=str)
        parser.add_argument('--edition', type=str)
        parser.add_argument('--date', type=str)

    def handle(self, *args, **options):
        cbz_path = options['cbz_path']

        try:
            issue = self.get_or_create_issue(options)
        except Issue.DoesNotExist:
            raise CommandError("Issue não encontrado")

        path = Path(cbz_path)

        if not path.exists():
            raise CommandError("Arquivo não existe")

        self.stdout.write(f"Importando CBZ para Issue {issue.id} ({issue})...")

        # ⚠️ limpar renders antigos
        issue.renders.all().delete()

        with zipfile.ZipFile(path) as zf:
            files = [f for f in zf.namelist() if is_image(f)]
            files.sort(key=natural_sort_key)

            self.stdout.write(f"{len(files)} imagens encontradas")

            for i, filename in enumerate(files, start=1):
                data = zf.read(filename)
                try:
                    image = Image.open(io.BytesIO(data))
                    width, height = image.size
                except Exception:
                    self.stdout.write(self.style.WARNING(f"Erro ao ler imagem: {filename}"))
                    continue

                render = RenderAsset.objects.create(
                    issue=issue,
                    order=i,
                    width=width,
                    height=height,
                )

                # mantém extensão original
                ext = Path(filename).suffix.lower()
                name = f"{i:04d}{ext}"

                render.image.save(
                    name,
                    ContentFile(data),
                    save=True,
                )

                if i % 10 == 0:
                    self.stdout.write(f"{i} páginas importadas...")

        self.stdout.write(self.style.SUCCESS("Importação concluída!"))