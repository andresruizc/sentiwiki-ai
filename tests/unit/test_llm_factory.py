"""Unit tests for LLM factory."""

import os
import pytest
from unittest.mock import Mock, patch, MagicMock

from src.llm.llm_factory import LiteLLMWrapper, get_llm


class TestLiteLLMWrapper:
    """Test suite for LiteLLMWrapper."""
    
    @pytest.fixture
    def mock_litellm(self):
        """Mock litellm module."""
        with patch('src.llm.llm_factory.litellm') as mock_litellm, \
             patch('src.llm.llm_factory.completion') as mock_completion:
            mock_litellm.completion_cost.return_value = 0.001
            yield mock_litellm, mock_completion
    
    @pytest.fixture
    def mock_settings(self):
        """Mock settings."""
        mock_settings = Mock()
        mock_settings.project_root = Mock()
        mock_settings.project_root.__truediv__ = Mock(return_value=Mock())
        return mock_settings
    
    @patch('src.llm.llm_factory.get_settings')
    @patch('src.llm.llm_factory.setup_logging')
    def test_llm_wrapper_initialization(
        self, mock_setup_logging, mock_get_settings, mock_litellm, mock_settings
    ):
        """Test LLM wrapper initialization."""
        mock_litellm_module, mock_completion = mock_litellm
        mock_get_settings.return_value = mock_settings
        
        wrapper = LiteLLMWrapper(
            model="claude-3-haiku",
            api_key="test-key",
            temperature=0.1,
            max_tokens=4096,
        )
        
        assert wrapper.model == "claude-3-haiku"
        assert wrapper.temperature == 0.1
        assert wrapper.max_tokens == 4096
        assert wrapper.total_cost == 0.0
        assert wrapper.call_count == 0
    
    @patch('src.llm.llm_factory.get_settings')
    @patch('src.llm.llm_factory.setup_logging')
    def test_llm_wrapper_without_litellm(
        self, mock_setup_logging, mock_get_settings, mock_settings
    ):
        """Test LLM wrapper raises error when litellm is not installed."""
        mock_get_settings.return_value = mock_settings
        
        with patch('src.llm.llm_factory.completion', None):
            with pytest.raises(ImportError, match="litellm is not installed"):
                LiteLLMWrapper(model="claude-3-haiku")
    
    @patch('src.llm.llm_factory.get_settings')
    @patch('src.llm.llm_factory.setup_logging')
    def test_llm_wrapper_sets_anthropic_api_key(
        self, mock_setup_logging, mock_get_settings, mock_litellm, mock_settings
    ):
        """Test LLM wrapper sets Anthropic API key."""
        mock_litellm_module, mock_completion = mock_litellm
        mock_get_settings.return_value = mock_settings
        
        with patch.dict(os.environ, {}, clear=False):
            wrapper = LiteLLMWrapper(
                model="claude-3-haiku",
                api_key="test-anthropic-key",
            )
            assert os.environ.get("ANTHROPIC_API_KEY") == "test-anthropic-key"
    
    @patch('src.llm.llm_factory.get_settings')
    @patch('src.llm.llm_factory.setup_logging')
    def test_llm_wrapper_sets_openai_api_key(
        self, mock_setup_logging, mock_get_settings, mock_litellm, mock_settings
    ):
        """Test LLM wrapper sets OpenAI API key."""
        mock_litellm_module, mock_completion = mock_litellm
        mock_get_settings.return_value = mock_settings
        
        with patch.dict(os.environ, {}, clear=False):
            wrapper = LiteLLMWrapper(
                model="gpt-4",
                api_key="test-openai-key",
            )
            assert os.environ.get("OPENAI_API_KEY") == "test-openai-key"
    
    @patch('src.llm.llm_factory.get_settings')
    @patch('src.llm.llm_factory.setup_logging')
    def test_llm_wrapper_invoke_non_streaming(
        self, mock_setup_logging, mock_get_settings, mock_litellm, mock_settings
    ):
        """Test LLM wrapper invoke with non-streaming response."""
        mock_litellm_module, mock_completion = mock_litellm
        mock_get_settings.return_value = mock_settings
        
        # Mock response
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message = Mock()
        mock_response.choices[0].message.content = "Test response"
        mock_response.usage = Mock()
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 20
        mock_response.usage.total_tokens = 30
        
        mock_completion.return_value = mock_response
        
        wrapper = LiteLLMWrapper(model="claude-3-haiku")
        result = wrapper.invoke([{"role": "user", "content": "Hello"}])
        
        assert result == "Test response"
        assert wrapper.call_count == 1
        mock_completion.assert_called_once()
    
    @patch('src.llm.llm_factory.get_settings')
    @patch('src.llm.llm_factory.setup_logging')
    def test_llm_wrapper_invoke_streaming(
        self, mock_setup_logging, mock_get_settings, mock_litellm, mock_settings
    ):
        """Test LLM wrapper invoke with streaming response."""
        mock_litellm_module, mock_completion = mock_litellm
        mock_get_settings.return_value = mock_settings
        
        # Mock streaming response
        mock_chunk1 = Mock()
        mock_chunk1.choices = [Mock()]
        mock_chunk1.choices[0].delta = Mock()
        mock_chunk1.choices[0].delta.content = "Test "
        
        mock_chunk2 = Mock()
        mock_chunk2.choices = [Mock()]
        mock_chunk2.choices[0].delta = Mock()
        mock_chunk2.choices[0].delta.content = "response"
        
        mock_completion.return_value = [mock_chunk1, mock_chunk2]
        
        wrapper = LiteLLMWrapper(model="claude-3-haiku", streaming=True)
        result = wrapper.invoke([{"role": "user", "content": "Hello"}], streaming=True)
        
        assert result == "Test response"
    
    @patch('src.llm.llm_factory.get_settings')
    @patch('src.llm.llm_factory.setup_logging')
    def test_llm_wrapper_prompt_caching_anthropic(
        self, mock_setup_logging, mock_get_settings, mock_litellm, mock_settings
    ):
        """Test LLM wrapper enables prompt caching for Anthropic models."""
        mock_litellm_module, mock_completion = mock_litellm
        mock_get_settings.return_value = mock_settings
        
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message = Mock()
        mock_response.choices[0].message.content = "Test"
        mock_completion.return_value = mock_response
        
        wrapper = LiteLLMWrapper(
            model="claude-3-haiku",
            prompt_caching=True,
        )
        wrapper.invoke([{"role": "user", "content": "Hello"}])
        
        # Check that caching parameter was passed
        call_args = mock_completion.call_args
        assert call_args[1].get("caching") is True
    
    @patch('src.llm.llm_factory.get_settings')
    @patch('src.llm.llm_factory.setup_logging')
    def test_llm_wrapper_model_not_found_retry(
        self, mock_setup_logging, mock_get_settings, mock_litellm, mock_settings
    ):
        """Test LLM wrapper retries with date suffix when model not found."""
        mock_litellm_module, mock_completion = mock_litellm
        mock_get_settings.return_value = mock_settings
        
        # Create successful response
        mock_success_response = Mock()
        mock_success_response.choices = [Mock()]
        mock_success_response.choices[0].message = Mock()
        mock_success_response.choices[0].message.content = "Success"
        mock_success_response.usage = Mock()
        mock_success_response.usage.prompt_tokens = 10
        mock_success_response.usage.completion_tokens = 20
        mock_success_response.usage.total_tokens = 30
        
        # Track call count manually
        call_count = [0]
        
        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # First call fails with "not found" error
                raise Exception("Model not found")
            # Second call succeeds
            return mock_success_response
        
        mock_completion.side_effect = side_effect
        
        wrapper = LiteLLMWrapper(model="anthropic/claude-3-haiku")  # Must have "anthropic" in model
        result = wrapper.invoke([{"role": "user", "content": "Hello"}])
        
        assert result == "Success"
        assert call_count[0] == 2
    
    @patch('src.llm.llm_factory.get_settings')
    @patch('src.llm.llm_factory.setup_logging')
    def test_llm_wrapper_get_last_response_metrics(
        self, mock_setup_logging, mock_get_settings, mock_litellm, mock_settings
    ):
        """Test getting metrics from last response."""
        mock_litellm_module, mock_completion = mock_litellm
        mock_get_settings.return_value = mock_settings
        
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message = Mock()
        mock_response.choices[0].message.content = "Test"
        mock_response.usage = Mock()
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 20
        mock_response.usage.total_tokens = 30
        
        mock_completion.return_value = mock_response
        mock_litellm_module.completion_cost.return_value = 0.001
        
        wrapper = LiteLLMWrapper(model="claude-3-haiku")
        wrapper.invoke([{"role": "user", "content": "Hello"}])
        
        metrics = wrapper.get_last_response_metrics()
        
        assert metrics.prompt_tokens == 10
        assert metrics.completion_tokens == 20
        assert metrics.total_tokens == 30
        assert metrics.cost is not None


