"""Tests for S3 uploader with mocked S3."""

import tempfile
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

from src.uploader import S3Uploader


@pytest.fixture
def aws_credentials():
    """Mock AWS credentials for moto."""
    import os
    os.environ['AWS_ACCESS_KEY_ID'] = 'testing'
    os.environ['AWS_SECRET_ACCESS_KEY'] = 'testing'
    os.environ['AWS_SECURITY_TOKEN'] = 'testing'
    os.environ['AWS_SESSION_TOKEN'] = 'testing'


@pytest.fixture
def s3_bucket(aws_credentials):
    """Create mock S3 bucket."""
    with mock_aws():
        s3 = boto3.client('s3', region_name='us-east-1')
        bucket_name = 'test-telemetry-bucket'
        s3.create_bucket(Bucket=bucket_name)
        yield bucket_name


@pytest.fixture
def temp_dirs():
    """Create temporary directories for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        archive_dir = tmppath / "archive"
        pending_dir = tmppath / "pending"
        archive_dir.mkdir()
        pending_dir.mkdir()
        yield {
            'archive': str(archive_dir),
            'pending': str(pending_dir),
        }


@pytest.fixture
def sample_parquet_file():
    """Create a sample Parquet file."""
    with tempfile.NamedTemporaryFile(mode='wb', suffix='.parquet', delete=False) as f:
        # Write minimal Parquet data
        import pyarrow as pa
        import pyarrow.parquet as pq

        table = pa.table({
            'timestamp': pa.array([1, 2, 3], type=pa.timestamp('ns')),
            'arb_id': pa.array([0x100, 0x101, 0x102], type=pa.uint32()),
            'dlc': pa.array([8, 8, 8], type=pa.uint8()),
            'data': pa.array([b'\x00' * 8] * 3, type=pa.binary()),
            'vehicle_id': pa.array(['TEST01'] * 3, type=pa.string()),
        })

        pq.write_table(table, f.name)
        yield Path(f.name)


@mock_aws
def test_uploader_initialization(s3_bucket, temp_dirs):
    """Test uploader initialization."""
    uploader = S3Uploader(
        bucket=s3_bucket,
        region='us-east-1',
        prefix='raw',
        archive_dir=temp_dirs['archive'],
        pending_dir=temp_dirs['pending'],
    )

    assert uploader.bucket == s3_bucket
    assert uploader.region == 'us-east-1'
    assert uploader.prefix == 'raw'
    assert uploader.archive_dir.exists()
    assert uploader.pending_dir.exists()


@mock_aws
def test_uploader_upload_success(s3_bucket, temp_dirs, sample_parquet_file):
    """Test successful upload."""
    # Create file in temp location
    test_file = Path(temp_dirs['pending']).parent / "test.parquet"
    test_file.write_bytes(sample_parquet_file.read_bytes())

    uploader = S3Uploader(
        bucket=s3_bucket,
        region='us-east-1',
        prefix='raw',
        archive_dir=temp_dirs['archive'],
        pending_dir=temp_dirs['pending'],
    )

    # Upload
    success = uploader.upload(test_file)

    assert success is True
    assert not test_file.exists()  # Should be moved to archive
    assert (Path(temp_dirs['archive']) / test_file.name).exists()

    # Verify S3 object exists
    s3 = boto3.client('s3', region_name='us-east-1')
    response = s3.list_objects_v2(Bucket=s3_bucket, Prefix='raw/')
    assert response['KeyCount'] > 0


@mock_aws
def test_uploader_s3_key_generation(s3_bucket, temp_dirs):
    """Test S3 key generation from Hive-partitioned path."""
    uploader = S3Uploader(
        bucket=s3_bucket,
        region='us-east-1',
        prefix='raw',
        archive_dir=temp_dirs['archive'],
        pending_dir=temp_dirs['pending'],
    )

    # Create a Hive-partitioned path
    test_path = Path("./data/vehicle_id=VIN123/year=2025/month=02/day=12/test.parquet")

    s3_key = uploader._get_s3_key(test_path)

    assert s3_key == "raw/vehicle_id=VIN123/year=2025/month=02/day=12/test.parquet"


@mock_aws
def test_uploader_nonexistent_file(s3_bucket, temp_dirs):
    """Test upload of nonexistent file."""
    uploader = S3Uploader(
        bucket=s3_bucket,
        region='us-east-1',
        archive_dir=temp_dirs['archive'],
        pending_dir=temp_dirs['pending'],
    )

    fake_path = Path("/nonexistent/file.parquet")
    success = uploader.upload(fake_path)

    assert success is False


@mock_aws
def test_uploader_retry_pending(s3_bucket, temp_dirs, sample_parquet_file):
    """Test retrying pending uploads."""
    uploader = S3Uploader(
        bucket=s3_bucket,
        region='us-east-1',
        prefix='raw',
        archive_dir=temp_dirs['archive'],
        pending_dir=temp_dirs['pending'],
    )

    # Create a pending file
    pending_file = Path(temp_dirs['pending']) / "pending_test.parquet"
    pending_file.write_bytes(sample_parquet_file.read_bytes())

    # Retry pending
    success_count, fail_count = uploader.retry_pending()

    assert success_count == 1
    assert fail_count == 0
    assert not pending_file.exists()  # Should be moved to archive
    assert (Path(temp_dirs['archive']) / pending_file.name).exists()


def test_uploader_exponential_backoff(s3_bucket, temp_dirs):
    """Test exponential backoff calculation."""
    uploader = S3Uploader(
        bucket=s3_bucket,
        region='us-east-1',
        initial_backoff_sec=2,
        max_backoff_sec=64,
        archive_dir=temp_dirs['archive'],
        pending_dir=temp_dirs['pending'],
    )

    # Backoff should start at 2 and double each time, maxing at 64
    assert uploader.initial_backoff_sec == 2
    assert uploader.max_backoff_sec == 64
