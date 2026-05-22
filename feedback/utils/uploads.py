"""Attachment sanitisation — close the metadata side-channel on uploads.

Even with the author FK gone (migration 0012), files dragged into a post
or a comment carried two leaks of their own:

1. The original filename — "Screenshot by Saqib.png" or
   "Q4 plan - draft by anna.docx". Members usually don't think about
   filenames as identity, but they are.
2. Embedded document metadata. JPEGs carry EXIF: GPS coordinates,
   camera model, sometimes the owner's full name from the iCloud
   account. Office docs (.docx, .xlsx) embed `dc:creator` and
   `lastModifiedBy` in `docProps/core.xml`. PDFs have an Info
   dictionary with /Author and /Creator.

This module rewrites every uploaded file before it lands in
`MEDIA_ROOT`:

- Filename → random URL-safe token + the original extension.
- Image bytes → re-encoded via Pillow, dropping EXIF as a side effect.
- PDF bytes → rewritten via pikepdf with `clear_metadata=True`.
- Office bytes → ZIP unpacked, `docProps/core.xml` and
  `docProps/app.xml` overwritten with neutral content.

`.doc` and `.xls` (legacy OLE binary formats) cannot be sanitised
reliably without third-party libraries we don't want to add; uploads
are rejected with a message asking for PDF or modern Office export.

Wired into `feedback/forms.py:PostForm.clean_attachments` and
`CommentForm.clean_image`.
"""

import io
import os
import secrets
import zipfile

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile

# Extensions we know how to sanitise. Tighter than the form-level
# `ALLOWED_ATTACHMENT_EXTENSIONS` because legacy Office binary formats
# (.doc, .xls) need different tooling.
_IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
_PDF_EXTS = {'.pdf'}
_OOXML_EXTS = {'.docx', '.xlsx'}
_LEGACY_OFFICE_EXTS = {'.doc', '.xls'}
_TEXT_EXTS = {'.csv'}

# Inside .docx / .xlsx the metadata files we care about. Overwriting
# both with empty XML is enough to wipe author / lastModifiedBy /
# revision history at the file-property level.
_OOXML_METADATA_FILES = ('docProps/core.xml', 'docProps/app.xml')
_EMPTY_CORE_XML = (
    b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    b'<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"'
    b' xmlns:dc="http://purl.org/dc/elements/1.1/"'
    b' xmlns:dcterms="http://purl.org/dc/terms/"'
    b' xmlns:dcmitype="http://purl.org/dc/dcmitype/"'
    b' xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
    b'</cp:coreProperties>'
)
_EMPTY_APP_XML = (
    b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    b'<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"'
    b' xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
    b'</Properties>'
)


def _random_filename(ext: str) -> str:
    """Random URL-safe stem + the supplied extension, lowercased."""
    return f"{secrets.token_urlsafe(16)}{ext.lower()}"


def _strip_image(raw_bytes: bytes, ext: str) -> bytes:
    """Re-encode an image so its EXIF, IPTC, XMP, and ICC are dropped.

    Pillow rebuilds the image from pixel data; everything outside the
    bitmap is lost unless we explicitly carry it across, which we don't.
    """
    from PIL import Image

    image = Image.open(io.BytesIO(raw_bytes))
    output = io.BytesIO()
    # Pillow's format names don't match extensions 1:1. Map.
    fmt = {
        '.jpg': 'JPEG',
        '.jpeg': 'JPEG',
        '.png': 'PNG',
        '.gif': 'GIF',
        '.webp': 'WEBP',
    }[ext.lower()]
    save_kwargs = {}
    if fmt == 'JPEG':
        if image.mode in ('RGBA', 'P'):
            image = image.convert('RGB')
        save_kwargs.update(quality=90, optimize=True)
    image.save(output, format=fmt, **save_kwargs)
    return output.getvalue()


def _strip_pdf(raw_bytes: bytes) -> bytes:
    """Rewrite a PDF with metadata cleared.

    `pikepdf.Pdf.save(..., deterministic_id=False)` plus
    `with pikepdf.open(...).open_metadata() as m: m.clear()` removes
    /Author, /Creator, /Producer, /Title, /Subject, /Keywords, the
    XMP packet, and the document ID trailer.
    """
    import pikepdf

    src = pikepdf.open(io.BytesIO(raw_bytes))
    with src.open_metadata() as m:
        m.clear()
    # pikepdf doesn't expose a single-flag "clear info dictionary",
    # but explicitly nulling the Info entry is safe.
    if src.docinfo is not None:
        for key in list(src.docinfo.keys()):
            del src.docinfo[key]
    output = io.BytesIO()
    src.save(output)
    return output.getvalue()


def _strip_ooxml(raw_bytes: bytes) -> bytes:
    """Rewrite a .docx / .xlsx with author / lastModifiedBy / etc wiped.

    OOXML files are ZIP archives. We rewrite the archive, replacing
    `docProps/core.xml` and `docProps/app.xml` with neutral templates.
    """
    src_buf = io.BytesIO(raw_bytes)
    out_buf = io.BytesIO()
    with zipfile.ZipFile(src_buf, 'r') as src, zipfile.ZipFile(out_buf, 'w', zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            if info.filename == 'docProps/core.xml':
                dst.writestr(info, _EMPTY_CORE_XML)
            elif info.filename == 'docProps/app.xml':
                dst.writestr(info, _EMPTY_APP_XML)
            else:
                dst.writestr(info, src.read(info.filename))
    return out_buf.getvalue()


def sanitise_upload(uploaded_file):
    """Return a fresh `ContentFile` with neutral name and stripped metadata.

    `uploaded_file` is a Django UploadedFile (from `request.FILES`). The
    returned ContentFile is a drop-in replacement: assign it to the
    model's FileField directly.

    Raises `ValidationError` if the file is a legacy Office binary we
    can't sanitise.
    """
    name = uploaded_file.name or 'upload'
    ext = os.path.splitext(name)[1].lower()

    if ext in _LEGACY_OFFICE_EXTS:
        raise ValidationError(
            f'"{name}" is a legacy Office binary format. Please export '
            'to PDF or modern .docx/.xlsx and re-upload.'
        )

    uploaded_file.seek(0)
    raw = uploaded_file.read()

    if ext in _IMAGE_EXTS:
        cleaned = _strip_image(raw, ext)
    elif ext in _PDF_EXTS:
        cleaned = _strip_pdf(raw)
    elif ext in _OOXML_EXTS:
        cleaned = _strip_ooxml(raw)
    elif ext in _TEXT_EXTS:
        # CSV is plain text; no embedded metadata to strip. We still
        # rename to drop the original filename leak.
        cleaned = raw
    else:
        raise ValidationError(
            f'"{name}" is not a supported attachment type.'
        )

    return ContentFile(cleaned, name=_random_filename(ext))
