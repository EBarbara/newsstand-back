
import os
import django
from django.core.files.uploadedfile import SimpleUploadedFile
import io
import zipfile

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'newsstand_back.settings')
django.setup()

from core.services import process_cbz_file
from core.models import Issue, Magazine

def test_invalid_cbz():
    # Create an invalid zip file (just some random bytes)
    invalid_cbz = SimpleUploadedFile("invalid.cbz", b"not a zip file", content_type="application/x-cbz")
    
    try:
        process_cbz_file(invalid_cbz, "invalid.cbz", magazine_slug="test", edition="01")
        print("Success (unexpected)")
    except Exception as e:
        print(f"Caught expected exception: {type(e).__name__}: {e}")

def test_empty_cbz():
    # Create a valid zip file but with no images
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as zf:
        zf.writestr("readme.txt", "hello")
    
    buf.seek(0)
    empty_cbz = SimpleUploadedFile("empty.cbz", buf.read(), content_type="application/x-cbz")
    
    try:
        issue, count = process_cbz_file(empty_cbz, "empty.cbz", magazine_slug="test", edition="02")
        print(f"Success with {count} pages")
    except Exception as e:
        print(f"Caught exception: {type(e).__name__}: {e}")

if __name__ == "__main__":
    test_invalid_cbz()
    test_empty_cbz()
