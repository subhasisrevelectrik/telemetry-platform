#!/usr/bin/env python3
"""Verify CDK deployment success."""
import boto3
import json
from botocore.exceptions import ClientError

def check_resource(service, check_func, resource_name):
    """Check if a resource exists."""
    try:
        check_func()
        print(f"✅ {service}: {resource_name}")
        return True
    except ClientError as e:
        print(f"❌ {service}: {resource_name} - {e}")
        return False
    except Exception as e:
        print(f"⚠️  {service}: {resource_name} - {e}")
        return False

def main():
    print("🔍 Verifying CDK Deployment...\n")

    # Initialize AWS clients
    s3 = boto3.client('s3')
    lambda_client = boto3.client('lambda')
    apigateway = boto3.client('apigateway')
    glue = boto3.client('glue')
    athena = boto3.client('athena')
    cognito = boto3.client('cognito-idp')
    cloudformation = boto3.client('cloudformation')

    account_id = boto3.client('sts').get_caller_identity()['Account']

    print("=" * 60)
    print("CloudFormation Stack")
    print("=" * 60)

    # Check CloudFormation stack
    try:
        response = cloudformation.describe_stacks(StackName='TelemetryStack')
        stack = response['Stacks'][0]
        status = stack['StackStatus']

        if 'COMPLETE' in status:
            print(f"✅ Stack Status: {status}")
            print(f"\n📋 Stack Outputs:")
            for output in stack.get('Outputs', []):
                print(f"   {output['OutputKey']}: {output['OutputValue']}")
        else:
            print(f"⚠️  Stack Status: {status}")
    except ClientError:
        print("❌ TelemetryStack not found")
        return

    print(f"\n{'=' * 60}")
    print("S3 Buckets")
    print("=" * 60)

    buckets = [
        f"telemetry-data-lake-{account_id}",
        f"telemetry-athena-results-{account_id}",
        f"telemetry-frontend-{account_id}",
    ]

    for bucket in buckets:
        check_resource("S3", lambda b=bucket: s3.head_bucket(Bucket=b), bucket)

    print(f"\n{'=' * 60}")
    print("Glue Resources")
    print("=" * 60)

    check_resource("Glue Database",
                   lambda: glue.get_database(Name='telemetry_db'),
                   "telemetry_db")

    check_resource("Glue Crawler",
                   lambda: glue.get_crawler(Name='telemetry-crawler'),
                   "telemetry-crawler")

    print(f"\n{'=' * 60}")
    print("Athena Resources")
    print("=" * 60)

    check_resource("Athena Workgroup",
                   lambda: athena.get_work_group(WorkGroup='telemetry-workgroup'),
                   "telemetry-workgroup")

    print(f"\n{'=' * 60}")
    print("Lambda Functions")
    print("=" * 60)

    # List Lambda functions with our prefix
    try:
        response = lambda_client.list_functions()
        telemetry_functions = [f for f in response['Functions']
                               if 'TelemetryStack' in f['FunctionName']]

        if telemetry_functions:
            for func in telemetry_functions:
                print(f"✅ Lambda: {func['FunctionName']}")
        else:
            print("⚠️  No Lambda functions found")
    except Exception as e:
        print(f"❌ Error listing Lambda functions: {e}")

    print(f"\n{'=' * 60}")
    print("API Gateway")
    print("=" * 60)

    try:
        response = apigateway.get_rest_apis()
        telemetry_apis = [api for api in response['items']
                          if api['name'] == 'telemetry-api']

        if telemetry_apis:
            api = telemetry_apis[0]
            print(f"✅ API Gateway: {api['name']}")
            print(f"   API ID: {api['id']}")
        else:
            print("⚠️  API Gateway not found")
    except Exception as e:
        print(f"❌ Error checking API Gateway: {e}")

    print(f"\n{'=' * 60}")
    print("Cognito Resources")
    print("=" * 60)

    try:
        response = cognito.list_user_pools(MaxResults=50)
        telemetry_pools = [p for p in response['UserPools']
                           if p['Name'] == 'telemetry-users']

        if telemetry_pools:
            pool = telemetry_pools[0]
            print(f"✅ User Pool: {pool['Name']}")
            print(f"   Pool ID: {pool['Id']}")
        else:
            print("⚠️  User Pool not found")
    except Exception as e:
        print(f"❌ Error checking Cognito: {e}")

    print(f"\n{'=' * 60}")
    print("✨ Verification Complete!")
    print("=" * 60)

if __name__ == "__main__":
    main()
