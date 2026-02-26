"""Athena client wrapper for querying telemetry data."""

import logging
import time
from typing import Any, Dict, List

import boto3
from botocore.exceptions import ClientError

from .config import settings

logger = logging.getLogger(__name__)


class AthenaClient:
    """Wrapper around boto3 Athena client."""

    def __init__(self):
        """Initialize Athena client."""
        self.client = boto3.client("athena", region_name=settings.aws_region)
        self.database = settings.athena_database
        self.output_location = f"s3://{settings.athena_results_bucket}/query-results/"

    def start_query(self, sql: str) -> str:
        """
        Start an Athena query execution.

        Args:
            sql: SQL query string

        Returns:
            Query execution ID
        """
        response = self.client.start_query_execution(
            QueryString=sql,
            QueryExecutionContext={"Database": self.database},
            ResultConfiguration={
                "OutputLocation": self.output_location,
            },
        )

        execution_id = response["QueryExecutionId"]
        logger.info(f"Started query: {execution_id}")
        return execution_id

    def poll_query(self, execution_id: str, timeout: int = 30) -> str:
        """
        Poll query status until complete or timeout.

        Args:
            execution_id: Query execution ID
            timeout: Maximum wait time in seconds

        Returns:
            Final query state (SUCCEEDED, FAILED, CANCELLED)
        """
        start_time = time.time()

        while True:
            response = self.client.get_query_execution(QueryExecutionId=execution_id)
            state = response["QueryExecution"]["Status"]["State"]

            if state in ["SUCCEEDED", "FAILED", "CANCELLED"]:
                logger.info(f"Query {execution_id}: {state}")

                # Log failure reason if query failed
                if state == "FAILED":
                    reason = response["QueryExecution"]["Status"].get("StateChangeReason", "Unknown")
                    logger.error(f"Query failed: {reason}")
                    print(f"ATHENA ERROR: {reason}")

                return state

            if time.time() - start_time > timeout:
                logger.error(f"Query {execution_id} timeout after {timeout}s")
                return "TIMEOUT"

            time.sleep(0.5)

    def get_results(self, execution_id: str) -> List[Dict[str, Any]]:
        """
        Get query results.

        Args:
            execution_id: Query execution ID

        Returns:
            List of result rows as dictionaries
        """
        results = []
        paginator = self.client.get_paginator("get_query_results")

        for page in paginator.paginate(QueryExecutionId=execution_id):
            # Skip header row
            rows = page["ResultSet"]["Rows"]

            if not results:  # First page
                column_names = [col["VarCharValue"] for col in rows[0]["Data"]]
                rows = rows[1:]  # Skip header
            else:
                column_names = [col["VarCharValue"] for col in page["ResultSet"]["Rows"][0]["Data"]]

            for row in rows:
                row_dict = {}
                for i, col in enumerate(row["Data"]):
                    value = col.get("VarCharValue")
                    row_dict[column_names[i]] = value
                results.append(row_dict)

        return results

    def run_query(self, sql: str, timeout: int = 30) -> List[Dict[str, Any]]:
        """
        Execute query and return results.

        Args:
            sql: SQL query string
            timeout: Maximum wait time in seconds

        Returns:
            List of result rows as dictionaries
        """
        execution_id = self.start_query(sql)
        state = self.poll_query(execution_id, timeout)

        if state != "SUCCEEDED":
            raise RuntimeError(f"Query failed with state: {state}")

        return self.get_results(execution_id)
