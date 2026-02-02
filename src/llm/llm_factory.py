"""Factory for creating LLM instances using LiteLLM with cost tracking."""

import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Generator, Optional, List, Dict

from loguru import logger

from src.models.llm import LLMMetrics
from src.utils.config import get_settings
from src.utils.logger import setup_logging

try:
    import litellm
    from litellm import completion
except ImportError:
    litellm = None
    completion = None


# Mapping of provider names to their API key environment variables
# Supports the 7 most important providers to keep complexity manageable
PROVIDER_API_KEY_MAP = {
    "anthropic": "ANTHROPIC_API_KEY",  # Default provider, supports prompt caching
    "openai": "OPENAI_API_KEY",  # Most popular, widely used
    "google": "GOOGLE_API_KEY",  # Competitive pricing, multimodal
    "groq": "GROQ_API_KEY",  # Very fast inference, cost-effective
    "cohere": "COHERE_API_KEY",  # Enterprise-focused, strong reasoning
    "mistral": "MISTRAL_API_KEY",  # European provider, good performance
    "bedrock": "AWS_ACCESS_KEY_ID",  # AWS-native, uses AWS credentials
}


def detect_provider_from_model(model_name: str) -> Optional[str]:
    """Detect provider from model name.
    
    Args:
        model_name: Model name (e.g., "gpt-4o-mini", "claude-3-haiku", "anthropic/claude-3-haiku")
        
    Returns:
        Provider name if detected, None otherwise
    """
    model_lower = model_name.lower()
    
    # Check if model name already includes provider prefix
    for provider in PROVIDER_API_KEY_MAP.keys():
        if model_lower.startswith(f"{provider}/"):
            return provider
    
    # Detect from model name patterns (only for supported providers)
    if "claude" in model_lower or "anthropic" in model_lower:
        return "anthropic"
    elif "gpt" in model_lower or "openai" in model_lower:
        return "openai"
    elif "gemini" in model_lower or "palm" in model_lower or "bard" in model_lower:
        return "google"
    elif "command" in model_lower or "cohere" in model_lower:
        return "cohere"
    elif "mistral" in model_lower:
        return "mistral"
    elif "groq" in model_lower:
        return "groq"
    elif "bedrock" in model_lower:
        return "bedrock"
    
    return None


def get_api_key_for_provider(provider: str, settings: Any) -> Optional[str]:
    """Get API key for a specific provider.
    
    Args:
        provider: Provider name (e.g., "openai", "anthropic")
        settings: Settings object
        
    Returns:
        API key if found, None otherwise
    """
    # First try to get from settings object (supports custom attribute names)
    attr_name = f"{provider}_api_key"
    if hasattr(settings, attr_name):
        api_key = getattr(settings, attr_name)
        if api_key:
            return api_key
    
    # Then try environment variable
    env_var = PROVIDER_API_KEY_MAP.get(provider)
    if env_var:
        api_key = os.environ.get(env_var)
        if api_key:
            return api_key
    
    # Special case for AWS Bedrock (requires both access key and secret)
    if provider == "bedrock":
        access_key = os.environ.get("AWS_ACCESS_KEY_ID")
        secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY")
        if access_key and secret_key:
            return access_key  # Return access key as identifier
    
    return None


def format_model_name_for_litellm(model_name: str, provider: Optional[str] = None) -> str:
    """Format model name for LiteLLM.
    
    LiteLLM accepts models in formats like:
    - "gpt-4o-mini" (OpenAI models can omit prefix)
    - "openai/gpt-4o-mini"
    - "anthropic/claude-3-haiku"
    - "google/gemini-pro"
    
    Args:
        model_name: Model name
        provider: Provider name (optional, will be detected if not provided)
        
    Returns:
        Formatted model name
    """
    # If already has provider prefix, return as-is
    if "/" in model_name:
        return model_name
    
    # Detect provider if not provided
    if not provider:
        provider = detect_provider_from_model(model_name)
    
    # Format based on provider
    if provider:
        # Some providers allow omitting prefix (like OpenAI with gpt-* models)
        if provider == "openai" and model_name.startswith("gpt"):
            return model_name  # OpenAI gpt-* models work without prefix
        else:
            return f"{provider}/{model_name}"
    
    # If provider not detected, return as-is (LiteLLM might still work)
    return model_name


