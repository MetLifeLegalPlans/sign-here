"""
This module includes functions to insert images and text into PDF documents. This was originally aimed for inserting signatures as images into legal documentation. It also supports inserting text so that text can be added for answers to questions. This was used for inserting personal information and dates into documents. 
"""

import re
from io import BytesIO
from fitz import Document, Rect
from typing import Callable, List, Dict, Tuple, NewType, Union, Optional
from PIL.Image import Image

from .exceptions import AddImageArgumentError

ImageSettings = NewType("ImageSettings", Dict[str, Union[int, float]])
"""
An alias for the dictionary used for image settings. The following keys are required
- x_offset: A float offset in x of where to place the image
- y_offset: A float offset in y of where to place the image
The following keys are only required for images, not dynamic text
- max_x: An int value that is the max image size in x
- max_y: An int value that is the max image size in y
The following keys are optional. The default value is 1 (no scaling)
- x_scalar: how to scale the image (or text) in the x axes
- y_scalar: how to scale the image (or text) in the y axes

These values will be combined with a (x, y) coordinate to produce the final position, scaling, and size.
"""

DefaultImageSettings = NewType(
    "DefaultImageSettings", Dict[str, Union[ImageSettings, Dict[str, ImageSettings]]]
)
"""
Dictionary that is used as default values for image settings. The keys should be the image type (which should be part of the image name). The value should be a ImageSettings dictionary. In addition to the ImageSettings keys there can be an additional key where the key value is a string representing the "sub-type" and the value is another ImageSettings dictionary.

The image type of DYNAMIC_TEXT is a special key that will be applied to text (instead of images) inserted. Subtypes can be used under the DYNAMIC_TEXT entry like the other image types. 
"""

DYNAMIC_TEXT = "text"

"""
Constant used to identify an "image" as actually being text that should be inserted as if it was an image. 
"""


def make_image_name(img_type: str, name: str, sub_type: Optional[str] = None):
    """
    Helper function for creating names for images that includes their type / sub type in the format expected in add_images_to_pdf

    :param img_type: The top level type of the image as a string
    :param name: The name of the image as a string
    :param sub_type: The sub type of the image, optional
    """
    if sub_type:
        return f"{img_type}__{name}__{sub_type}"
    else:
        return f"{img_type}__{name}"


def add_images_to_pdf(
    initial_pdf: bytes,
    metadata: List[Dict[str, List[Tuple[float, float]]]],
    img_loader: Callable[[str], Image],
    dynamic_text: Dict[str, str],
    only_matches: Optional[str] = None,
    page_numbers: Optional[List[int]] = None,
    default_img_settings: Optional[DefaultImageSettings] = None,
) -> Document:
    """
    This function adds an image to a PDF document.

    :param initial_pdf: A pdf buffer in bytes
    :param metadata: A list of dictionaries, with each index of the list representing a page
        and each dictionary showing which image fits where on that page.
    :param img_loader: A function that should take in an image name and return a Pillow image.
    :param dynamic_text: A dictionary of text to add to images keyed by the image that the text
        should be inserted into.
    :param only_matches: A regex string, will insert only the images whose names match
        that regex. For instance, if you pass in "notary", this will only insert the values
        for the notary. Optional
    :param page_numbers: A list where you can specify only the page numbers that should
        be signed. this works with `only_matches` as well, if desired. Optional
    :param default_img_settings: A dictionary with image types as keys and the default
        parameters for inserting them as the values.
    :return: A pdf document with the inserted images and text
    """
    default_img_settings = default_img_settings or {}
    # Don't edit the existing PDF, instead create a new one from it and add images and text
    # to that new one.
    pdf = Document()
    pdf.insertPDF(initial_pdf)
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

            img_name, img_type, img_settings = _get_img_data(
                img_name, default_img_settings
            )

            if img_type == DYNAMIC_TEXT:
                _add_dynamic_text(
                    pdf,
                    img_name,
                    dynamic_text,
                    coords_list,
                    page,
                    img_settings,
                    img_loader,
                )
            else:
                _add_image(
                    pdf,
                    img_name,
                    img_loader,
                    coords_list,
                    page,
                    img_settings,
                )
    return pdf


