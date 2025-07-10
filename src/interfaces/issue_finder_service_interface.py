from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class IssueFinderServiceInterface(ABC):
    """
    An abstract base class for a service that finds specific Jira issues
    embedded in Confluence pages.
    """

    @abstractmethod
    def find_issue_on_page(
        self, page_id: str, issue_type_map: Dict[str, str]
    ) -> Optional[Dict[str, Any]]:
        """
        Finds the first Jira macro on a page matching a specified issue type.

        Args:
            page_id (str): The ID of the Confluence page to search.
            issue_type_map (Dict[str, str]): A mapping of issue type names to
                their corresponding IDs (e.g., {"Work Package": "10100"}).

        Returns:
            Optional[Dict[str, Any]]: The full Jira issue dictionary if a
                matching issue is found, otherwise None.
        """
        pass
