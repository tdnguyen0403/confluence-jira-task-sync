# To test the end-to-end functionality
# of the Jira and Confluence integration,
# including syncing projects, tasks, and undoing syncs.

import asyncio
import json
import logging
import os
from typing import Any, Dict, List  # Added imports

import httpx
from dotenv import load_dotenv

# Set up basic logging for the test script itself
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables for API key and URLs
load_dotenv(
    dotenv_path="./.env.dev"
)
BASE_URL = "http://localhost:8000"
API_KEY = os.getenv("API_SECRET_KEY")
if not API_KEY:
    raise ValueError(
        """API_SECRET_KEY not found in environment variables.
        Please set it in your .env file."""
    )

# --- Test Data (Replace with your actual test data) ---
TEST_USER = "j2t-automator"


async def run_end_to_end_test():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=60.0) as client:
        headers = {"X-API-Key": API_KEY, "Content-Type": "application/json"}

        # 1. Health Check (unchanged)
        logger.info("\n--- Testing /health endpoint ---")
        try:
            response = await client.get("/health")
            response.raise_for_status()
            health_status = response.json()
            logger.info(f"Health Check Response: {health_status}")
            assert health_status["status"] == "ok"
            assert health_status["detail"] == "Application is alive."
            logger.info("Health check passed.")
        except httpx.HTTPStatusError as e:
            logger.error(
                f"Health check failed with HTTP error: "
                f"{e.response.status_code} - {e.response.text}"
            )
            return
        except httpx.RequestError as e:
            logger.error(f"Health check failed with request error: {e}")
            return

        # 2. Readiness Check (unchanged)
        logger.info("\n--- Testing /ready endpoint ---")
        try:
            response = await client.get("/ready", headers=headers)
            response.raise_for_status()
            ready_status = response.json()
            logger.info(f"Readiness Check Response: {ready_status}")
            assert ready_status["status"] == "ready"
            assert ready_status["detail"] == "Application and dependencies are ready."
            logger.info("Readiness check passed. Jira and Confluence are reachable.")
        except httpx.HTTPStatusError as e:
            logger.error(
                f"Readiness check failed with HTTP error: {e.response.status_code} - {e.response.text}"
            )
            logger.error(
                """Ensure JIRA_URL, CONFLUENCE_URL, JIRA_API_TOKEN,
                CONFLUENCE_API_TOKEN are correct and have access."""
            )
            return
        except httpx.RequestError as e:
            logger.error(f"Readiness check failed with request error: {e}")
            return

        # 3. Sync Project (unchanged)
        logger.info("\n--- Testing /sync_project endpoint ---")
        sync_project_payload_1 = {
            "project_page_url": "https://pfteamspace.pepperl-fuchs.com/x/OTBhGg",
            "project_key": "SFSEA-1720",
            "request_user": TEST_USER,
        }

        sync_project_payload_2 = {
            "project_page_url": "https://pfteamspace.pepperl-fuchs.com/x/OTBhGg",
            "project_key": "SFSEA-1721",
            "request_user": TEST_USER,
        }
        try:
            response = await client.post(
                "/sync_project", headers=headers, json=sync_project_payload_1
            )
            response.raise_for_status()
            sync_project_response = response.json()
            logger.info(
                f"Sync Project Response: {json.dumps(sync_project_response, indent=2)}"
            )

            assert "request_id" in sync_project_response
            assert "results" in sync_project_response
            assert isinstance(sync_project_response["results"], list) # Correct for SyncProjectResponse
            logger.info("Sync Project call successful. Verify pages manually.")

            response = await client.post(
                "/sync_project", headers=headers, json=sync_project_payload_2
            )
            response.raise_for_status()
            sync_project_response = response.json()
            logger.info(
                f"Sync Project Response: {json.dumps(sync_project_response, indent=2)}"
            )

            assert "request_id" in sync_project_response
            assert "results" in sync_project_response
            assert isinstance(sync_project_response["results"], list) # Correct for SyncProjectResponse
            logger.info("Sync Project call successful. Verify pages manually.")

        except httpx.HTTPStatusError as e:
            logger.error(
                f"Request failed with HTTP error: "
                f"{e.response.status_code} - {e.response.text}"
            )
            logger.error(f"Request URL: {e.request.url}")
            logger.error(f"Request Headers: {e.request.headers}")
            logger.error(
                f"Request Content (truncated if large): "
                f"{e.request.content[:500] if e.request.content else 'N/A'}"
            )
            logger.error(f"Response Headers: {e.response.headers}")
            logger.error(
                f"Response Content (truncated if large): "
                f"{e.response.text[:500] if e.response.text else 'N/A'}"
            )
            return
        except httpx.RequestError as e:
            logger.error(f"Request failed with network/request error: {e}")
            logger.error(f"Request URL: {e.request.url if e.request else 'N/A'}")
            logger.error(
                f"Request Headers: {e.request.headers if e.request else 'N/A'}"
            )
            logger.error(
                f"Request Content (truncated if large): "
                f"{e.request.content[:500] if e.request and e.request.content else 'N/A'}"
            )
            return

        # 4. Sync Task
        logger.info("\n--- Testing /sync_task endpoint ---")
        sync_task_payload = {
            "confluence_page_urls": [
                "https://pfteamspace.pepperl-fuchs.com/x/W-T3GQ", #normal test page
                "https://pfteamspace.pepperl-fuchs.com/x/cDDsGg"  #locked test page
            ],
            "context": {"request_user": TEST_USER, "days_to_due_date": 7},
        }
        try:
            response = await client.post(
                "/sync_task", headers=headers, json=sync_task_payload
            )
            response.raise_for_status()
            # This is now the comprehensive SyncTaskResponse dictionary
            sync_task_full_response = response.json()

            logger.info(
                f"Sync Task Response: {json.dumps(sync_task_full_response, indent=2)}"
            )

            # Assertions for the comprehensive SyncTaskResponse structure
            assert "request_id" in sync_task_full_response
            assert "overall_jira_task_creation_status" in sync_task_full_response
            assert "overall_confluence_page_update_status" in sync_task_full_response
            assert "jira_task_creation_results" in sync_task_full_response
            assert "confluence_page_update_results" in sync_task_full_response

            # Access the lists from within the full response object
            sync_task_responses_list = sync_task_full_response["jira_task_creation_results"]
            confluence_update_list = sync_task_full_response["confluence_page_update_results"]

            assert isinstance(sync_task_responses_list, list) # This assertion now correctly checks the inner list
            assert isinstance(confluence_update_list, list)

            if sync_task_responses_list:
                # Check the structure of each item in the jira_task_creation_results list
                assert "confluence_page_id" in sync_task_responses_list[0]
                assert "new_jira_task_key" in sync_task_responses_list[0]
                assert "success" in sync_task_responses_list[0]

            # This will now store lists of dictionaries that directly match UndoSyncTaskRequest
            undo_payload: List[Dict[str, Any]] = []
            # Extract results that are eligible for undo (i.e., successful Jira creations)
            # and format them into the simplified UndoSyncTaskRequest structure
            undo_payload = [
                {
                    "confluence_page_id": res["confluence_page_id"],
                    "original_page_version": res["original_page_version"],
                    "new_jira_task_key": res["new_jira_task_key"],
                    "request_user": res["request_user"],
                }
                for res in sync_task_responses_list if res["success"]
            ]

            if not undo_payload:
                logger.warning(
                    """No successful tasks were processed by /sync_task.
                    Cannot proceed with undo test."""
                )
                return

            for result_for_undo in undo_payload:
                assert "new_jira_task_key" in result_for_undo and result_for_undo["new_jira_task_key"] is not None
                assert "confluence_page_id" in result_for_undo
                assert "original_page_version" in result_for_undo
                assert result_for_undo["original_page_version"] is not None

                logger.info(
                    f"Successfully prepared for undo: Jira Key {result_for_undo.get('new_jira_task_key', 'N/A')} "
                    f"on Confluence Page ID {result_for_undo.get('confluence_page_id', 'N/A')} "
                    f"version {result_for_undo.get('original_page_version', 'N/A')}"
                )
                assert sync_task_full_response["overall_jira_task_creation_status"] in ["Success", "Partial Success"]

            logger.info("""Sync Task call successful. Verifying Jira issues "
                        and Confluence page content manually or via API.""")
        except httpx.HTTPStatusError as e:
            logger.error(
                f"Request failed with HTTP error: "
                f"{e.response.status_code} - {e.response.text}"
            )
            logger.error(f"Request URL: {e.request.url}")
            logger.error(f"Request Headers: {e.request.headers}")
            logger.error(
                f"Request Content (truncated if large): "
                f"{e.request.content[:500] if e.request.content else 'N/A'}"
            )
            logger.error(f"Response Headers: {e.response.headers}")
            logger.error(
                f"Response Content (truncated if large): "
                f"{e.response.text[:500] if e.response.text else 'N/A'}"
            )
            return
        except httpx.RequestError as e:
            logger.error(f"Request failed with network/request error: {e}")
            logger.error(f"Request URL: {e.request.url if e.request else 'N/A'}")
            logger.error(
                f"Request Headers: {e.request.headers if e.request else 'N/A'}"
            )
            logger.error(
                f"Request Content (truncated if large): "
                f"{e.request.content[:500] if e.request and e.request.content else 'N/A'}"
            )
            return

        # 5. Undo Sync Task
        logger.info("\n--- Testing /undo_sync_task endpoint ---")
        if not undo_payload:
            logger.info(
                "Skipping /undo_sync_task as no tasks were synced successfully."
            )
            return

        try:
            response = await client.post(
                "/undo_sync_task", headers=headers, json=undo_payload
            )
            response.raise_for_status()
            # The response is now UndoSyncTaskResponse with results and overall status
            undo_sync_response = response.json()
            logger.info(
                f"Undo Sync Task Response: {json.dumps(undo_sync_response, indent=2)}"
            )

            assert "request_id" in undo_sync_response
            assert "results" in undo_sync_response
            assert isinstance(undo_sync_response["results"], list)
            assert "overall_status" in undo_sync_response
            assert undo_sync_response["overall_status"] in ["Success", "Partial Success", "Failed", "Skipped - No actions processed"]

            if undo_sync_response["results"]:
                assert "action_type" in undo_sync_response["results"][0]
                assert "target_id" in undo_sync_response["results"][0]
                assert "success" in undo_sync_response["results"][0]
                assert "status_message" in undo_sync_response["results"][0]

            logger.info("""Undo Sync Task call successful. Verifying Jira issues and
            Confluence page content manually or via API.""")
        except httpx.HTTPStatusError as e:
            logger.error(
                f"Request failed with HTTP error: "
                f"{e.response.status_code} - {e.response.text}"
            )
            logger.error(f"Request URL: {e.request.url}")
            logger.error(f"Request Headers: {e.request.headers}")
            logger.error(
                f"Request Content (truncated if large): "
                f"{e.request.content[:500] if e.request.content else 'N/A'}"
            )
            logger.error(f"Response Headers: {e.response.headers}")
            logger.error(
                f"Response Content (truncated if large): "
                f"{e.response.text[:500] if e.response.text else 'N/A'}"
            )
            return
        except httpx.RequestError as e:
            logger.error(f"Request failed with network/request error: {e}")
            logger.error(f"Request URL: {e.request.url if e.request else 'N/A'}")
            logger.error(
                f"Request Headers: {e.request.headers if e.request else 'N/A'}"
            )
            logger.error(
                f"Request Content (truncated if large): "
                f"{e.request.content[:500] if e.request and e.request.content else 'N/A'}"
            )
            return

    logger.info("\n--- End-to-End Test Sequence Completed ---")


if __name__ == "__main__":
    asyncio.run(run_end_to_end_test())
