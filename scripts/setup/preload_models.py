#!/usr/bin/env python3
"""Pre-download ML models based on config/settings.yaml during Docker build."""

import yaml
import sys
import os
from pathlib import Path

def load_config():
    """Load settings from config/settings.yaml"""
    config_path = Path("config/settings.yaml")
    if not config_path.exists():
        print(f"⚠️  Config file not found: {config_path}", file=sys.stderr)
        return None
    
    with open(config_path, "r") as f:
        return yaml.safe_load(f)

def get_models(config):
    """Extract model names from config"""
    models = {}
    
    # Embedding model
    if "embeddings" in config and "model" in config["embeddings"]:
        models["embedding"] = config["embeddings"]["model"]
    
    # Reranker model
    if "retrieval" in config and "reranker" in config["retrieval"]:
        if "model" in config["retrieval"]["reranker"]:
            models["reranker"] = config["retrieval"]["reranker"]["model"]
    
    return models

def download_models(models):
    """Download models using sentence-transformers"""
    from sentence_transformers import SentenceTransformer, CrossEncoder
    
    # Set cache directory to a shared location accessible by all users
    # This ensures models are available after switching to non-root user
    cache_dir = "/app/.cache/huggingface"
    os.makedirs(cache_dir, exist_ok=True, mode=0o755)
    
    # Set environment variables for Hugging Face cache
    os.environ["HF_HOME"] = cache_dir
    os.environ["TRANSFORMERS_CACHE"] = os.path.join(cache_dir, "transformers")
    os.environ["HF_HUB_CACHE"] = os.path.join(cache_dir, "hub")
    os.environ["SENTENCE_TRANSFORMERS_HOME"] = cache_dir
    
    # Create subdirectories
    for subdir in ["transformers", "hub"]:
        os.makedirs(os.path.join(cache_dir, subdir), exist_ok=True, mode=0o755)
    
    if "embedding" in models:
        model_name = models["embedding"]
        print(f"📥 Downloading embedding model: {model_name}")
        try:
            # Use cache_folder parameter to ensure models go to the right place
            SentenceTransformer(model_name, cache_folder=cache_dir)
            print(f"✅ Embedding model downloaded: {model_name}")
        except Exception as e:
            print(f"❌ Failed to download embedding model {model_name}: {e}", file=sys.stderr)
            sys.exit(1)
    
    if "reranker" in models:
        model_name = models["reranker"]
        print(f"📥 Downloading reranker model: {model_name}")
        try:
            # Use cache_folder parameter to ensure models go to the right place
            CrossEncoder(model_name, cache_folder=cache_dir)
            print(f"✅ Reranker model downloaded: {model_name}")
        except Exception as e:
            print(f"❌ Failed to download reranker model {model_name}: {e}", file=sys.stderr)
            sys.exit(1)

def main():
    print("🔍 Reading config/settings.yaml...")
    config = load_config()
    
    if not config:
        print("⚠️  No config found, skipping model pre-download", file=sys.stderr)
        sys.exit(0)
    
    models = get_models(config)
    
    if not models:
        print("⚠️  No models found in config, skipping pre-download", file=sys.stderr)
        sys.exit(0)
    
    print(f"📋 Found {len(models)} model(s) to pre-download")
    download_models(models)
    print("✅ All models pre-downloaded successfully!")

if __name__ == "__main__":
    main()

