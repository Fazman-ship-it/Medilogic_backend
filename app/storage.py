# app/services/storage.py
import boto3, uuid
from fastapi import UploadFile
from app.config import settings
from typing import Tuple


class S3Storage:
    def __init__(self):  # ✅ constructor
        self.client = boto3.client(
            "s3",
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_REGION,
        )
        self.bucket = settings.AWS_S3_BUCKET

    def save_file(self, file: UploadFile) -> Tuple[str, str]:
        """Upload file to S3 and return (raw_key, pdf_key)."""
        ext = file.filename.split(".")[-1]
        filename = f"{uuid.uuid4().hex}.{ext}"
        key = f"pods/raw/{filename}"

        # Upload directly to S3
        self.client.upload_fileobj(file.file, self.bucket, key)

        # For now, raw = pdf (later you’ll plug in PDF conversion logic)
        return key, key  

    def generate_download_url(self, key: str, expires_in: int = 600) -> str:
        """Return presigned download URL."""
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires_in
        )
        
