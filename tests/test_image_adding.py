import pytest
from io import BytesIO

from PIL import Image
from fitz import Document

from signhere.utils import add_image_to_pdf

PAGES_TO_TEST = 64


def blank_call(*args, **kwargs):
    return add_image_to_pdf(None, None, None, None, *args, **kwargs)


def test_sanity():
    invalid_kwargs = [
        {"page_num": -1},
        {"x": -1},
        {"y": -1},
    ]

    for kwargs in invalid_kwargs:
        with pytest.raises(AssertionError):
            assert blank_call(**kwargs)


def test_adding_valid_image():
    document = Document()
    document.insertPage(-1, text="(watermark)", width=32, height=32)

    img = Image.new("RGB", (5, 10), color="red")
    watermark = BytesIO()
    img.save(watermark, format="PNG")

    for page_num in range(0, PAGES_TO_TEST):
        document.insertPage(-1, text=f"This is page number {page_num}")

    for page_num in range(0, PAGES_TO_TEST):
        assert add_image_to_pdf(
            document,
            watermark,
            32,
            32,
            page_num=page_num + 1,
            x=64,
            y=64,
            x_offset=page_num / 100,
            y_offset=page_num / 100,
        )
