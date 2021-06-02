import re
from io import BytesIO
from box import Box
from fitz import Document, Rect

from .exceptions import AddImageArgumentError


DEFAULT_SCALAR = 0.75


DYNAMIC_TEXT = "text"
IMAGE_CONSTANTS = Box(
    {
        "signature": {
            "max_x": 175,
            "max_y": 40,
            "x_offset": 0,
            "y_offset": -35,
        },
        "initials": {
            "max_x": 37,
            "max_y": 37,
            "x_offset": -38,
            "y_offset": -15,
            "yes": {
                "max_x": 37,
                "max_y": 37,
                "x_offset": -93,
                "y_offset": -15,
            },
            "checkbox": {
                "max_x": 45,
                "max_y": 45,
                "x_offset": 0.10,
                "y_offset": 0.2,
                "x_scalar": 0.8,
            },
        },
        "seal": {
            "max_x": 256,
            "max_y": 150,
            "x_offset": -25,
            "y_offset": -140,
        },
        "checkmark": {
            "max_x": 18,
            "max_y": 18,
            "x_offset": -11,
            "y_offset": -6,
        },
        DYNAMIC_TEXT: {
            "x_offset": 3,
            "y_offset": -15,
            "inline": {
                "x_offset": 3,
                "y_offset": -2,
            },
            "under_seal": {
                "x_offset": -18,
                "y_offset": -24,
            },
        },
    }
)


def add_images_to_pdf(
    initial_pdf,
    metadata,
    img_loader,
    dynamic_text,
    only_matches=None,
    page_numbers=None,
    loader_args=None,
):
    """
    pdf is the pdf buffer in bytes.
    metadata is a list of dictionaries, with each index of the list representing a page
        and each dictionary showing which image fits where on that page.
    img_loader is a function that should take in an image name and return a Pillow image.
    only_matches is an optional regex string, and will insert only the images whose names match
        that regex. for instance, if you pass in "notary", this will only insert the values
        for the notary.
    page_numbers is an optional list where you can specify only the page numbers that should
        be signed. this works with `only_matches` as well, if desired.
    """
    # Don't edit the existing PDF, instead create a new one from it and add images and text
    # to that new one.
    pdf = Document()
    pdf.insertPDF(initial_pdf)
    if not loader_args:
        loader_args = []
    for page, page_data in enumerate(metadata):
        if not page_data:
            # Nothing to insert on this page.
            continue
        if page_numbers and page + 1 not in page_numbers:
            # We have specified page numbers but this isn't one of them.
            continue

        for img_name, coords_list in page_data.items():
            if only_matches and not re.search(only_matches, img_name):
                continue

            img_name, img_type, img_settings = _get_img_data(img_name)

            if img_type == DYNAMIC_TEXT:
                _add_dynamic_text(
                    pdf,
                    img_name,
                    dynamic_text,
                    coords_list,
                    page,
                    img_settings,
                    img_loader,
                    loader_args,
                )
            else:
                _add_image(
                    pdf,
                    img_name,
                    img_loader,
                    coords_list,
                    page,
                    img_settings,
                    loader_args,
                )
    return pdf


def _add_dynamic_text(
    pdf,
    img_name,
    dynamic_text,
    coords_list,
    page,
    img_settings,
    img_loader,
    loader_args,
):
    try:
        text_to_add = dynamic_text[img_name]
    except KeyError:
        try:
            # That dynamic text doesn't exist, try looking for it more generally.
            text_to_add = dynamic_text[img_name.rsplit("__", 1)[0]]
        except KeyError:
            # Last backup: see if the given image loader will give us what we want.
            text_to_add = img_loader(img_name, *loader_args)
    for coords in coords_list:
        pdf = add_text_to_pdf(
            pdf,
            text_to_add,
            page,
            x=coords[0] * img_settings.get("x_scalar", DEFAULT_SCALAR),
            y=coords[1] * img_settings.get("y_scalar", DEFAULT_SCALAR),
            x_offset=img_settings.x_offset,
            y_offset=img_settings.y_offset,
        )


def _add_image(pdf, img_name, img_loader, coords_list, page, img_settings, loader_args):
    pillow_img = img_loader(img_name, *loader_args)
    # Crop to the box that has the signature or initials in it.
    pillow_img = pillow_img.crop(pillow_img.getbbox())
    img = BytesIO()
    pillow_img.save(img, format="PNG")
    for coords in coords_list:
        pdf = add_image_to_pdf(
            pdf,
            img,
            img_settings.max_x,
            img_settings.max_y,
            page,
            x=coords[0] * img_settings.get("x_scalar", DEFAULT_SCALAR),
            y=coords[1] * img_settings.get("y_scalar", DEFAULT_SCALAR),
            x_offset=img_settings.x_offset,
            y_offset=img_settings.y_offset,
        )


def _get_img_data(img_name):
    """Anchor names for images are formatted so:
    {type}__{optional: person/role}{optional: __{subtype}}
    We use the type and optional subtype to figure out how to load the image and what
    settings to use to position and resize the image. The returned image name is what's
    used to load or generate the image.
    """
    split = img_name.split("__")
    img_type = split[0]
    img_settings = IMAGE_CONSTANTS.get(img_type)
    if not img_settings:
        img_settings = IMAGE_CONSTANTS[DYNAMIC_TEXT]
        img_type = DYNAMIC_TEXT
    if len(split) == 3:
        # This has a possible subtype. Get the name without the subtype to return.
        img_name = "__".join([s for s in split[:-1] if s])
        if split[-1] in img_settings:
            # This has a sub type that we need to use for placement/size settings.
            img_settings = img_settings[split[-1]]

    return img_name, img_type, img_settings


def add_image_to_pdf(
    document: Document,
    image_buffer: bytes,
    img_width: float,
    img_height: float,
    page_num: int = 0,
    x: int = 0,
    y: int = 0,
    x_offset: float = 0.0,
    y_offset: float = 0.0,
) -> bytes:
    """
    Add an image to a PDF document, at the specified page and coordinates.

    Optionally takes an decimal-represented interpolation percentage to specify
    image placement relative to the coordinates.
    """
    _do_checks(page_num, x, y)

    page = document[page_num]
    page.cleanContents()

    rect = Rect(
        x + x_offset,
        y + y_offset,
        x + x_offset + img_width,
        y + y_offset + img_height,
    )

    page.insertImage(rect, stream=image_buffer)

    return document


def add_text_to_pdf(
    document: Document,
    text: str,
    page_num: int = 0,
    x: int = 0,
    y: int = 0,
    x_offset: float = 0.0,
    y_offset: float = 0.0,
    fontsize: int = 11,
) -> bytes:
    """
    Add text to a PDF document, at the specified page and coordinates.

    Optionally takes an decimal-represented interpolation percentage to specify
    image placement relative to the coordinates, as well as a fontsize.
    """
    _do_checks(page_num, x, y)

    page = document[page_num]
    page.cleanContents()

    rect = Rect(x + x_offset, y + y_offset, x + x_offset + 500, y + y_offset + 100)

    page.insertTextbox(rect, buffer=text, fontsize=fontsize, fontname="times-roman")

    return document


def _do_checks(page_num, x, y):
    # Enforce sanity checks inline instead of solely in tests as this operation is expensive
    checks = [
        (page_num >= 0, "Page must be a zero-indexed positive integer"),
        (x >= 0 and y >= 0, "Page coordinates must be a positive integer"),
    ]

    for check, message in checks:
        if not check:
            raise AddImageArgumentError(message)
