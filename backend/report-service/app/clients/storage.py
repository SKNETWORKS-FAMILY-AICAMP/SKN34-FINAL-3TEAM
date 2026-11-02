"""S3/MinIO storage. Credentials use the SDK provider chain, never source constants."""

import re
from datetime import UTC, datetime, timedelta
from uuid import UUID

import boto3
from botocore.config import Config


def report_prefix(student_id: UUID, report_id: UUID, revision: int) -> str:
    if revision < 1:
        raise ValueError("Report revision must be positive")
    return f"reports/{student_id}/{report_id}/r{revision}/"


def report_key(
    student_id: UUID, report_id: UUID, revision: int, format: str, audience="full"
) -> str:
    if format not in {"PDF", "MD", "HTML"} or audience not in {"full", "free"}:
        raise ValueError("Invalid report file format/audience")
    return f"{report_prefix(student_id, report_id, revision)}{audience}/{format.lower()}"


class ObjectStorage:
    def __init__(self, client, bucket: str, *, signing_client=None) -> None:
        self._client, self._bucket = client, bucket
        self._signing = signing_client or client

    @classmethod
    def configured(cls):
        from app.config import get_settings

        settings = get_settings()
        config = Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            retries={"total_max_attempts": 1},
            connect_timeout=2,
            read_timeout=10,
        )
        client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            region_name=settings.s3_region,
            config=config,
        )
        signer = (
            boto3.client(
                "s3",
                endpoint_url=settings.s3_public_endpoint_url,
                region_name=settings.s3_region,
                config=config,
            )
            if settings.s3_public_endpoint_url
            else client
        )
        return cls(client, settings.s3_bucket, signing_client=signer)

    def put(self, key: str, body: bytes, content_type: str) -> None:
        self._client.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=body,
            ContentType=content_type,
            CacheControl="private, no-store",
        )

    def presigned_url(self, key: str, ttl: int, filename: str) -> dict:
        if not 1 <= ttl <= 3600:
            raise ValueError("Download URL lifetime must be 1..3600 seconds")
        self._client.head_object(Bucket=self._bucket, Key=key)
        url = self._signing.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": self._bucket,
                "Key": key,
                "ResponseContentDisposition": f'attachment; filename="{filename}"',
            },
            ExpiresIn=ttl,
        )
        return {"url": url, "expiresAt": (datetime.now(UTC) + timedelta(seconds=ttl)).isoformat()}

    def delete_prefix(self, prefix: str) -> None:
        # Only canonical report/student prefixes, never an empty bucket-wide prefix.
        pieces = prefix.split("/")
        if len(pieces) not in (3, 5) or pieces[0] != "reports" or not prefix.endswith("/"):
            raise ValueError("Unsafe report deletion prefix")
        UUID(pieces[1])
        if len(pieces) == 5:
            UUID(pieces[2])
            if not re.fullmatch(r"r[1-9]\d*", pieces[3]):
                raise ValueError("Unsafe report revision prefix")
        keys = []
        for page in self._client.get_paginator("list_objects_v2").paginate(
            Bucket=self._bucket, Prefix=prefix
        ):
            keys.extend({"Key": entry["Key"]} for entry in page.get("Contents", []))
        for index in range(0, len(keys), 1000):
            result = self._client.delete_objects(
                Bucket=self._bucket, Delete={"Objects": keys[index : index + 1000], "Quiet": True}
            )
            if result.get("Errors"):
                raise RuntimeError("Some report objects could not be deleted")

    def close(self):
        self._client.close()
        if self._signing is not self._client:
            self._signing.close()
