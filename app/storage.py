# app/services/storage.py
import boto3
import uuid
from fastapi import UploadFile
from typing import Tuple
from app.config import settings

# 🔑 Default expiry for presigned URLs (change here once for global effect)
PRESIGNED_EXPIRY = 600  # 10 minutes


class S3Storage:
    def __init__(self):
        """Initialize S3 client."""
        self.client = boto3.client(
            "s3",
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_REGION,
        )
        self.bucket = settings.AWS_S3_BUCKET

    def save_file(self, file: UploadFile) -> Tuple[str, str]:
        """
        Upload file to S3 and return (raw_key, pdf_key).
        For now, raw = pdf (later you can add PDF conversion).
        """
        ext = file.filename.split(".")[-1].lower()
        filename = f"{uuid.uuid4().hex}.{ext}"
        key = f"pods/raw/{filename}"

        # ✅ Upload directly to S3
        self.client.upload_fileobj(file.file, self.bucket, key)

        return key, key

    def generate_download_url(
        self, key: str, expires_in: int = PRESIGNED_EXPIRY
    ) -> str:
        """Generate a presigned URL for downloading an object."""
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires_in,
        )

    def delete_file(self, key: str) -> None:
        """Delete a file from S3."""
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
        except Exception as e:
            print(f"⚠️ Failed to delete {key} from S3: {e}")