def _add_dynamic_text(
    pdf: Document,
    img_name: str,
    dynamic_text: Dict[str, str],
    coords_list: List[Tuple[float, float]],
    page: int,
    img_settings: ImageSettings,
    img_loader: Callable[[str], Image],
) -> None:
    try:
        text_to_add = dynamic_text[img_name]
    except KeyError:
        try:
            # That dynamic text doesn't exist, try looking for it more generally.
            text_to_add = dynamic_text[img_name.rsplit("__", 1)[0]]
        except KeyError:
            # Last backup: see if the given image loader will give us what we want.
            text_to_add = img_loader(img_name)
    for coords in coords_list:
        pdf = add_text_to_pdf(
            pdf,
            text_to_add,
            page,
            x=coords[0] * img_settings.get("x_scalar", 1.0),
            y=coords[1] * img_settings.get("y_scalar", 1.0),
            x_offset=img_settings.get("x_offset", 0.0),
            y_offset=img_settings.get("y_offset", 0.0),
        )


def _add_image(
    pdf: Document,
    img_name: str,
    img_loader: Callable[[str], Image],
    coords_list: List[Tuple[float, float]],
    page: int,
    img_settings: ImageSettings,
) -> None:
    pillow_img = img_loader(img_name)
    # Crop to the box that has the signature or initials in it.
    pillow_img = pillow_img.crop(pillow_img.getbbox())
    img = BytesIO()
    pillow_img.save(img, format="PNG")
    for coords in coords_list:
        pdf = add_image_to_pdf(
            pdf,
            img,
            img_settings.get("max_x", 0),
            img_settings.get("max_y", 0),
            page,
            x=coords[0] * img_settings.get("x_scalar", 1.0),
            y=coords[1] * img_settings.get("y_scalar", 1.0),
            x_offset=img_settings.get("x_offset", 0.0),
            y_offset=img_settings.get("y_offset", 0.0),
        )


def _get_img_data(
    img_name: str, default_img_settings: DefaultImageSettings
) -> Tuple[str, str, ImageSettings]:
    """Anchor names for images are formatted so:
    {type}__{optional: person/role}{optional: __{subtype}}
    We use the type and optional subtype to figure out how to load the image and what
    settings to use to position and resize the image. The returned image name is what's
    used to load or generate the image.
    """
    split = img_name.split("__")
    img_type = split[0]
    img_settings = default_img_settings.get(img_type, {})
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
    x: float = 0.0,
    y: float = 0.0,
    x_offset: float = 0.0,
    y_offset: float = 0.0,
) -> bytes:
    """
    Add an image to a PDF document, at the specified page and coordinates.

    :param document: A pdf Document to add an image to
    :param image_buffer:
    :param img_width: Width of the image being added
    :param img_heigh: Height of the image being added
    :param page_num: Page to add the image
    :param x: x coordinate to insert the image, optional
    :param y: y coordinate to insert the image, optional
    :param x_offset: decimal-represented interpolation percentage to specify
        image placement relative to the x coordinate, optional
    :param y_offset: decimal-represented interpolation percentage to specify
        image placement relative to the y coordinate, optional
    :return: pdf as a bytestring

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
    x: float = 0.0,
    y: float = 0.0,
    x_offset: float = 0.0,
    y_offset: float = 0.0,
    fontsize: int = 11,
) -> bytes:
    """
    Add text to a PDF document, at the specified page and coordinates.

    :param document: A pdf Document to add an image to
    :param image_buffer:
    :param img_width: Width of the image being added
    :param img_heigh: Height of the image being added
    :param page_num: Page to add the image
    :param x: x coordinate to insert the image, optional
    :param y: y coordinate to insert the image, optional
    :param x_offset: decimal-represented interpolation percentage to specify
        image placement relative to the x coordinate, optional
    :param y_offset: decimal-represented interpolation percentage to specify
        image placement relative to the y coordinate, optional
    :param fontsize: fontsize for the inserted text, optional

    """
    _do_checks(page_num, x, y)

    page = document[page_num]
    page.cleanContents()

    rect = Rect(x + x_offset, y + y_offset, x + x_offset + 500, y + y_offset + 100)

    page.insertTextbox(rect, buffer=text, fontsize=fontsize, fontname="times-roman")

    return document


def _do_checks(page_num: int, x: float, y: float) -> None:
    # Enforce sanity checks inline instead of solely in tests as this operation is expensive
    checks = [
        (page_num >= 0, "Page must be a zero-indexed positive integer"),
        (x >= 0 and y >= 0, "Page coordinates must be a positive integer"),
    ]

    for check, message in checks:
        if not check:
            raise AddImageArgumentError(message)
