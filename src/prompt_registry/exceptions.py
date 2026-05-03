class PromptRegistryError(Exception):
    """Base error for the prompt registry."""


class PromptNotFoundError(PromptRegistryError, KeyError):
    """Raised when a prompt name has no entries in the registry."""


class VersionNotFoundError(PromptRegistryError, KeyError):
    """Raised when a specific prompt version cannot be located."""
