# 🧪 Test Suite

Suite completa de tests para ESA IAGen project.

## 📁 Estructura

```
tests/
├── __init__.py
├── conftest.py          # Fixtures compartidos
├── unit/                # Tests unitarios
│   ├── test_retriever.py
│   └── test_router_agent.py
├── integration/         # Tests de integración
│   └── test_api_endpoints.py
└── e2e/                 # Tests end-to-end
    └── (futuro)
```

## 🚀 Ejecutar Tests

### Todos los tests
```bash
pytest
```

### Solo tests unitarios
```bash
pytest tests/unit/
```

### Solo tests de integración
```bash
pytest tests/integration/
```

### Con coverage
```bash
pytest --cov=src --cov-report=html
```

### Tests específicos
```bash
pytest tests/unit/test_retriever.py
pytest tests/integration/test_api_endpoints.py::TestHealthEndpoints
```

### Con marcadores
```bash
pytest -m unit
pytest -m integration
pytest -m "not slow"
```

## 📊 Coverage

El objetivo es mantener >80% de coverage.

Ver reporte HTML:
```bash
pytest --cov=src --cov-report=html
open htmlcov/index.html
```

## 🔧 Fixtures Disponibles

### Fixtures de Aplicación
- `test_app`: FastAPI app instance
- `client`: AsyncClient para testing de API

### Fixtures de Servicios
- `mock_qdrant_client`: Mock Qdrant client
- `mock_qdrant_manager`: Mock QdrantManager
- `mock_embedder`: Mock embedder
- `mock_reranker`: Mock reranker
- `mock_retriever`: Mock AdvancedRetriever
- `mock_llm_service`: Mock LLM service
- `mock_router_agent`: Mock RouterAgent

### Fixtures de Datos
- `sample_documents`: Documentos de ejemplo para testing

## 📝 Escribir Nuevos Tests

### Test Unitario
```python
import pytest
from src.retrieval.retriever import AdvancedRetriever

class TestAdvancedRetriever:
    def test_something(self, mock_retriever):
        result = mock_retriever.retrieve("test")
        assert result is not None
```

### Test de Integración
```python
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_endpoint(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200
```

## 🎯 Mejores Prácticas

1. **Usar fixtures**: Reutilizar fixtures en lugar de crear mocks en cada test
2. **Nombres descriptivos**: `test_retrieve_with_reranking` mejor que `test_1`
3. **Arrange-Act-Assert**: Estructura clara en cada test
4. **Tests independientes**: Cada test debe poder ejecutarse solo
5. **Mock external services**: No depender de servicios externos reales

## ⚠️ Notas

- Los tests usan mocks para evitar dependencias externas (Qdrant, LLMs)
- Variables de entorno de test se configuran automáticamente en `conftest.py`
- Tests de integración pueden requerir servicios corriendo (usar Docker Compose)

## 🔄 CI/CD

Los tests se ejecutan automáticamente en CI/CD:
- En cada PR
- En cada push a `main` o `develop`
- Con coverage reporting

