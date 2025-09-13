"""
Retail AI package

This package organizes the app into modules commonly used in production:
- settings: configuration and constants
- adapters: external integrations (DB, LLM)
- domain: prompts and guardrails/business rules
- services: orchestration/business logic
- ui: static assets
"""

__all__ = [
    "settings",
    "adapters",
    "domain",
    "services",
]

