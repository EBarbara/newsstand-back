import io
import re
import zipfile
from datetime import date
from pathlib import Path
from typing import TypedDict, Optional, Any, Callable

from PIL import Image
from django.core.files.base import ContentFile
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

class ParsedCBZ(TypedDict):
    magazine_name: Optional[str]
    year: Optional[int]
    edition: Optional[str]
    publishing_date: Optional[date]

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

def process_cbz_file(
    file_obj: Any,
    filename: str,
    magazine_slug: Optional[str] = None,
    edition: Optional[str] = None,
    publishing_date: Optional[date | str] = None,
    logger: Optional[Callable[[str], None]] = None,
    issue: Optional[Issue] = None
) -> Issue:
    """
    Processa um arquivo CBZ (file_obj) e importa suas imagens para um Issue.
    :param file_obj: Pode ser um objeto de arquivo aberto (open(path, 'rb')) ou um UploadedFile do Django.
    :param filename: Nome do arquivo original (usado para extrair metadata se necessário).
    :param logger: Uma função opcional que recebe strings, para fins de log de progresso.
    :param issue: Opcional. Se passado, as imagens serão atreladas a este Issue existente.
    """
    
    def log(msg: str):
        if logger:
            logger(msg)

    if not issue:
        parsed = None
        if not (magazine_slug and edition):
            parsed = parse_cbz_filename(filename)

            magazine_name = parsed.get("magazine_name")
            edition = edition or parsed.get("edition")
            pub_date_parsed = parsed.get("publishing_date")

            if not publishing_date:
                publishing_date = pub_date_parsed

            if magazine_name and not magazine_slug:
                magazine_slug = slugify(str(magazine_name))

        # --- validação mínima
        if not magazine_slug or not edition:
            raise ValueError(
                "Não foi possível determinar magazine/edition. "
                "Forneça magazine_slug e edition, ou certifique-se que o nome do arquivo contém essas informações."
            )

        # --- criar/pegar magazine
        magazine, _ = Magazine.objects.get_or_create(
            slug=magazine_slug,
            defaults={"name": parsed["magazine_name"] if parsed and parsed.get("magazine_name") else magazine_slug}
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
            log(f"Issue criado: {issue}")

    log(f"Importando CBZ para Issue {issue.id} ({issue})...")

    # ⚠️ limpar renders antigos
    issue.renders.all().delete()

    with zipfile.ZipFile(file_obj) as zf:
        files = [f for f in zf.namelist() if is_image(f)]
        files.sort(key=natural_sort_key)

        log(f"{len(files)} imagens encontradas")

        for i, img_filename in enumerate(files, start=1):
            data = zf.read(img_filename)
            try:
                image = Image.open(io.BytesIO(data))
                width, height = image.size
            except Exception:
                log(f"AVISO: Erro ao ler imagem: {img_filename}")
                continue

            render = RenderAsset.objects.create(
                issue=issue,
                order=i,
                width=width,
                height=height,
            )

            # mantém extensão original
            ext = Path(img_filename).suffix.lower()
            name = f"{i:04d}{ext}"

            render.image.save(
                name,
                ContentFile(data),
                save=True,
            )

            if i % 10 == 0:
                log(f"{i} páginas importadas...")

    log("Importação concluída!")
    return issue
