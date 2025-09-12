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

async def upload_file_to_s3_async(file: UploadFile, prefix: str) -> str:
    """Uploads file to S3 asynchronously and returns S3 key"""
    ext = os.path.splitext(file.filename)[1]
    key = f"intl_applications/{prefix}/{uuid.uuid4().hex}{ext}"
    content = await file.read()

    session = aioboto3.Session()
    async with session.client(
        "s3",
        aws_access_key_id=AWS_ACCESS_KEY,
        aws_secret_access_key=AWS_SECRET_KEY,
        region_name=AWS_REGION
    ) as s3:
        await s3.put_object(Bucket=AWS_BUCKET, Key=key, Body=content, ContentType=file.content_type)
    return key

async def generate_presigned_url_async(key: str, expires_in: int = 3600) -> str:
    """Generate presigned URL asynchronously"""
    session = aioboto3.Session()
    async with session.client(
        "s3",
        aws_access_key_id=AWS_ACCESS_KEY,
        aws_secret_access_key=AWS_SECRET_KEY,
        region_name=AWS_REGION
    ) as s3:
        url = await s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": AWS_BUCKET, "Key": key},
            ExpiresIn=expires_in
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