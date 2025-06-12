"""
Utility functions for the Deadline Cloud MCP Server.

Consolidates common functionality like name conversion to eliminate duplication.
"""

import re


class NameConverter:
    """Handles name conversions between different naming conventions."""

    @staticmethod
    def to_snake_case(name: str) -> str:
        """
        Convert PascalCase/camelCase to snake_case.

        Args:
            name: PascalCase or camelCase string

        Returns:
            str: snake_case string

        Examples:
            GetFarm -> get_farm
            ListQueues -> list_queues
            GetQueueEnvironment -> get_queue_environment
        """
        result = []
        for i, char in enumerate(name):
            if char.isupper() and i > 0:
                result.append("_")
            result.append(char.lower())
        return "".join(result)

    @staticmethod
    def to_kebab_case(name: str) -> str:
        """
        Convert PascalCase to kebab-case.

        Args:
            name: PascalCase string (e.g., 'QueueFleetAssociations')

        Returns:
            str: kebab-case string (e.g., 'queue-fleet-associations')

        Examples:
            QueueFleetAssociations -> queue-fleet-associations
            GetFarm -> get-farm
        """
        # Insert hyphens before capital letters (except the first one)
        result = re.sub(r"(?<!^)(?=[A-Z])", "-", name)
        return result.lower()

    @staticmethod
    def to_camel_case(snake_name: str) -> str:
        """
        Convert snake_case to camelCase.

        Args:
            snake_name: snake_case string

        Returns:
            str: camelCase string

        Examples:
            farm_id -> farmId
            queue_environment_id -> queueEnvironmentId
        """
        words = snake_name.split("_")
        if len(words) == 1:
            return words[0]
        else:
            return words[0] + "".join(word.capitalize() for word in words[1:])
