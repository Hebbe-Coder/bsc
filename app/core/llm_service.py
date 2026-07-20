"""Compatibility exports for the consolidated LLM service module."""

from app.services.llm_service import LLMService, LLMServiceFactory, get_llm_service, get_thread_local_service

__all__ = ["LLMService", "LLMServiceFactory", "get_llm_service", "get_thread_local_service"]
