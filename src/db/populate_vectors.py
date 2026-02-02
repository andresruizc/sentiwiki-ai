"""Populate Qdrant with document embeddings."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List, Optional

import click
from loguru import logger
import sys
from datetime import datetime
from tqdm import tqdm

# Increase HuggingFace timeout for large model downloads (default is 10s)
os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "300")

from src.db.qdrant_client import QdrantManager
from src.utils.config import get_settings
from src.utils.logger import setup_logging

try:
    from sentence_transformers import SentenceTransformer
except ImportError:  # pragma: no cover
    SentenceTransformer = None


class VectorPopulator:
    """Populates vector database with chunk embeddings."""

    def __init__(
        self,
        input_dir: Path,
        collection_name: str,
        embedding_provider: str,
        embedding_model: str,
        batch_size: int,
        distance: str,
        normalize_embeddings: bool,
        vector_size_override: Optional[int] = None,
    ) -> None:
        self.settings = get_settings()
        self.input_dir = input_dir
        self.batch_size = batch_size
        self.embedding_provider = embedding_provider
        self.embedding_model_name = embedding_model
        self.normalize_embeddings = normalize_embeddings

        self.qdrant = QdrantManager(
            collection_name=collection_name,
            distance=distance,
        )

        self.embedder = self._load_embedder()
        self.vector_size_override = vector_size_override

    def _load_embedder(self):
        if self.embedding_provider == "huggingface":
            if SentenceTransformer is None:
                raise ImportError(
                    "sentence-transformers is required for huggingface embeddings"
                )
            logger.info(f"Loading SentenceTransformer: {self.embedding_model_name}")
            return SentenceTransformer(self.embedding_model_name)

        raise ValueError(f"Unsupported embedding provider: {self.embedding_provider}")

    def load_documents(self) -> List[Dict[str, Dict]]:
        """Load structured chunk JSON files and flatten chunks."""
        if not self.input_dir.exists():
            raise FileNotFoundError(f"Input directory not found: {self.input_dir}")

        documents: List[Dict[str, Dict]] = []
        json_files = sorted(self.input_dir.glob("*.json"))
        
        # Filter out macOS resource fork files (._*)
        # These are metadata files created by macOS and are not valid JSON
        json_files = [f for f in json_files if not f.name.startswith("._")]
        
        if not json_files:
            raise FileNotFoundError(f"No JSON files found in {self.input_dir}")

        for json_path in json_files:
            # Try to read with UTF-8, fallback to other encodings if needed
            try:
                with open(json_path, encoding="utf-8") as f:
                    data = json.load(f)
            except UnicodeDecodeError:
                # Try with error handling (replace invalid chars) or detect encoding
                logger.warning(f"UTF-8 decode failed for {json_path.name}, trying with error handling")
                try:
                    with open(json_path, encoding="utf-8", errors="replace") as f:
                        data = json.load(f)
                    logger.warning(f"Read {json_path.name} with UTF-8 error replacement (some characters may be lost)")
                except Exception as e:
                    # Try latin-1 as fallback (can decode any byte)
                    logger.warning(f"UTF-8 with error handling failed for {json_path.name}, trying latin-1: {e}")
                    try:
                        with open(json_path, encoding="latin-1") as f:
                            content = f.read()
                            # Try to decode as UTF-8 after reading
                            try:
                                content = content.encode("latin-1").decode("utf-8", errors="replace")
                            except Exception:
                                pass  # Use latin-1 content as-is
                            data = json.loads(content)
                        logger.warning(f"Read {json_path.name} using latin-1 encoding")
                    except Exception as e2:
                        logger.error(f"Failed to read {json_path.name} with multiple encoding attempts: {e2}")
                        raise ValueError(
                            f"Could not decode JSON file {json_path.name}. "
                            f"File may be corrupted or use an unsupported encoding. "
                            f"Original error: {e}, Fallback error: {e2}"
                        )

            file_name = data.get("file_name", json_path.name)
            frontmatter = data.get("frontmatter", {})

            for chunk in data.get("chunks", []):
                contextualized = chunk.get("contextualized_text") or chunk.get("text", "")
                metadata = {
                    "file_name": file_name,
                    **frontmatter,
                    **chunk.get("metadata", {}),
                }
                documents.append(
                    {
                        "text": chunk.get("text", ""),
                        "contextualized_text": contextualized,
                        "metadata": metadata,
                    }
                )

        logger.info(f"Loaded {len(documents)} chunks from {len(json_files)} files")
        return documents

    def _embed_batch(self, texts: List[str]) -> List[List[float]]:
        if self.embedding_provider == "huggingface":
            embeddings = self.embedder.encode(
                texts,
                normalize_embeddings=self.normalize_embeddings,
                batch_size=self.batch_size,
                convert_to_numpy=False,
                convert_to_tensor=False,
            )
            return [emb.tolist() if hasattr(emb, "tolist") else emb for emb in embeddings]

        # OpenAI provider via LangChain
        return self.embedder.embed_documents(texts)

    def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for texts."""
        all_embeddings: List[List[float]] = []

        for i in tqdm(range(0, len(texts), self.batch_size), desc="Generating embeddings"):
            batch = texts[i : i + self.batch_size]
            embeddings = self._embed_batch(batch)
            all_embeddings.extend(embeddings)

        return all_embeddings

    def populate(self, recreate: bool) -> None:
        documents = self.load_documents()
        texts = [doc["contextualized_text"] for doc in documents]

        logger.info("Generating embeddings...")
        embeddings = self.generate_embeddings(texts)

        if not embeddings:
            raise ValueError("No embeddings generated. Check input data.")

        vector_size = len(embeddings[0])
        if self.vector_size_override:
            vector_size = self.vector_size_override

        logger.info(
            f"Creating collection with vector_size={vector_size} "
            f"(provider={self.embedding_provider}, model={self.embedding_model_name})"
        )
        self.qdrant.create_collection(
            recreate=recreate,
            vector_size=vector_size,
        )

        logger.info("Inserting embeddings into Qdrant...")
        self.qdrant.insert_documents(documents, embeddings)

        info = self.qdrant.get_collection_info()
        logger.info(f"Collection info: {info}")


