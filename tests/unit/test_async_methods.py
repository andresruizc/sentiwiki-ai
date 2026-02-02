"""Unit tests for async methods in retriever and LLM wrapper."""

import asyncio
import pytest
from unittest.mock import Mock, patch, MagicMock

from src.retrieval.retriever import AdvancedRetriever
from src.llm.llm_factory import LiteLLMWrapper


class TestRetrieverAsync:
    """Test async methods in AdvancedRetriever."""

    @pytest.mark.asyncio
    async def test_retrieve_async_returns_same_as_sync(self):
        """Test that retrieve_async returns same results as retrieve."""
        with patch("src.retrieval.retriever.QdrantManager"), \
             patch("src.retrieval.retriever._model_registry") as mock_registry:

            # Mock the model registry
            mock_embedder = Mock()
            mock_embedder.encode.return_value = [[0.1] * 384]
            mock_registry.get_embedder.return_value = mock_embedder
            mock_registry.get_reranker.return_value = None

            retriever = AdvancedRetriever()

            # Mock the retrieve method
            expected_docs = [
                {"id": "1", "title": "Test Doc", "score": 0.9, "text": "Test content"}
            ]
            retriever.retrieve = Mock(return_value=expected_docs)

            # Call async version
            docs = await retriever.retrieve_async("test query")

            # Should call sync version with correct params
            retriever.retrieve.assert_called_once_with(
                query="test query",
                top_k=None,
                filters=None,
                use_reranking=None,
                use_hybrid=None,
                auto_extract_filters=None,
            )

            # Should return same results
            assert docs == expected_docs

    @pytest.mark.asyncio
    async def test_retrieve_async_runs_in_thread_pool(self):
        """Test that retrieve_async doesn't block event loop."""
        with patch("src.retrieval.retriever.QdrantManager"), \
             patch("src.retrieval.retriever._model_registry") as mock_registry:

            mock_embedder = Mock()
            mock_embedder.encode.return_value = [[0.1] * 384]
            mock_registry.get_embedder.return_value = mock_embedder
            mock_registry.get_reranker.return_value = None

            retriever = AdvancedRetriever()

            # Mock retrieve to simulate slow operation
            def slow_retrieve(*args, **kwargs):
                import time
                time.sleep(0.1)  # 100ms delay
                return [{"id": "1", "score": 0.9}]

            retriever.retrieve = slow_retrieve

            # Run multiple async calls concurrently
            start = asyncio.get_event_loop().time()
            tasks = [
                retriever.retrieve_async("query 1"),
                retriever.retrieve_async("query 2"),
                retriever.retrieve_async("query 3"),
            ]
            results = await asyncio.gather(*tasks)
            duration = asyncio.get_event_loop().time() - start

            # All 3 tasks completed
            assert len(results) == 3

            # Should take ~100ms (parallel) not ~300ms (sequential)
            # Allow some overhead but should be much less than sequential
            assert duration < 0.25, f"Took {duration}s, expected <0.25s (parallel execution)"

    @pytest.mark.asyncio
    async def test_retrieve_async_with_parameters(self):
        """Test retrieve_async passes parameters correctly."""
        with patch("src.retrieval.retriever.QdrantManager"), \
             patch("src.retrieval.retriever._model_registry") as mock_registry:

            mock_registry.get_embedder.return_value = Mock()
            mock_registry.get_reranker.return_value = None

            retriever = AdvancedRetriever()
            retriever.retrieve = Mock(return_value=[])

            # Call with all parameters
            await retriever.retrieve_async(
                query="test",
                top_k=5,
                filters={"mission": "Sentinel-1"},
                use_reranking=True,
                use_hybrid=False,
                auto_extract_filters=False,
            )

            # Verify all parameters were passed
            retriever.retrieve.assert_called_once_with(
                query="test",
                top_k=5,
                filters={"mission": "Sentinel-1"},
                use_reranking=True,
                use_hybrid=False,
                auto_extract_filters=False,
            )


