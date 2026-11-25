"""
Image upload and validation service.
Handles secure file storage, MIME verification via Pillow, and collision-free path generation.
"""

import os
import uuid
from pathlib import Path

from flask import current_app
from PIL import Image, UnidentifiedImageError
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename


class InvalidImageError(Exception):
    """Raised when an uploaded file fails format, MIME, or dimension integrity validation."""


def get_allowed_extensions() -> set[str]:
    """Retrieve allowed image file extensions from application configuration."""
    return current_app.config.get("ALLOWED_EXTENSIONS", {"jpg", "jpeg", "png"})


def save_image(file_storage: FileStorage, subfolder: str = "chats") -> str:
    """
    Validate and save an uploaded image file securely to disk.

    Validation Checks:
    1. Presence of file and valid filename.
    2. Extension belongs to ALLOWED_EXTENSIONS (jpg, jpeg, png).
    3. Payload size <= MAX_CONTENT_LENGTH (5MB) and not empty.
    4. Binary content verified using Pillow (Image.open + verify) to prevent disguised executables.

    Returns:
        str: Relative path of the stored file (e.g. 'chats/3f82a9..._photo.jpg').

    Raises:
        InvalidImageError: If the file fails any security or integrity constraint.
    """
    if not file_storage or not file_storage.filename or file_storage.filename.strip() == "":
        raise InvalidImageError("No file was selected for upload.")

    original_filename = secure_filename(file_storage.filename)
    if "." not in original_filename:
        raise InvalidImageError("File has no extension. Only JPG, JPEG, and PNG images are allowed.")

    ext = original_filename.rsplit(".", 1)[1].lower()
    allowed_extensions = get_allowed_extensions()
    if ext not in allowed_extensions:
        raise InvalidImageError(
            f"File extension '.{ext}' is not permitted. Allowed formats: {', '.join(sorted(allowed_extensions))}."
        )

    # Validate file size by reading stream length
    file_storage.stream.seek(0, os.SEEK_END)
    file_size = file_storage.stream.tell()
    file_storage.stream.seek(0)

    max_size = current_app.config.get("MAX_CONTENT_LENGTH", 5 * 1024 * 1024)
    if file_size > max_size:
        raise InvalidImageError(f"Image exceeds the maximum allowed size of {max_size // (1024 * 1024)}MB.")
    if file_size == 0:
        raise InvalidImageError("Uploaded file is empty.")

    # Deep verification with Pillow to confirm valid image binary
    try:
        img = Image.open(file_storage.stream)
        img.verify()
        format_name = (img.format or "").upper()
        if format_name not in ["JPEG", "PNG"]:
            raise InvalidImageError(f"Detected format '{format_name}' is not supported. Use JPEG or PNG.")
        file_storage.stream.seek(0)
    except InvalidImageError:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as e:
        raise InvalidImageError(f"File is not a valid image or is corrupted: {e!s}") from e

    # Generate collision-free unique filename
    unique_prefix = uuid.uuid4().hex
    stored_filename = f"{unique_prefix}_{original_filename}"

    upload_root = Path(current_app.config["UPLOAD_FOLDER"])
    destination_dir = upload_root / subfolder
    destination_dir.mkdir(parents=True, exist_ok=True)

    destination_path = destination_dir / stored_filename
    file_storage.save(str(destination_path))

    # Return relative path for database persistence
    return f"{subfolder}/{stored_filename}".replace("\\", "/")
