#!/usr/bin/env python3
"""Quick script to get AWS account ID."""
import boto3

try:
    sts = boto3.client('sts')
    identity = sts.get_caller_identity()
    print(f"Account ID: {identity['Account']}")
    print(f"User ARN: {identity['Arn']}")
except Exception as e:
    print(f"Error: {e}")
    print("\nMake sure AWS credentials are configured correctly.")