class TestLLMWrapperAsync:
    """Test async methods in LiteLLMWrapper."""

    @pytest.mark.asyncio
    async def test_invoke_async_returns_same_as_sync(self):
        """Test that invoke_async returns same result as invoke."""
        with patch("src.llm.llm_factory.completion") as mock_completion:
            # Mock LiteLLM response
            mock_response = Mock()
            mock_response.choices = [Mock()]
            mock_response.choices[0].message.content = "Test response"
            mock_response.usage = Mock(prompt_tokens=10, completion_tokens=20, total_tokens=30)
            mock_completion.return_value = mock_response

            llm = LiteLLMWrapper(model="gpt-3.5-turbo", temperature=0.7)

            messages = [
                {"role": "system", "content": "You are a helpful assistant"},
                {"role": "user", "content": "Hello"},
            ]

            # Call async version
            response = await llm.invoke_async(messages)

            # Should return same result
            assert response == "Test response"

            # Should have called completion
            assert mock_completion.called

    @pytest.mark.asyncio
    async def test_invoke_async_runs_in_thread_pool(self):
        """Test that invoke_async doesn't block event loop."""
        with patch("src.llm.llm_factory.completion") as mock_completion:
            # Mock slow LLM response
            def slow_completion(*args, **kwargs):
                import time
                time.sleep(0.1)  # 100ms delay
                mock_response = Mock()
                mock_response.choices = [Mock()]
                mock_response.choices[0].message.content = "Response"
                mock_response.usage = Mock(prompt_tokens=10, completion_tokens=20, total_tokens=30)
                return mock_response

            mock_completion.side_effect = slow_completion

            llm = LiteLLMWrapper(model="gpt-3.5-turbo")
            messages = [{"role": "user", "content": "Test"}]

            # Run multiple concurrent calls
            start = asyncio.get_event_loop().time()
            tasks = [
                llm.invoke_async(messages),
                llm.invoke_async(messages),
                llm.invoke_async(messages),
            ]
            results = await asyncio.gather(*tasks)
            duration = asyncio.get_event_loop().time() - start

            # All 3 tasks completed
            assert len(results) == 3

            # Should take ~100ms (parallel) not ~300ms (sequential)
            assert duration < 0.25, f"Took {duration}s, expected <0.25s"

    @pytest.mark.asyncio
    async def test_stream_async_yields_tokens(self):
        """Test that stream_async yields tokens asynchronously."""
        with patch("src.llm.llm_factory.completion") as mock_completion:
            # Mock streaming response
            mock_chunks = [
                Mock(choices=[Mock(delta=Mock(content="Hello"))]),
                Mock(choices=[Mock(delta=Mock(content=" "))]),
                Mock(choices=[Mock(delta=Mock(content="world"))]),
            ]

            # Add usage to last chunk for cost tracking
            mock_chunks[-1].usage = Mock(
                prompt_tokens=10,
                completion_tokens=3,
                total_tokens=13
            )

            mock_completion.return_value = iter(mock_chunks)

            llm = LiteLLMWrapper(model="gpt-3.5-turbo")
            messages = [{"role": "user", "content": "Test"}]

            # Collect tokens from async stream
            tokens = []
            async for token in llm.stream_async(messages):
                tokens.append(token)

            # Should yield all tokens
            assert tokens == ["Hello", " ", "world"]

    @pytest.mark.asyncio
    async def test_invoke_async_with_kwargs(self):
        """Test invoke_async passes kwargs correctly."""
        with patch("src.llm.llm_factory.completion") as mock_completion:
            mock_response = Mock()
            mock_response.choices = [Mock()]
            mock_response.choices[0].message.content = "Response"
            mock_response.usage = Mock(prompt_tokens=10, completion_tokens=20, total_tokens=30)
            mock_completion.return_value = mock_response

            llm = LiteLLMWrapper(model="gpt-3.5-turbo", temperature=0.5, max_tokens=100)

            messages = [{"role": "user", "content": "Test"}]

            # Call with custom kwargs
            await llm.invoke_async(messages, temperature=0.9, max_tokens=500)

            # Verify kwargs were passed to completion
            call_args = mock_completion.call_args
            assert call_args[1]["temperature"] == 0.9
            assert call_args[1]["max_tokens"] == 500


class TestConcurrentAsyncOperations:
    """Test concurrent async operations to verify thread pool benefits."""

    @pytest.mark.asyncio
    async def test_concurrent_retrieval_and_llm_calls(self):
        """Test that retrieval and LLM calls can run concurrently."""
        with patch("src.retrieval.retriever.QdrantManager"), \
             patch("src.retrieval.retriever._model_registry") as mock_registry, \
             patch("src.llm.llm_factory.completion") as mock_completion:

            # Setup mocks
            mock_registry.get_embedder.return_value = Mock(encode=lambda x, **kw: [[0.1] * 384])
            mock_registry.get_reranker.return_value = None

            mock_response = Mock()
            mock_response.choices = [Mock()]
            mock_response.choices[0].message.content = "LLM response"
            mock_response.usage = Mock(prompt_tokens=10, completion_tokens=20, total_tokens=30)
            mock_completion.return_value = mock_response

            retriever = AdvancedRetriever()
            retriever.retrieve = Mock(return_value=[{"id": "1", "score": 0.9}])

            llm = LiteLLMWrapper(model="gpt-3.5-turbo")

            # Run retrieval and LLM concurrently (like in RAG endpoint)
            docs_task = retriever.retrieve_async("query")
            llm_task = llm.invoke_async([{"role": "user", "content": "test"}])

            docs, llm_response = await asyncio.gather(docs_task, llm_task)

            # Both should complete
            assert len(docs) > 0
            assert llm_response == "LLM response"

    @pytest.mark.asyncio
    async def test_many_concurrent_requests(self):
        """Stress test: Many concurrent async requests."""
        with patch("src.retrieval.retriever.QdrantManager"), \
             patch("src.retrieval.retriever._model_registry") as mock_registry:

            mock_embedder = Mock()
            mock_embedder.encode.return_value = [[0.1] * 384]
            mock_registry.get_embedder.return_value = mock_embedder
            mock_registry.get_reranker.return_value = None

            retriever = AdvancedRetriever()
            retriever.retrieve = Mock(return_value=[{"id": "1"}])

            # Simulate 50 concurrent requests
            tasks = [
                retriever.retrieve_async(f"query {i}")
                for i in range(50)
            ]

            start = asyncio.get_event_loop().time()
            results = await asyncio.gather(*tasks)
            duration = asyncio.get_event_loop().time() - start

            # All requests completed
            assert len(results) == 50

            # Should complete reasonably fast (concurrent, not sequential)
            # With 8 workers, 50 requests should take ~7 batches at most
            # Allow generous time for test stability
            assert duration < 1.0, f"50 requests took {duration}s, expected <1s"
