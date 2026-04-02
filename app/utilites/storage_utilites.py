# app/utilities/s3_utils.py
import aioboto3
import uuid
import os
from fastapi import UploadFile, HTTPException
from app.utilites.logging import log_activity

AWS_BUCKET = os.getenv("AWS_S3_BUCKET")
AWS_REGION = os.getenv("AWS_REGION")
AWS_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")

async def upload_file_to_s3_async(file, prefix: str, filename: str = None, content_type: str = None) -> str:
    """Uploads a file (UploadFile or regular file object) to S3 asynchronously and returns the S3 key"""
    import mimetypes

    # Determine filename and content type
    if hasattr(file, "filename"):  # FastAPI UploadFile
        ext = os.path.splitext(file.filename)[1]
        filename = filename or file.filename
        content_type = content_type or file.content_type
        content = await file.read()
    else:  # Regular file object (like from open())
        ext = os.path.splitext(filename or "file")[1]
        content = file.read()
        content_type = content_type or mimetypes.guess_type(filename or "file")[0] or "application/octet-stream"

    key = f"pods/{prefix}/{uuid.uuid4().hex}{ext}"

    session = aioboto3.Session()
    async with session.client(
        "s3",
        aws_access_key_id=AWS_ACCESS_KEY,
        aws_secret_access_key=AWS_SECRET_KEY,
        region_name=AWS_REGION
    ) as s3:
        await s3.put_object(
            Bucket=AWS_BUCKET,
            Key=key,
            Body=content,
            ContentType=content_type
        )

    return key

async def generate_presigned_url_async(
    key: str,
    method: str = "get_object",
    expires_in: int = 604800,  # 7 days in seconds
    content_type: str | None = None
) -> str:
    """
    Generate a presigned URL asynchronously for S3.

    Supports both 'get_object' (download) and 'put_object' (upload) methods.
    Optionally includes ContentType for uploads (important for jpg/png/pdf).
    """
    session = aioboto3.Session()

    async with session.client(
        "s3",
        aws_access_key_id=AWS_ACCESS_KEY,
        aws_secret_access_key=AWS_SECRET_KEY,
        region_name=AWS_REGION,
    ) as s3:

        params = {"Bucket": AWS_BUCKET, "Key": key}

        # ✅ Include ContentType if provided (used for uploads)
        if content_type:
            params["ContentType"] = content_type

        url = await s3.generate_presigned_url(
            ClientMethod=method,
            Params=params,
            ExpiresIn=expires_in,
        )

    return url


async def handle_file_upload(app, file: UploadFile, prefix: str, field_name: str, db, user_id: uuid.UUID, action: str):
    """Generic helper to upload, update DB, log, and return presigned URL"""
    try:
        s3_key = await upload_file_to_s3_async(file, prefix)
        setattr(app, field_name + "_path", s3_key)
        db.commit()
        db.refresh(app)
        url = await generate_presigned_url_async(s3_key)
        setattr(app, field_name + "_url", url)
        log_activity(db=db, user_id=user_id, action=action, details=f"Uploaded {prefix} for application {app.id}")
        return app
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to upload {prefix}: {str(e)}")

async def delete_file_from_s3(key: str):
    """Delete a file from S3 asynchronously by key"""
    session = aioboto3.Session()
    async with session.client(
        "s3",
        aws_access_key_id=AWS_ACCESS_KEY,
        aws_secret_access_key=AWS_SECRET_KEY,
        region_name=AWS_REGION
    ) as s3:
        await s3.delete_object(Bucket=AWS_BUCKET, Key=key)
        
        
import boto3

def generate_presigned_url(key: str, expires_in: int = 3600):
    if not key:
        return None

    s3 = boto3.client(
        "s3",
        aws_access_key_id=AWS_ACCESS_KEY,
        aws_secret_access_key=AWS_SECRET_KEY,
        region_name=AWS_REGION,
    )

    try:
        url = s3.generate_presigned_url(
            ClientMethod="get_object",
            Params={
                "Bucket": AWS_BUCKET,
                "Key": key,
            },
            ExpiresIn=expires_in,
        )
        return url
    except Exception as e:
        print("❌ PRESIGNED URL ERROR:", str(e))
        return None