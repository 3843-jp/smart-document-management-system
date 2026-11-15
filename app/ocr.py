import io
from pathlib import Path
from PIL import Image, UnidentifiedImageError
import fitz
import pytesseract
from pdf2image import convert_from_bytes

ALLOWED = {'.pdf', '.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp'}


def validate_upload(filename, mimetype=''):
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED:
        return False, 'Only PDF and common image files are accepted'
    allowed_mimes = {'application/pdf', 'image/png', 'image/jpeg', 'image/tiff', 'image/bmp', 'application/octet-stream'}
    if mimetype and mimetype not in allowed_mimes:
        return False, 'File content type does not match an accepted document type'
    return True, ''


def extract_text(data, filename, mimetype=''):
    suffix = Path(filename).suffix.lower()
    if suffix == '.pdf':
        doc = fitz.open(stream=data, filetype='pdf')
        extracted = '\n'.join(page.get_text() for page in doc).strip()
        if extracted:
            return extracted
        pages = convert_from_bytes(data, fmt='png')
        return '\n'.join(pytesseract.image_to_string(page) for page in pages).strip()
    try:
        image = Image.open(io.BytesIO(data))
        return pytesseract.image_to_string(image).strip()
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError('Image could not be decoded') from exc
