import pytest
from io import BytesIO

from PIL import Image
from fitz import Document

from signhere.utils import add_images_to_pdf

PAGES_TO_TEST = 64


PLACEMENT_SETTINGS = {
    "image": {
        "max_y": 50,
        "max_x": 50,
    },
    "text": {},
}

DYNAMIC_TEXT = {
    "name__test": "test name",
    "date": "9/12/2019"
}


def test_adding_multiple_images_and_text():
    document = Document()
    document.insertPage(-1, text="(watermark)", width=32, height=32)

    img = Image.new("RGB", (5, 10), color="red")
    watermark = BytesIO()
    img.save(watermark, format="PNG")

    def img_loader(name):
        return img

    for page_num in range(0, PAGES_TO_TEST):
        document.insertPage(-1, text=f"This is page number {page_num}")

    metadata = []
    for page_num in range(0, PAGES_TO_TEST):
        metadata.append(
            {
                f"image__{page_num}": [[0, 0]],
                f"name__test": [[50, 50]],
                f"date__test": [[10, 10]],
            }
        )

    assert add_images_to_pdf(
        document,
        metadata,
        img_loader,
        DYNAMIC_TEXT,
        PLACEMENT_SETTINGS,
    )
