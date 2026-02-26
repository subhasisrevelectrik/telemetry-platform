#!/usr/bin/env python3
"""AWS CDK app for CAN Telemetry Platform."""

import os

import aws_cdk as cdk

from stacks.telemetry_stack import TelemetryStack

app = cdk.App()

# Define the deployment environment.
# Set CDK_DEFAULT_ACCOUNT and CDK_DEFAULT_REGION in your shell,
# or run `aws login` and CDK will resolve them automatically.
env = cdk.Environment(
    account=os.environ.get("CDK_DEFAULT_ACCOUNT"),
    region=os.environ.get("CDK_DEFAULT_REGION", "us-east-1"),
)

# Create the telemetry stack
TelemetryStack(
    app,
    "TelemetryStack",
    env=env,
    description="CAN Bus Telemetry Platform - Complete infrastructure",
)

app.synth()
