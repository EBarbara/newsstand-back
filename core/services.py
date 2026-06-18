import io
import re
import zipfile
from datetime import date
from pathlib import Path
from typing import TypedDict, Optional, Any, Callable

from PIL import Image, UnidentifiedImageError
from django.core.files.base import ContentFile
from django.utils.text import slugify

from core.models import Issue, Render, Magazine

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
    volume: Optional[str]
    year: Optional[int]
    edition: Optional[str]
    publishing_date: Optional[date]


def parse_cbz_filename(filename: str) -> ParsedCBZ:
    name = filename.replace(".cbz", "")

    # --- magazine (tudo antes de "Vol.")
    magazine_match = re.match(r"^(.*?)\s+Vol\.", name)
    magazine = magazine_match.group(1).strip() if magazine_match else None
    if not magazine:
        # Fallback
        magazine = name.strip()

    # --- volume flexível (qualquer número ou ano depois de Vol.)
    volume_match = re.search(r"Vol\.([a-zA-Z0-9]+)", name)
    volume = volume_match.group(1).strip() if volume_match else None

    # --- ano do volume (se for um ano de 4 dígitos)
    year = None
    if volume and volume.isdigit() and len(volume) == 4:
        year = int(volume)

    # --- edição (#105A, #3-4, #3_4)
    edition_match = re.search(r"#([a-zA-Z0-9_\-\/]+)", name)
    edition = edition_match.group(1) if edition_match else None
    if edition:
        edition = edition.replace("_", "-").replace("/", "-")
        if edition.isdigit():
            edition = edition.zfill(2)

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
        "volume": volume,
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
    issue: Optional[Issue] = None,
    append: bool = False,
    volume: Optional[str] = None,
) -> tuple[Issue, int]:
    """
    Processa um arquivo CBZ (file_obj) e importa suas imagens para um Issue.
    :param append:
    :param edition:
    :param publishing_date:
    :param magazine_slug:
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
                year = parsed.get("year")
                if year:
                    magazine_slug = f"{slugify(str(magazine_name))}-{year}"
                else:
                    magazine_slug = slugify(str(magazine_name))

        # --- validação mínima
        if not magazine_slug or not edition:
            raise ValueError(
                "Não foi possível determinar magazine/edition. "
                "Forneça magazine_slug e edition, ou certifique-se que o nome do arquivo contém essas informações."
            )

        # --- obter ou criar magazine
        existing_magazine = None
        if magazine_slug:
            existing_magazine = Magazine.objects.filter(slug=magazine_slug).first()

        mag_defaults = {"name": parsed["magazine_name"] if parsed and parsed.get("magazine_name") else magazine_slug}
        
        # --- determinar volume do issue vs volume do magazine
        if parsed and not volume:
            parsed_volume = parsed.get("volume")
            parsed_year = parsed.get("year")
            
            if parsed_volume:
                # Decidir se o volume pertence à Revista (publicação) ou à Edição (numeração)
                belongs_to_magazine = False
                
                if existing_magazine:
                    if existing_magazine.volume and existing_magazine.volume == parsed_volume:
                        belongs_to_magazine = True
                else:
                    # Se a revista ainda não existe no banco, olhamos se o slug termina com o ano do volume
                    if parsed_year and magazine_slug.endswith(str(parsed_year)):
                        belongs_to_magazine = True
                
                if belongs_to_magazine:
                    mag_defaults["volume"] = parsed_volume
                    volume = None
                else:
                    volume = parsed_volume

        magazine, _ = Magazine.objects.get_or_create(
            slug=magazine_slug,
            defaults=mag_defaults
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
            volume=volume,
            defaults={"publishing_date": publishing_date},
        )

        if created:
            log(f"Issue criado: {issue}")

    log(f"Importando CBZ para Issue {issue.pk} ({issue})...")

    start_order = 1
    if not append:
        # ⚠️ limpar renders antigos
        issue.renders.all().delete()
    else:
        from django.db.models import Max
        max_order = issue.renders.aggregate(Max('order'))['order__max'] or 0
        start_order = max_order + 1

    with zipfile.ZipFile(file_obj) as zf:
        files = [f for f in zf.namelist() if is_image(f)]
        files.sort(key=natural_sort_key)

        if not files:
            raise ValueError("O arquivo CBZ não contém nenhuma imagem válida (.jpg, .jpeg, .png, .webp).")

        log(f"{len(files)} imagens encontradas")

        imported_count = 0

        for i, img_filename in enumerate(files, start=start_order):
            data = zf.read(img_filename)
            try:
                image = Image.open(io.BytesIO(data))
                width, height = image.size
            except (OSError, UnidentifiedImageError):
                log(f"AVISO: Erro ao ler imagem: {img_filename}")
                continue

            render = Render.objects.create(
                issue=issue,
                order=i,
                width=width,
                height=height,
            )

            # mantém nome original com prefixo numérico para ordenação
            original_name = Path(img_filename).name
            safe_name = re.sub(r'[^a-zA-Z0-9_\.-]', '_', original_name)
            name = f"{i:04d}_{safe_name}"

            render.image.save(
                name,
                ContentFile(data),
                save=True,
            )
            imported_count += 1

            if i % 10 == 0:
                log(f"{i} páginas importadas...")

    if imported_count == 0:
        raise ValueError("Nenhuma imagem pôde ser processada no arquivo CBZ.")

    log(f"Importação concluída! {imported_count} páginas processadas.")
    return issue, imported_count
