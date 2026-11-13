import os
from pathlib import Path
import boto3

ROOT = Path(os.getenv('UPLOAD_DIR', './uploads')).resolve()
MODE = os.getenv('STORAGE_MODE', 'local')
BUCKET = os.getenv('S3_BUCKET', 'invoices')

def client():
    return boto3.client('s3', endpoint_url=os.getenv('S3_ENDPOINT'),
        aws_access_key_id=os.getenv('S3_ACCESS_KEY'), aws_secret_access_key=os.getenv('S3_SECRET_KEY'),
        region_name='us-east-1')

def initialize():
    if MODE == 'local':
        ROOT.mkdir(parents=True, exist_ok=True)
    elif MODE == 's3':
        from botocore.exceptions import ClientError
        s3 = client()
        try:
            s3.head_bucket(Bucket=BUCKET)
        except ClientError as exc:
            if exc.response['Error']['Code'] not in ('404', 'NoSuchBucket'):
                raise
            s3.create_bucket(Bucket=BUCKET)
    else:
        raise ValueError('STORAGE_MODE doit être local ou s3')

def put(key, data, content_type):
    if MODE == 's3':
        client().put_object(Bucket=BUCKET, Key=key, Body=data, ContentType=content_type)
    else:
        (ROOT / key).write_bytes(data)

def read(key):
    if MODE == 's3':
        return client().get_object(Bucket=BUCKET, Key=key)['Body'].read()
    return (ROOT / key).read_bytes()

def remove(key):
    if MODE == 's3':
        client().delete_object(Bucket=BUCKET, Key=key)
    else:
        (ROOT / key).unlink(missing_ok=True)
