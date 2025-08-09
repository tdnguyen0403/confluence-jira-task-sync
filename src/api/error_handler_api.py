import functools
import logging
from typing import Any, Callable, Type

from src.api.https_helper import (
    HTTPXClientError,
    HTTPXCustomError,
    HTTPXServerError,
)
from src.exceptions import ApiError

logger = logging.getLogger(__name__)


def handle_api_errors(api_error_class: Type[ApiError]) -> Callable[..., Any]:
    """
    A decorator that catches low-level HTTP exceptions and translates them
    into a specific, domain-level ApiError.

    This decorator centralizes the error translation logic for all methods
    in the SafeJiraApi and SafeConfluenceApi wrappers.

    Args:
        api_error_class (Type[ApiError]): The specific ApiError subclass
            (e.g., JiraApiError, ConfluenceApiError) to be raised on failure.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                # Execute the decorated API call function (e.g., get_issue)
                return await func(*args, **kwargs)
            except (HTTPXClientError, HTTPXServerError, HTTPXCustomError) as e:
                # This is the single place where the translation logic lives.
                func_name = func.__name__
                # The first argument of the wrapped method is 'self',
                # which is the API client instance.
                # This helps in logging which API failed (Jira or Confluence).
                class_name = args[0].__class__.__name__

                log_message = f"API call failed in {class_name}.{func_name}: {e}"
                logger.error(log_message)

                # Raise the specific error class (JiraApiError or ConfluenceApiError)
                # with details from the original exception.
                raise api_error_class(
                    message=log_message,
                    status_code=e.status_code,
                    details=e.details,
                ) from e

        return wrapper

    return decorator
