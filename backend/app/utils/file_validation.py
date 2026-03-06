import io
import zipfile

ALLOWED_EXTS = {"pdf", "docx", "xlsx", "xls", "csv"}


def is_allowed_file(filename: str) -> bool:
    if "." not in filename:
        return False
    return filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTS


def is_valid_file_content(data: bytes, extension: str) -> bool:
    ext = extension.lower().lstrip(".")
    header = data[:8192]

    if ext == "pdf":
        return b"%PDF-" in header[:1024]

    if ext in ("docx", "xlsx"):
        if not header.startswith(b"PK\x03\x04"):
            return False
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                if ext == "docx":
                    return any(name.startswith("word/") for name in zf.namelist())
                if ext == "xlsx":
                    return any(name.startswith("xl/") for name in zf.namelist())
        except Exception:
            return False
        return True

    if ext == "csv":
        try:
            data[:8192].decode("utf-8")
            return True
        except UnicodeDecodeError:
            return False

    return False