class TestGetLLM:
    """Test suite for get_llm function."""
    
    @pytest.fixture
    def mock_settings(self):
        """Mock settings."""
        mock_settings = Mock()
        mock_settings.llm.provider = "anthropic"
        mock_settings.llm.model = "claude-3-haiku"
        mock_settings.llm.temperature = 0.1
        mock_settings.llm.max_tokens = 4096
        mock_settings.llm.streaming = False
        mock_settings.llm.prompt_caching = False
        mock_settings.project_root = Mock()
        mock_settings.project_root.__truediv__ = Mock(return_value=Mock())
        return mock_settings
    
    @patch('src.llm.llm_factory.get_settings')
    @patch('src.llm.llm_factory.setup_logging')
    @patch('src.llm.llm_factory.LiteLLMWrapper')
    def test_get_llm_with_defaults(
        self, mock_wrapper_class, mock_setup_logging, mock_get_settings, mock_settings
    ):
        """Test get_llm with default settings."""
        mock_get_settings.return_value = mock_settings
        mock_wrapper = Mock()
        mock_wrapper_class.return_value = mock_wrapper
        
        result = get_llm()
        
        assert result == mock_wrapper
        mock_wrapper_class.assert_called_once()
        call_kwargs = mock_wrapper_class.call_args[1]
        assert call_kwargs["model"] == "anthropic/claude-3-haiku"
    
    @patch('src.llm.llm_factory.get_settings')
    @patch('src.llm.llm_factory.setup_logging')
    @patch('src.llm.llm_factory.LiteLLMWrapper')
    def test_get_llm_with_custom_provider(
        self, mock_wrapper_class, mock_setup_logging, mock_get_settings, mock_settings
    ):
        """Test get_llm with custom provider."""
        mock_get_settings.return_value = mock_settings
        mock_wrapper = Mock()
        mock_wrapper_class.return_value = mock_wrapper
        
        result = get_llm(provider="openai", model="gpt-4")
        
        assert result == mock_wrapper
        call_kwargs = mock_wrapper_class.call_args[1]
        assert "gpt-4" in call_kwargs["model"] or "openai" in call_kwargs["model"]
    
    @patch('src.llm.llm_factory.get_settings')
    @patch('src.llm.llm_factory.setup_logging')
    @patch('src.llm.llm_factory.LiteLLMWrapper')
    def test_get_llm_with_custom_parameters(
        self, mock_wrapper_class, mock_setup_logging, mock_get_settings, mock_settings
    ):
        """Test get_llm with custom parameters."""
        mock_get_settings.return_value = mock_settings
        mock_wrapper = Mock()
        mock_wrapper_class.return_value = mock_wrapper
        
        result = get_llm(temperature=0.5, max_tokens=2048)
        
        assert result == mock_wrapper
        call_kwargs = mock_wrapper_class.call_args[1]
        assert call_kwargs["temperature"] == 0.5
        assert call_kwargs["max_tokens"] == 2048
    
    @patch('src.llm.llm_factory.get_settings')
    @patch('src.llm.llm_factory.setup_logging')
    @patch('src.llm.llm_factory.LiteLLMWrapper')
    def test_get_llm_anthropic_prefix(
        self, mock_wrapper_class, mock_setup_logging, mock_get_settings, mock_settings
    ):
        """Test get_llm adds anthropic/ prefix."""
        mock_get_settings.return_value = mock_settings
        mock_wrapper = Mock()
        mock_wrapper_class.return_value = mock_wrapper
        
        get_llm(provider="anthropic", model="claude-3-haiku")
        
        call_kwargs = mock_wrapper_class.call_args[1]
        assert call_kwargs["model"] == "anthropic/claude-3-haiku"
    
    @patch('src.llm.llm_factory.get_settings')
    @patch('src.llm.llm_factory.setup_logging')
    @patch('src.llm.llm_factory.LiteLLMWrapper')
    def test_get_llm_openai_prefix(
        self, mock_wrapper_class, mock_setup_logging, mock_get_settings, mock_settings
    ):
        """Test get_llm adds openai/ prefix when needed."""
        mock_get_settings.return_value = mock_settings
        mock_wrapper = Mock()
        mock_wrapper_class.return_value = mock_wrapper
        
        get_llm(provider="openai", model="davinci")
        
        call_kwargs = mock_wrapper_class.call_args[1]
        assert call_kwargs["model"] == "openai/davinci"

