import os
import uuid
from fastapi import UploadFile
import shutil

def save_upload_file(file: UploadFile, subfolder: str = "static/uploads") -> str:
    if not file:
        return None

    os.makedirs(subfolder, exist_ok=True)
    filename = f"{uuid.uuid4().hex}_{file.filename}"
    file_path = os.path.join(subfolder, filename)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    return file_path