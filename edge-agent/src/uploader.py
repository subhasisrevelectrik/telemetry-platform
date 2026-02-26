"""S3 uploader with retry logic and multipart support."""

import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Tuple

import boto3
from botocore.exceptions import ClientError, EndpointConnectionError

logger = logging.getLogger(__name__)


class S3Uploader:
    """Uploads Parquet files to S3 with retry logic."""

    def __init__(
        self,
        bucket: str,
        region: str = "us-east-1",
        prefix: str = "raw",
        max_retries: int = 5,
        initial_backoff_sec: int = 2,
        max_backoff_sec: int = 300,
        archive_dir: str = "./data/archive",
        pending_dir: str = "./data/pending",
    ):
        """
        Initialize S3 uploader.

        Args:
            bucket: S3 bucket name
            region: AWS region
            prefix: S3 prefix for uploads
            max_retries: Maximum retry attempts
            initial_backoff_sec: Initial backoff delay in seconds
            max_backoff_sec: Maximum backoff delay in seconds
            archive_dir: Directory for successfully uploaded files
            pending_dir: Directory for files awaiting upload
        """
        self.bucket = bucket
        self.region = region
        self.prefix = prefix
        self.max_retries = max_retries
        self.initial_backoff_sec = initial_backoff_sec
        self.max_backoff_sec = max_backoff_sec
        self.archive_dir = Path(archive_dir)
        self.pending_dir = Path(pending_dir)

        # Create directories
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        self.pending_dir.mkdir(parents=True, exist_ok=True)

        # Initialize S3 client
        self.s3_client = boto3.client("s3", region_name=region)

        logger.info(
            f"Initialized S3 uploader: bucket={bucket}, region={region}, "
            f"prefix={prefix}"
        )

    def _get_s3_key(self, local_path: Path) -> str:
        """
        Generate S3 key from local Hive-partitioned path.

        Args:
            local_path: Local file path

        Returns:
            S3 key
        """
        # Extract Hive partitions from path
        # Example: ./data/vehicle_id=X/year=Y/month=M/day=D/file.parquet
        parts = local_path.parts

        # Find partition components
        partition_parts = []
        for part in parts:
            if "=" in part:  # Hive partition format
                partition_parts.append(part)

        # Add filename
        filename = local_path.name

        # Build S3 key: prefix/vehicle_id=X/year=Y/month=M/day=D/file.parquet
        key_parts = [self.prefix] + partition_parts + [filename]
        s3_key = "/".join(key_parts)

        return s3_key

    def _upload_with_retry(self, local_path: Path, s3_key: str) -> bool:
        """
        Upload file with exponential backoff retry.

        Args:
            local_path: Local file path
            s3_key: S3 object key

        Returns:
            True if upload succeeded, False otherwise
        """
        backoff = self.initial_backoff_sec

        for attempt in range(self.max_retries):
            try:
                # Check if file is large (> 100 MB) - use multipart
                file_size = local_path.stat().st_size
                if file_size > 100 * 1024 * 1024:
                    logger.info(
                        f"Using multipart upload for large file: "
                        f"{file_size / (1024*1024):.1f} MB"
                    )
                    self._multipart_upload(local_path, s3_key)
                else:
                    # Regular upload
                    self.s3_client.upload_file(
                        str(local_path),
                        self.bucket,
                        s3_key,
                        ExtraArgs={
                            "StorageClass": "STANDARD",
                            "ServerSideEncryption": "AES256",
                        },
                    )

                logger.info(
                    f"Upload succeeded: s3://{self.bucket}/{s3_key} "
                    f"(attempt {attempt + 1}/{self.max_retries})"
                )
                return True

            except EndpointConnectionError as e:
                logger.warning(
                    f"No network connection (attempt {attempt + 1}/{self.max_retries}): {e}"
                )
                if attempt < self.max_retries - 1:
                    logger.info(f"Retrying in {backoff}s...")
                    time.sleep(backoff)
                    backoff = min(backoff * 2, self.max_backoff_sec)
                else:
                    logger.error("Max retries reached, upload failed (offline)")
                    return False

            except ClientError as e:
                error_code = e.response.get("Error", {}).get("Code", "Unknown")
                logger.error(
                    f"S3 client error (attempt {attempt + 1}/{self.max_retries}): "
                    f"{error_code} - {e}"
                )
                if attempt < self.max_retries - 1:
                    logger.info(f"Retrying in {backoff}s...")
                    time.sleep(backoff)
                    backoff = min(backoff * 2, self.max_backoff_sec)
                else:
                    logger.error("Max retries reached, upload failed")
                    return False

            except Exception as e:
                logger.error(f"Unexpected error during upload: {e}")
                return False

        return False

    def _multipart_upload(self, local_path: Path, s3_key: str) -> None:
        """
        Perform multipart upload for large files.

        Args:
            local_path: Local file path
            s3_key: S3 object key
        """
        # Initiate multipart upload
        response = self.s3_client.create_multipart_upload(
            Bucket=self.bucket,
            Key=s3_key,
            StorageClass="STANDARD",
            ServerSideEncryption="AES256",
        )
        upload_id = response["UploadId"]

        try:
            # Upload parts (5 MB chunks)
            part_size = 5 * 1024 * 1024
            parts = []
            part_number = 1

            with open(local_path, "rb") as f:
                while True:
                    data = f.read(part_size)
                    if not data:
                        break

                    response = self.s3_client.upload_part(
                        Bucket=self.bucket,
                        Key=s3_key,
                        PartNumber=part_number,
                        UploadId=upload_id,
                        Body=data,
                    )

                    parts.append({
                        "PartNumber": part_number,
                        "ETag": response["ETag"],
                    })

                    part_number += 1

            # Complete multipart upload
            self.s3_client.complete_multipart_upload(
                Bucket=self.bucket,
                Key=s3_key,
                UploadId=upload_id,
                MultipartUpload={"Parts": parts},
            )

        except Exception as e:
            # Abort on error
            logger.error(f"Multipart upload failed, aborting: {e}")
            self.s3_client.abort_multipart_upload(
                Bucket=self.bucket,
                Key=s3_key,
                UploadId=upload_id,
            )
            raise

    def upload(self, local_path: Path) -> bool:
        """
        Upload file to S3 and move to archive or pending.

        Args:
            local_path: Local file path

        Returns:
            True if upload succeeded, False otherwise
        """
        if not local_path.exists():
            logger.error(f"File does not exist: {local_path}")
            return False

        # Generate S3 key
        s3_key = self._get_s3_key(local_path)

        logger.info(f"Uploading: {local_path} -> s3://{self.bucket}/{s3_key}")

        # Attempt upload
        success = self._upload_with_retry(local_path, s3_key)

        if success:
            # Move to archive
            archive_path = self.archive_dir / local_path.name
            local_path.rename(archive_path)
            logger.info(f"Moved to archive: {archive_path}")
        else:
            # Move to pending for later retry
            pending_path = self.pending_dir / local_path.name
            if not pending_path.exists():
                local_path.rename(pending_path)
                logger.info(f"Moved to pending: {pending_path}")

        return success

    def retry_pending(self) -> Tuple[int, int]:
        """
        Retry uploading files in pending directory.

        Returns:
            Tuple of (successful_count, failed_count)
        """
        pending_files = list(self.pending_dir.glob("*.parquet"))

        if not pending_files:
            return (0, 0)

        logger.info(f"Retrying {len(pending_files)} pending uploads...")

        success_count = 0
        fail_count = 0

        for pending_path in pending_files:
            # Generate S3 key from filename
            # Need to reconstruct partition path from filename
            # This is a simplified version - in production, store metadata
            s3_key = f"{self.prefix}/{pending_path.name}"

            if self._upload_with_retry(pending_path, s3_key):
                # Move to archive
                archive_path = self.archive_dir / pending_path.name
                pending_path.rename(archive_path)
                success_count += 1
            else:
                fail_count += 1

        logger.info(
            f"Pending retry complete: {success_count} succeeded, "
            f"{fail_count} failed"
        )

        return (success_count, fail_count)
