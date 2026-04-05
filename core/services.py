import os
import zipfile
from typing import List

from .models import Issue
from .utils import is_safe_path, get_cbz_file_list


def get_issue_pages(issue: Issue) -> List[str]:
    if not issue.file_path:
        raise FileNotFoundError("No file")

    if not is_safe_path(issue.file_path):
        raise PermissionError("Invalid path")

    if not os.path.exists(issue.file_path):
        raise FileNotFoundError("File not found")

    return get_cbz_file_list(issue)


def get_page_image(issue: Issue, index: int) -> bytes:
    files = get_issue_pages(issue)

    if index < 0 or index >= len(files):
        raise IndexError("Invalid index")

    try:
        with zipfile.ZipFile(issue.file_path) as zf:
            return zf.read(files[index])
    except zipfile.BadZipFile:
        raise ValueError("Invalid CBZ file")