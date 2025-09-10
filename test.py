
from app.storage import S3Storage
s3 = S3Storage()
from app.config import settings
from app.utilites.storage_utilites import s3_client

import boto3
import os

# Load credentials from environment variables
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION")
AWS_S3_BUCKET = os.getenv("AWS_S3_BUCKET")

s3 = boto3.client(
    "s3",
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name=AWS_REGION
)

# 1. List objects
print("Listing bucket contents:")
response = s3.list_objects_v2(Bucket=AWS_S3_BUCKET)
print(response.get("Contents", "Bucket is empty"))

# 2. Upload a test file
s3.put_object(Bucket=AWS_S3_BUCKET, Key="test_file.txt", Body="Hello Medilogic!")
print("Uploaded test_file.txt")

# 3. Download the test file
s3.download_file(AWS_S3_BUCKET, "test_file.txt", "downloaded_test_file.txt")
print("Downloaded test_file.txt as downloaded_test_file.txt")

# 4. Delete the test file
s3.delete_object(Bucket=AWS_S3_BUCKET, Key="test_file.txt")
print("Deleted test_file.txt")