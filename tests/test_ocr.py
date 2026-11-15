import io
from app.ocr import validate_upload, extract_text


def test_validate_upload_allows_pdf_and_images():
    assert validate_upload('report.pdf', 'application/pdf')[0]
    assert validate_upload('photo.png', 'image/png')[0]


def test_validate_upload_rejects_executable():
    assert not validate_upload('program.exe', 'application/octet-stream')[0]


def test_extract_text_reports_invalid_image():
    try:
        extract_text(b'bad image', 'bad.png', 'image/png')
    except ValueError as exc:
        assert 'could not be decoded' in str(exc)
    else:
        raise AssertionError('invalid image should fail extraction')
