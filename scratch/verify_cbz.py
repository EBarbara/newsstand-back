
import io
import zipfile
import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path

# Mock Django before importing services
import sys
from types import ModuleType

mock_django = ModuleType('django')
sys.modules['django'] = mock_django
mock_django.core = ModuleType('core')
mock_django.core.files = ModuleType('files')
mock_django.core.files.base = ModuleType('base')
mock_django.core.files.base.ContentFile = MagicMock()
mock_django.utils = ModuleType('utils')
mock_django.utils.text = ModuleType('text')
mock_django.utils.text.slugify = lambda x: x.lower().replace(' ', '-')
mock_django.db = ModuleType('db')
mock_django.db.models = ModuleType('models')
mock_django.db.models.Max = MagicMock()

# Mock core.models
mock_core = ModuleType('core')
sys.modules['core'] = mock_core
mock_core.models = ModuleType('models')
mock_core.models.Issue = MagicMock()
mock_core.models.Render = MagicMock()
mock_core.models.Magazine = MagicMock()

from core.services import process_cbz_file

class TestCBZProcessing(unittest.TestCase):
    def test_no_images(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as zf:
            zf.writestr("test.txt", "not an image")
        
        buf.seek(0)
        with self.assertRaises(ValueError) as cm:
            process_cbz_file(buf, "test.cbz", magazine_slug="test", edition="01")
        
        self.assertIn("não contém nenhuma imagem válida", str(cm.exception))

    def test_invalid_zip(self):
        buf = io.BytesIO(b"not a zip file")
        with self.assertRaises(zipfile.BadZipFile):
            process_cbz_file(buf, "test.cbz", magazine_slug="test", edition="01")

if __name__ == "__main__":
    unittest.main()
