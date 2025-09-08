import boto3
from botocore.exceptions import ClientError
from datetime import timedelta
from fastapi import HTTPException
import os

AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION")
AWS_S3_BUCKET = os.getenv("AWS_S3_BUCKET")

s3_client = boto3.client(
    "s3",
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name=AWS_REGION,
)

def upload_file_to_s3(file_bytes: bytes, key: str, content_type: str):
    try:
        s3_client.put_object(Bucket=AWS_S3_BUCKET, Key=key, Body=file_bytes, ContentType=content_type)
    except ClientError as e:
        raise HTTPException(status_code=500, detail=f"S3 upload failed: {e}")

def generate_presigned_url(key: str, expires_in: int = 3600) -> str:
    try:
        url = s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": AWS_S3_BUCKET, "Key": key},
            ExpiresIn=expires_in,
        )
        return url
    except ClientError as e:
        raise HTTPException(status_code=500, detail=f"S3 presigned URL generation failed: {e}")

def delete_file_from_s3(key: str):
    try:
        s3_client.delete_object(Bucket=AWS_S3_BUCKET, Key=key)
    except ClientError as e:
        raise HTTPException(status_code=500, detail=f"S3 delete failed: {e}")        