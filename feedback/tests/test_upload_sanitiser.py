"""Tests for feedback/utils/uploads.py.

The sanitiser exists to close the side-channel where attachment
filenames and embedded metadata (EXIF, /Author, dc:creator) deanonymise
a member who otherwise posted anonymously. Each test below is a tripwire
for one specific leak.
"""

import io
import zipfile
from io import BytesIO

import pikepdf
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from PIL import Image

from feedback.utils.uploads import sanitise_upload


def _image_with_exif(name='photo.jpg'):
    """Pillow JPEG that embeds a fake EXIF blob describing camera +
    'Artist' tag (the field that leaks the photographer's name)."""
    img = Image.new('RGB', (4, 4), color=(255, 0, 0))
    buf = BytesIO()
    # Pillow's `exif` kwarg accepts a packed EXIF bytes payload.
    # We craft a small one with the Artist tag set.
    exif = img.getexif()
    exif[0x013B] = 'Saqib Rahman'    # Artist
    exif[0x010F] = 'Strativ Camera'  # Make
    img.save(buf, format='JPEG', exif=exif.tobytes())
    return SimpleUploadedFile(name, buf.getvalue(), content_type='image/jpeg')


def _pdf_with_author(name='note.pdf', author='Saqib Rahman'):
    pdf = pikepdf.new()
    pdf.add_blank_page()
    pdf.docinfo['/Author'] = author
    pdf.docinfo['/Creator'] = 'Strativ Editor'
    buf = BytesIO()
    pdf.save(buf)
    return SimpleUploadedFile(name, buf.getvalue(), content_type='application/pdf')


def _docx_with_author(name='draft.docx', author='Saqib Rahman'):
    """Bare-minimum .docx (a ZIP with a docProps/core.xml carrying the
    author). Not a valid Word document by Word's standards, but it's
    enough to test the metadata strip path."""
    buf = BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', '<Types/>')
        z.writestr(
            'docProps/core.xml',
            f'<?xml version="1.0"?>'
            f'<cp:coreProperties xmlns:cp="x" xmlns:dc="y">'
            f'<dc:creator>{author}</dc:creator>'
            f'<cp:lastModifiedBy>{author}</cp:lastModifiedBy>'
            f'</cp:coreProperties>'.encode('utf-8'),
        )
        z.writestr(
            'docProps/app.xml',
            f'<?xml version="1.0"?>'
            f'<Properties xmlns="x"><Application>Word</Application>'
            f'<Company>Strativ</Company></Properties>'.encode('utf-8'),
        )
        z.writestr('word/document.xml', '<document/>')
    return SimpleUploadedFile(name, buf.getvalue(), content_type='application/vnd.openxmlformats')


class FilenameAnonymisationTest(TestCase):
    def test_image_filename_replaced_with_random_token(self):
        uploaded = _image_with_exif('Screenshot_by_saqib.jpg')
        cleaned = sanitise_upload(uploaded)
        self.assertNotEqual(cleaned.name, 'Screenshot_by_saqib.jpg')
        self.assertTrue(cleaned.name.endswith('.jpg'))
        # The stem is a token; we don't assert the exact value but it
        # must not contain the original filename.
        self.assertNotIn('saqib', cleaned.name.lower())

    def test_pdf_filename_replaced(self):
        cleaned = sanitise_upload(_pdf_with_author('Quarterly review by Saqib.pdf'))
        self.assertNotEqual(cleaned.name, 'Quarterly review by Saqib.pdf')
        self.assertNotIn('saqib', cleaned.name.lower())
        self.assertTrue(cleaned.name.endswith('.pdf'))


class ImageEXIFStrippedTest(TestCase):
    def test_jpeg_exif_artist_is_removed(self):
        cleaned = sanitise_upload(_image_with_exif())
        cleaned_bytes = cleaned.read()
        img = Image.open(io.BytesIO(cleaned_bytes))
        exif = img.getexif()
        # 0x013B is the Artist tag.
        self.assertNotIn(0x013B, exif)
        self.assertNotIn(0x010F, exif)
        # And the cleaned blob shouldn't contain the literal name.
        self.assertNotIn(b'Saqib Rahman', cleaned_bytes)


class PDFMetadataStrippedTest(TestCase):
    def test_pdf_author_is_removed(self):
        cleaned = sanitise_upload(_pdf_with_author())
        cleaned_bytes = cleaned.read()
        out = pikepdf.open(io.BytesIO(cleaned_bytes))
        info = out.docinfo
        self.assertNotIn('/Author', info)
        self.assertNotIn('/Creator', info)
        # And the literal name shouldn't appear in the raw bytes either
        # (pikepdf may compress streams, but Info dict is uncompressed).
        self.assertNotIn(b'Saqib Rahman', cleaned_bytes)


class DocxMetadataStrippedTest(TestCase):
    def test_docx_creator_is_removed(self):
        cleaned = sanitise_upload(_docx_with_author())
        cleaned_bytes = cleaned.read()
        with zipfile.ZipFile(io.BytesIO(cleaned_bytes), 'r') as z:
            core = z.read('docProps/core.xml').decode('utf-8')
            app = z.read('docProps/app.xml').decode('utf-8')
        self.assertNotIn('Saqib Rahman', core)
        self.assertNotIn('Strativ', app)


class LegacyOfficeRejectedTest(TestCase):
    def test_legacy_doc_is_rejected_with_helpful_message(self):
        uploaded = SimpleUploadedFile('old.doc', b'fake binary', content_type='application/msword')
        with self.assertRaises(ValidationError) as cm:
            sanitise_upload(uploaded)
        self.assertIn('legacy Office binary', str(cm.exception))