class LiteLLMWrapper:
    """Simple wrapper for LiteLLM with cost tracking.
    
    Supports 7 major LLM providers through LiteLLM: Anthropic, OpenAI, Google, Groq,
    Cohere, Mistral, and AWS Bedrock. Automatically handles API key management
    and model name formatting for different providers.
    """
    
    def __init__(
        self,
        model: str,
        api_key: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        streaming: bool = False,
        prompt_caching: bool = False,
    ):
        """Initialize LiteLLM wrapper.
        
        Args:
            model: Model name (e.g., "claude-3-5-sonnet")
            api_key: API key for the provider
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            streaming: Whether to stream responses
            prompt_caching: Enable prompt caching for faster responses (reduces latency up to 80%)
        """
        if completion is None:
            raise ImportError("litellm is not installed. Install with: uv pip install litellm")
        
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.streaming = streaming
        self.prompt_caching = prompt_caching
        self.total_cost = 0.0  # Track total cost across all calls
        self.call_count = 0  # Track number of calls
        self._last_messages: Optional[List[Dict[str, str]]] = None  # Store last prompt/messages for logging
        
        # Setup logging for LLM costs using setup_logging function
        settings = get_settings()
        log_dir = settings.project_root / "logs"
        
        # Use setup_logging to configure cost logging
        # Only configure once per class to avoid reconfiguring multiple times
        if not hasattr(LiteLLMWrapper, "_cost_logger_configured"):
            setup_logging(log_dir=log_dir, name="llm_costs")
            LiteLLMWrapper._cost_logger_configured = True
        
        # Detect provider from model name for logging and API key setup
        detected_provider = detect_provider_from_model(model)
        
        # Set API key in environment if provided
        if api_key:
            if detected_provider:
                env_var = PROVIDER_API_KEY_MAP.get(detected_provider)
                if env_var:
                    os.environ[env_var] = api_key
                    logger.debug(f"Set {env_var} for provider: {detected_provider}")
            else:
                # Fallback: try to detect from model name patterns
                model_lower = model.lower()
                if "claude" in model_lower or "anthropic" in model_lower:
                    os.environ["ANTHROPIC_API_KEY"] = api_key
                elif "gpt" in model_lower or "openai" in model_lower:
                    os.environ["OPENAI_API_KEY"] = api_key
        
        # Log initialization with provider information
        if detected_provider:
            logger.info(f"🤖 Initialized LLM | Provider: {detected_provider} | Model: {model}")
        else:
            logger.info(f"🤖 Initialized LLM | Model: {model} (provider auto-detected by LiteLLM)")
    
    def invoke(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        """Invoke the LLM with messages and log cost.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            **kwargs: Additional parameters
            
        Returns:
            Generated text response
        """
        start_time = time.time()
        stream_mode = kwargs.get("streaming", self.streaming)
        # Store messages for cost logging (prompt trace)
        self._last_messages = messages
        
        # Prepare completion parameters
        completion_params = {
            "model": self.model,
            "messages": messages,
            "temperature": kwargs.get("temperature", self.temperature),
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
            "stream": stream_mode,
        }
        
        # Add prompt caching if enabled (only supported for Anthropic models)
        caching_enabled = kwargs.get("prompt_caching", self.prompt_caching)
        if caching_enabled:
            # Check if provider supports prompt caching
            is_anthropic = "anthropic" in self.model.lower() or "claude" in self.model.lower()
            if is_anthropic:
                # LiteLLM supports prompt caching via caching parameter for Anthropic
                # This enables prompt caching which can reduce latency up to 80%
                completion_params["caching"] = True
                logger.debug(f"Prompt caching enabled for Anthropic model: {self.model}")
            else:
                # Prompt caching is not supported for this provider
                # LiteLLM will ignore the parameter, but we log it for clarity
                logger.debug(
                    f"Prompt caching requested but not supported for provider/model: {self.model}. "
                    f"Prompt caching is currently only supported for Anthropic/Claude models."
                )
        
        # Make the API call
        try:
            response = completion(**completion_params)
        except Exception as e:
            # If model not found, try with date suffix for Anthropic models
            if "not found" in str(e).lower() and "anthropic" in self.model:
                logger.warning(f"Model {self.model} not found, trying with date suffix...")
                alt_model = f"{self.model}-20241022"
                try:
                    # Retry with same caching settings
                    retry_params = completion_params.copy()
                    retry_params["model"] = alt_model
                    response = completion(**retry_params)
                    logger.info(f"Successfully used model: {alt_model}")
                except Exception:
                    raise e
            else:
                raise e
        
        # Handle streaming response
        if stream_mode:
            full_response = ""
            for chunk in response:
                if hasattr(chunk, "choices") and chunk.choices:
                    delta = chunk.choices[0].delta
                    if hasattr(delta, "content") and delta.content:
                        full_response += delta.content
            response_text = full_response
        else:
            # Extract content from response
            if hasattr(response, "choices") and response.choices:
                response_text = response.choices[0].message.content
            elif isinstance(response, dict) and "choices" in response:
                response_text = response["choices"][0]["message"]["content"]
            else:
                response_text = str(response)
        
        # Calculate and log cost
        duration = time.time() - start_time
        self._log_cost(response, duration)
        
        # Store response object for metrics extraction
        self._last_response = response
        
        return response_text
    
    def stream(self, messages: list[dict[str, str]], **kwargs: Any) -> Generator[str, None, None]:
        """Stream tokens from the LLM as they're generated.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            **kwargs: Additional parameters
            
        Yields:
            Token strings as they arrive from the LLM
        """
        start_time = time.time()
        # Store messages for cost logging (prompt trace)
        self._last_messages = messages
        
        # Prepare completion parameters (always use streaming for this method)
        completion_params = {
            "model": self.model,
            "messages": messages,
            "temperature": kwargs.get("temperature", self.temperature),
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
            "stream": True,  # Always stream for this method
        }
        
        # Add prompt caching if enabled
        caching_enabled = kwargs.get("prompt_caching", self.prompt_caching)
        if caching_enabled:
            is_anthropic = "anthropic" in self.model.lower() or "claude" in self.model.lower()
            if is_anthropic:
                completion_params["caching"] = True
                logger.debug(f"Prompt caching enabled for Anthropic model: {self.model}")
        
        # Make the API call
        try:
            response = completion(**completion_params)
        except Exception as e:
            # If model not found, try with date suffix for Anthropic models
            if "not found" in str(e).lower() and "anthropic" in self.model:
                logger.warning(f"Model {self.model} not found, trying with date suffix...")
                alt_model = f"{self.model}-20241022"
                try:
                    retry_params = completion_params.copy()
                    retry_params["model"] = alt_model
                    response = completion(**retry_params)
                    logger.info(f"Successfully used model: {alt_model}")
                except Exception:
                    raise e
            else:
                raise e
        
        # Stream tokens as they arrive
        full_response = ""
        last_chunk = None
        for chunk in response:
            last_chunk = chunk
            if hasattr(chunk, "choices") and chunk.choices:
                delta = chunk.choices[0].delta
                if hasattr(delta, "content") and delta.content:
                    token = delta.content
                    full_response += token
                    yield token
            elif isinstance(chunk, dict) and "choices" in chunk:
                delta = chunk["choices"][0].get("delta", {})
                if delta.get("content"):
                    token = delta["content"]
                    full_response += token
                    yield token
        
        # Store final response for metrics
        duration = time.time() - start_time
        # Create a mock response object for cost tracking
        # We'll use the last chunk if available, or create a minimal response
        try:
            # Try to get usage from the last chunk
            if last_chunk and hasattr(last_chunk, "usage"):
                self._last_response = last_chunk
            else:
                # Create minimal response for cost tracking
                self._last_response = type('obj', (object,), {
                    'usage': type('obj', (object,), {
                        'prompt_tokens': None,
                        'completion_tokens': len(full_response.split()) if full_response else None,
                        'total_tokens': None
                    })()
                })()
            self._log_cost(self._last_response, duration)
        except Exception as e:
            logger.debug(f"Could not log streaming cost: {e}")
    
    def get_last_response_metrics(self) -> Optional[LLMMetrics]:
        """Get metrics from the last LLM response.

        Returns:
            LLMMetrics object with token usage, cost, and other metrics, or None if no response
        """
        if not hasattr(self, "_last_response") or self._last_response is None:
            return None

        response = self._last_response

        # Initialize metrics data
        prompt_tokens = None
        completion_tokens = None
        total_tokens = None
        cost = None
        cost_per_1k_tokens = None

        # Extract token usage
        if hasattr(response, "usage"):
            usage = response.usage
            prompt_tokens = getattr(usage, "prompt_tokens", None)
            completion_tokens = getattr(usage, "completion_tokens", None)
            total_tokens = getattr(usage, "total_tokens", None)
        elif isinstance(response, dict) and "usage" in response:
            usage = response["usage"]
            prompt_tokens = usage.get("prompt_tokens")
            completion_tokens = usage.get("completion_tokens")
            total_tokens = usage.get("total_tokens")

        # Calculate cost
        if litellm:
            try:
                # Pass explicit model name so LiteLLM can price streaming/custom
                # response objects that don't carry the model attribute.
                calculated_cost = litellm.completion_cost(
                    completion_response=response,
                    model=getattr(response, "model", None) or self.model,
                )
                if calculated_cost is not None:
                    cost = calculated_cost
                    if total_tokens:
                        cost_per_1k_tokens = round((calculated_cost / total_tokens * 1000), 6)
            except Exception:
                pass

        # Create and return LLMMetrics model
        return LLMMetrics(
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost=cost,
            cost_per_1k_tokens=cost_per_1k_tokens,
        )
    
    def _log_cost(self, response: Any, duration: float) -> None:
        """Log the cost and details of the LLM call with comprehensive tracking."""
        try:
            # Use a dedicated logger tagged for LLM cost tracking so the
            # llm_costs_* log file only contains these records
            cost_logger = logger.bind(llm_cost=True)

            # Get token usage
            prompt_tokens = None
            completion_tokens = None
            total_tokens = None
            
            if hasattr(response, "usage"):
                usage = response.usage
                prompt_tokens = getattr(usage, "prompt_tokens", None)
                completion_tokens = getattr(usage, "completion_tokens", None)
                total_tokens = getattr(usage, "total_tokens", None)
            elif isinstance(response, dict) and "usage" in response:
                usage = response["usage"]
                prompt_tokens = usage.get("prompt_tokens")
                completion_tokens = usage.get("completion_tokens")
                total_tokens = usage.get("total_tokens")
            
            # Calculate total tokens if not provided
            if total_tokens is None and prompt_tokens and completion_tokens:
                total_tokens = prompt_tokens + completion_tokens
            
            # Calculate cost using LiteLLM
            cost = None
            if litellm:
                try:
                    # Pass explicit model name so LiteLLM can price calls even when
                    # the response object (e.g. streaming wrapper) does not carry it.
                    cost = litellm.completion_cost(
                        completion_response=response,
                        model=getattr(response, "model", None) or self.model,
                    )
                    if cost is not None:
                        self.total_cost += cost
                        self.call_count += 1
                except Exception as e:
                    logger.debug(f"Error calculating cost: {e}")
            
            # Log detailed cost information (tagged as llm_cost)
            cost_logger.info("=" * 80)
            cost_logger.info("💰 LLM Call Cost Tracking")
            cost_logger.info("=" * 80)
            cost_logger.info(f"📊 Model: {self.model}")
            
            if prompt_tokens is not None:
                cost_logger.info(f"📥 Prompt Tokens: {prompt_tokens:,}")
            if completion_tokens is not None:
                cost_logger.info(f"📤 Completion Tokens: {completion_tokens:,}")
            if total_tokens is not None:
                cost_logger.info(f"📊 Total Tokens: {total_tokens:,}")
            
            if cost is not None:
                cost_logger.info(f"💵 Call Cost: ${cost:.6f}")
                cost_logger.info(f"📈 Total Cost (Session): ${self.total_cost:.6f}")
                cost_logger.info(f"🔢 Total Calls: {self.call_count}")
            else:
                cost_logger.warning("⚠️  Cost calculation unavailable")

            # Log prompt / messages for this call so we can inspect what was sent
            if getattr(self, "_last_messages", None):
                # Avoid gigantic one-line logs: show a compact structured view
                try:
                    # Show roles and first 200 characters of each message for readability
                    summarized = [
                        {
                            "role": m.get("role"),
                            "content_preview": (m.get("content") or "")[:200],
                        }
                        for m in self._last_messages
                    ]
                    cost_logger.info(f"📝 Prompt Messages (truncated): {summarized}")
                except Exception as e:
                    cost_logger.debug(f"Could not log prompt messages: {e}")

            cost_logger.info(f"⏱️  Duration: {duration:.2f}s")
            if total_tokens and duration > 0:
                tokens_per_second = total_tokens / duration
                cost_logger.info(f"⚡ Throughput: {tokens_per_second:.1f} tokens/s")
            cost_logger.info("=" * 80)
            
        except Exception as e:
            # Errors here are also tagged so they appear in the cost log file
            cost_logger = logger.bind(llm_cost=True)
            cost_logger.error(f"❌ Error logging cost details: {e}")
            # Still log basic info even if detailed logging fails
            cost_logger.info(f"LLM Call completed | Model: {self.model} | Duration: {duration:.2f}s")

    async def invoke_async(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        """Async version of invoke() - runs in thread pool to avoid blocking event loop.

        This method is identical to invoke() but runs asynchronously, allowing
        other requests to be processed while waiting for LLM response.

        Use this in async endpoints to prevent blocking the event loop during
        LLM API calls, which can take 1-5 seconds.

        Args:
            messages: List of message dicts with 'role' and 'content'
            **kwargs: Additional parameters

        Returns:
            Generated text response

        Example:
            >>> # In async endpoint
            >>> async def chat_endpoint(query: str):
            ...     llm = get_llm()
            ...     response = await llm.invoke_async([
            ...         {"role": "system", "content": "You are a helpful assistant"},
            ...         {"role": "user", "content": query}
            ...     ])
            ...     return {"answer": response}
        """
        import asyncio

        # Run the blocking invoke() in thread pool
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,  # Use default executor
            lambda: self.invoke(messages, **kwargs),
        )

    async def stream_async(self, messages: list[dict[str, str]], **kwargs: Any):
        """Async version of stream() - yields tokens asynchronously.

        This method streams LLM tokens asynchronously, allowing other
        requests to be processed while tokens are being generated.

        Args:
            messages: List of message dicts with 'role' and 'content'
            **kwargs: Additional parameters

        Yields:
            Token strings as they arrive from the LLM

        Example:
            >>> # In async endpoint with streaming
            >>> async def stream_endpoint(query: str):
            ...     llm = get_llm()
            ...     async for token in llm.stream_async([{"role": "user", "content": query}]):
            ...         yield token
        """
        import asyncio

        # Run stream() in a thread and yield tokens asynchronously
        loop = asyncio.get_event_loop()

        # Create a queue to pass tokens from sync to async context
        queue = asyncio.Queue()

        def run_stream():
            """Run the sync stream() and put tokens in queue."""
            try:
                for token in self.stream(messages, **kwargs):
                    # Put token in queue (thread-safe)
                    asyncio.run_coroutine_threadsafe(queue.put(token), loop)
            finally:
                # Signal end of stream
                asyncio.run_coroutine_threadsafe(queue.put(None), loop)

        # Start stream in thread pool
        await loop.run_in_executor(None, run_stream)

        # Yield tokens from queue
        while True:
            token = await queue.get()
            if token is None:
                break
            yield token


def get_llm(
    provider: Optional[str] = None,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    **kwargs: Any,
) -> LiteLLMWrapper:
    """Get LLM instance using LiteLLM.
    
    Supports 7 providers: anthropic (default), openai, google, groq, cohere,
    mistral, and bedrock. Provider can be explicitly specified or auto-detected
    from model name.
    
    The provider can be:
    - Explicitly provided via the provider parameter
    - Set in config/settings.yaml
    - Auto-detected from the model name
    
    API keys are automatically retrieved from:
    - Settings object (e.g., settings.openai_api_key)
    - Environment variables (e.g., OPENAI_API_KEY)
    
    Args:
        provider: Provider name (e.g., "openai", "anthropic", "google", "cohere")
        model: Model name (e.g., "gpt-4o-mini", "claude-3-haiku", "gemini-pro")
        api_key: API key for the provider (optional, will be auto-detected if not provided)
        **kwargs: Additional parameters (temperature, max_tokens, streaming, prompt_caching)
        
    Returns:
        LiteLLMWrapper instance
        
    Examples:
        >>> # Using OpenAI
        >>> llm = get_llm(provider="openai", model="gpt-4o-mini")
        
        >>> # Using Anthropic (auto-detected from model name)
        >>> llm = get_llm(model="claude-3-haiku")
        
        >>> # Using Google
        >>> llm = get_llm(provider="google", model="gemini-pro")
    """
    settings = get_settings()
    
    # Get provider - use provided, or from config, or detect from model name
    model_name = model or settings.llm.model
    config_provider = provider or settings.llm.provider
    
    if not provider:
        provider = config_provider or detect_provider_from_model(model_name)
    
    # Get API key based on provider (generic approach)
    if not api_key and provider:
        api_key = get_api_key_for_provider(provider, settings)
        if api_key:
            logger.debug(f"✅ API key found for provider: {provider}")
        else:
            logger.warning(f"⚠️  No API key found for provider: {provider}. Check environment variables or settings.")
    
    # Format model name for LiteLLM
    model_name = format_model_name_for_litellm(model_name, provider)
    
    # Log provider and model configuration
    if provider:
        logger.info(f"🔧 LLM Configuration | Provider: {provider} | Model: {model_name} | API Key: {'✅ Set' if api_key else '❌ Missing'}")
    else:
        logger.info(f"🔧 LLM Configuration | Model: {model_name} | Provider: Auto-detect | API Key: {'✅ Set' if api_key else '❌ Missing'}")
    
    temperature = kwargs.get("temperature", settings.llm.temperature)
    max_tokens = kwargs.get("max_tokens", settings.llm.max_tokens)
    streaming = kwargs.get("streaming", settings.llm.streaming)
    prompt_caching = kwargs.get("prompt_caching", settings.llm.prompt_caching)
    
    return LiteLLMWrapper(
        model=model_name,
        api_key=api_key,
        temperature=temperature,
        max_tokens=max_tokens,
        streaming=streaming,
        prompt_caching=prompt_caching,
    )
