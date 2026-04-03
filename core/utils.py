import os.path
import re
from typing import LiteralString
from zipfile import ZipFile

from django.conf import settings
from django.core.cache import cache

from core.models import Issue

IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}


def natural_key(s: str) -> list[int | LiteralString]:
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]


def is_image_file(filename: str) -> bool:
    _, ext = os.path.splitext(filename.lower())
    return ext in IMAGE_EXTENSIONS


def get_sorted_images_from_cbz(zip_file: ZipFile) -> list[str]:
    files = [f for f in zip_file.namelist() if not f.endswith('/') and is_image_file(f)]
    files.sort(key=natural_key)
    return files


def is_safe_path(path) -> bool:
    base = os.path.abspath(settings.CBZ_BASE_PATH)
    target = os.path.abspath(path)
    return os.path.commonpath([base]) == os.path.commonpath([base, target])


def get_cbz_file_list(issue: Issue) -> list[str]:
    path = issue.file_path

    mtime = os.path.getmtime(path)
    cache_key = f'cbz:{issue.id}:{mtime}'

    files = cache.get(cache_key)
    if files is not None:
        return files

    #cache miss
    with ZipFile(path) as zf:
        files = get_sorted_images_from_cbz(zf)

    # cache por 1 hora
    cache.set(cache_key, files, timeout=3600)

    return files