@click.command()
@click.option(
    "--input-dir",
    type=click.Path(exists=True, path_type=Path),
    default=lambda: get_settings().data_dir / "processed" / "rag_ready_structured",
    help="Directory containing chunked JSON files",
)
@click.option(
    "--collection",
    type=str,
    default="sentiwiki_index",
    help="Qdrant collection name",
)
@click.option(
    "--provider",
    type=click.Choice(["huggingface", "openai"]),
    default="huggingface",
    help="Embedding provider",
)
@click.option(
    "--model",
    type=str,
    default=None,
    help="Embedding model identifier (defaults to config/settings.yaml)",
)
@click.option(
    "--batch-size",
    type=int,
    default=32,
    help="Embedding batch size",
)
@click.option(
    "--distance",
    type=click.Choice(["Cosine", "Euclid", "Dot"]),
    default="Cosine",
    help="Vector distance metric",
)
@click.option(
    "--normalize/--no-normalize",
    default=True,
    help="Normalize embeddings (only for HuggingFace models)",
)
@click.option(
    "--vector-size",
    type=int,
    default=None,
    help="Override vector size (required for OpenAI if not set in settings)",
)
@click.option(
    "--recreate",
    is_flag=True,
    help="Recreate collection before inserting data",
)

@click.option(
    "--log-dir",
    type=click.Path(path_type=Path),
    default="logs",
    help="Directory for log files",
)
def main(
    input_dir: Path,
    collection: str,
    provider: str,
    model: Optional[str],
    batch_size: int,
    distance: str,
    normalize: bool,
    log_dir: Path,
    vector_size: Optional[int],
    recreate: bool,
) -> None:
    """Main entry point."""

    setup_logging(log_dir=log_dir, name="qdrant_populate_vectors")

    # Use config default if model not provided
    settings = get_settings()
    embedding_model = model or settings.embeddings.model

    populator = VectorPopulator(
        input_dir=input_dir,
        collection_name=collection,
        embedding_provider=provider,
        embedding_model=embedding_model,
        batch_size=batch_size,
        distance=distance,
        normalize_embeddings=normalize,
        vector_size_override=vector_size,
    )
    populator.populate(recreate=recreate)


if __name__ == "__main__":
    main()

