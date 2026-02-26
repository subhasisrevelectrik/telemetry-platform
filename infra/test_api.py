#!/usr/bin/env python3
"""Test the deployed API."""
import boto3
import requests
import json

def get_api_url():
    """Get API URL from CloudFormation outputs."""
    cf = boto3.client('cloudformation')
    response = cf.describe_stacks(StackName='TelemetryStack')
    outputs = response['Stacks'][0]['Outputs']

    for output in outputs:
        if output['OutputKey'] == 'ApiUrl':
            return output['OutputValue']

    return None

def main():
    print("🧪 Testing Deployed API...\n")

    # Get API URL
    api_url = get_api_url()
    if not api_url:
        print("❌ Could not find API URL in stack outputs")
        return

    print(f"API URL: {api_url}\n")

    # Test health endpoint
    print("Testing GET / (health check)...")
    try:
        response = requests.get(api_url)
        if response.status_code == 200:
            print(f"✅ Health check passed")
            print(f"   Response: {response.json()}")
        else:
            print(f"⚠️  Status: {response.status_code}")
            print(f"   Response: {response.text}")
    except Exception as e:
        print(f"❌ Error: {e}")

    # Test vehicles endpoint
    print("\nTesting GET /vehicles...")
    try:
        response = requests.get(f"{api_url}vehicles")
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Vehicles endpoint working")
            print(f"   Found {len(data.get('vehicles', []))} vehicles")
        else:
            print(f"   Response: {response.text}")
    except Exception as e:
        print(f"❌ Error: {e}")

    # Test signals endpoint
    print("\nTesting GET /signals...")
    try:
        response = requests.get(f"{api_url}signals")
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            print(f"✅ Signals endpoint working")
        else:
            print(f"   Response: {response.text}")
    except Exception as e:
        print(f"❌ Error: {e}")

    print("\n✨ API testing complete!")
    print(f"\n💡 You can open the API in your browser: {api_url}")

if __name__ == "__main__":
    main()
