"""S3 helper scripts."""

import boto3


def list_buckets():
    s3 = boto3.client("s3")
    response = s3.list_buckets()
    for bucket in response.get("Buckets", []):
        print(bucket["Name"])
