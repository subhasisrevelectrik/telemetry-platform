#!/usr/bin/env python3
"""Check CloudFormation stack events for errors."""
import boto3
from datetime import datetime

def main():
    print("🔍 Checking CloudFormation Events for Errors...\n")

    cf = boto3.client('cloudformation')

    try:
        response = cf.describe_stack_events(StackName='TelemetryStack')
        events = response['StackEvents']

        # Filter for failed events
        print("=" * 80)
        print("FAILED EVENTS:")
        print("=" * 80)

        failed_events = [e for e in events
                        if 'FAILED' in e.get('ResourceStatus', '')]

        if failed_events:
            for event in failed_events[:10]:  # Show first 10 failures
                print(f"\n⏰ Time: {event['Timestamp']}")
                print(f"📦 Resource: {event.get('LogicalResourceId', 'N/A')}")
                print(f"🏷️  Type: {event.get('ResourceType', 'N/A')}")
                print(f"❌ Status: {event['ResourceStatus']}")
                print(f"💬 Reason: {event.get('ResourceStatusReason', 'No reason provided')}")
                print("-" * 80)
        else:
            print("No FAILED events found in recent history")

        # Show all events in chronological order
        print("\n" + "=" * 80)
        print("ALL RECENT EVENTS (chronological):")
        print("=" * 80)

        for event in reversed(events[:20]):  # Show last 20 events
            status = event['ResourceStatus']
            emoji = "✅" if "COMPLETE" in status else "❌" if "FAILED" in status else "⏳"
            print(f"{emoji} {event['Timestamp'].strftime('%H:%M:%S')} | "
                  f"{event.get('LogicalResourceId', 'Stack')[:40]:40} | "
                  f"{status}")

    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()
