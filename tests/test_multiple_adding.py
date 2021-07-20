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

DYNAMIC_TEXT = {"text__name": "test name"}


def test_adding_valid_image():
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
                f"text__name": [[50, 50]],
            }
        )

    assert add_images_to_pdf(
        document,
        metadata,
        img_loader,
        PLACEMENT_SETTINGS,
        DYNAMIC_TEXT,
        ["text"],
    )
