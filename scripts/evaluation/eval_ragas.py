#!/usr/bin/env python3
"""
RAGAS Evaluation Script for ECSS Standards RAG System

This script evaluates the ECSS RAG system using RAGAS metrics:
- Context Precision
- Context Recall
- Faithfulness
- Answer Relevancy
"""

import os
import sys
import time
from pathlib import Path
from typing import List, Dict, Any, Optional

import click
from datasets import Dataset
from loguru import logger
import pandas as pd

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.llm.llm_factory import get_llm
from src.retrieval.retriever import AdvancedRetriever
from src.utils.config import get_settings
from src.utils.logger import setup_logger

try:
    from ragas import evaluate, RunConfig
    from ragas.metrics import (
        context_precision,
        context_recall,
        faithfulness,
        answer_relevancy,
    )
    from ragas.llms import LangchainLLMWrapper
    from ragas.embeddings import LangchainEmbeddingsWrapper # <--- NEW
except ImportError:
    logger.error(
        "RAGAS dependencies missing.\n"
        "Run: uv add ragas datasets pandas langchain-anthropic langchain-huggingface sentence-transformers"
    )
    sys.exit(1)

try:
    from langchain_anthropic import ChatAnthropic
    # New import for local embeddings
    from langchain_huggingface import HuggingFaceEmbeddings 
    LANGCHAIN_AVAILABLE = True
except ImportError:
    ChatAnthropic = None
    HuggingFaceEmbeddings = None
    LANGCHAIN_AVAILABLE = False
    logger.warning("LangChain dependencies missing. Install langchain-anthropic and langchain-huggingface.")

GOLDEN_DATASET = [
  # ===================================================================
  # 🛑 CATEGORY 1: HALLUCINATION & NEGATIVE CONSTRAINTS (The "Killer" Tests)
  # ===================================================================
  {
    "difficulty": "Hard",
    "capability": "Hallucination Check",
    "filtering_test": "negative_constraint",
    "question": "What is the swath width of the Sentinel-2 SAR instrument?",
    "ground_truth": "Sentinel-2 does not carry a SAR instrument; it is an optical mission (MSI). Sentinel-1 is the SAR mission."
  },
  {
    "difficulty": "Hard",
    "capability": "Hallucination Check",
    "filtering_test": "negative_constraint",
    "question": "Can Sentinel-1 detect vegetation health using the Red Edge band?",
    "ground_truth": "No. Sentinel-1 is a Radar (SAR) satellite. Vegetation health via Red Edge bands is monitored by the Optical satellite Sentinel-2."
  },
  {
    "difficulty": "Medium",
    "capability": "Negative Constraint",
    "filtering_test": "negative_test",
    "question": "Does Sentinel-2 carry a Thermal Infrared (TIR) sensor?",
    "ground_truth": "No, Sentinel-2 does not carry a thermal infrared sensor. Land Surface Temperature monitoring is covered by Sentinel-3 and the future LSTM mission."
  },

  # ===================================================================
  # ⏳ CATEGORY 2: TEMPORAL & STATUS (Tests "Current Knowledge")
  # ===================================================================
  {
    "difficulty": "Hard",
    "capability": "Temporal Reasoning",
    "filtering_test": "status_check",
    "question": "Is the Sentinel-1B satellite currently operational?",
    "ground_truth": "No. The Sentinel-1B mission ended on August 3, 2022, following a power supply anomaly in December 2021."
  },
  {
    "difficulty": "Hard",
    "capability": "Temporal Reasoning",
    "filtering_test": "status_check",
    "question": "Has the Sentinel-4 mission been launched? If so, on which platform?",
    "ground_truth": "Yes, Sentinel-4 launched on July 1, 2025, onboard the MTG-S1 (Meteosat Third Generation Sounder-1) satellite."
  },

  # ===================================================================
  # 📡 CATEGORY 3: SENTINEL-1 (SAR EXPERTISE)
  # ===================================================================
  {
    "difficulty": "Medium",
    "capability": "Fact Retrieval",
    "filtering_test": "mission_specific",
    "question": "What is the default acquisition mode for Sentinel-1 over land, and what are its swath width and spatial resolution?",
    "ground_truth": "The default mode is Interferometric Wide (IW). It has a swath width of 250 km and a spatial resolution of 5 m x 20 m."
  },
  {
    "difficulty": "Hard",
    "capability": "Contextual Retrieval",
    "filtering_test": "technical_nuance",
    "question": "Why does Sentinel-1 Wave Mode (WV) not provide a continuous image strip?",
    "ground_truth": "WV mode acquires data in small 'vignettes' of 20 km x 20 km spaced at 100 km intervals along the track to sample ocean waves, rather than a continuous strip."
  },
  {
    "difficulty": "Hard",
    "capability": "Syntax Specificity",
    "filtering_test": "naming_convention",
    "question": "What is the exact naming convention for the Sentinel-1 Precise Orbit Ephemerides (POE) auxiliary file?",
    "ground_truth": "The file type is AUX_POEORB. It is generated with a latency of 20 days (Non-Time Critical)."
  },
  {
    "difficulty": "Medium",
    "capability": "Fact Retrieval",
    "filtering_test": "acronym_heavy",
    "question": "Explain the difference between Level-1 SLC and Level-1 GRD products for Sentinel-1.",
    "ground_truth": "SLC (Single Look Complex) contains phase and amplitude information in slant range geometry. GRD (Ground Range Detected) contains only detected amplitude projected to ground range with phase information lost."
  },

  # ===================================================================
  # 📸 CATEGORY 4: SENTINEL-2 (OPTICAL EXPERTISE)
  # ===================================================================
  {
    "difficulty": "Medium",
    "capability": "Tabular Extraction",
    "filtering_test": "tabular_data",
    "question": "List the central wavelengths and spatial resolutions for Sentinel-2 Band 2, Band 3, and Band 4.",
    "ground_truth": "Band 2 (Blue): ~490 nm, 10 m. Band 3 (Green): ~560 nm, 10 m. Band 4 (Red): ~665 nm, 10 m."
  },
  {
    "difficulty": "Medium",
    "capability": "Fact Retrieval",
    "filtering_test": "mission_specific",
    "question": "What is the revisit time of the Sentinel-2 constellation at the Equator with two satellites?",
    "ground_truth": "The revisit time at the Equator is 5 days with two satellites."
  },
  {
    "difficulty": "Hard",
    "capability": "Contextual Retrieval",
    "filtering_test": "technical_nuance",
    "question": "For Sentinel-2 Processing Baseline 04.00, what is the value of the radiometric offset added to the Digital Numbers?",
    "ground_truth": "The offset is -1000 DN (Digital Numbers). It is added to allow recording of negative radiometric values without truncation."
  },
  {
    "difficulty": "Medium",
    "capability": "Fact Retrieval",
    "filtering_test": "mission_specific",
    "question": "Which Sentinel-2 bands are dedicated to atmospheric correction (Cirrus and Water Vapour)?",
    "ground_truth": "Band 9 (945 nm) is for Water Vapour, and Band 10 (1375 nm) is for Cirrus detection. Both have 60 m resolution."
  },

  # ===================================================================
  # 🌊 CATEGORY 5: SENTINEL-3 (MULTI-INSTRUMENT SYNERGY)
  # ===================================================================
  {
    "difficulty": "Medium",
    "capability": "Fact Retrieval",
    "filtering_test": "mission_specific",
    "question": "Which Sentinel-3 instrument is responsible for measuring sea and land surface temperatures, and what is its nadir spatial resolution?",
    "ground_truth": "The SLSTR (Sea and Land Surface Temperature Radiometer). Its thermal channels have a spatial resolution of 1 km at nadir."
  },
  {
    "difficulty": "Medium",
    "capability": "Fact Retrieval",
    "filtering_test": "mission_specific",
    "question": "How many spectral bands does the Sentinel-3 OLCI instrument have, and what is its spectral range?",
    "ground_truth": "OLCI has 21 spectral bands covering the spectral range from 400 nm to 1020 nm."
  },
  {
    "difficulty": "Hard",
    "capability": "Multi-hop Reasoning",
    "filtering_test": "intra_mission_comparison",
    "question": "Does the Sentinel-3 SLSTR instrument have a wider or narrower swath than the OLCI instrument?",
    "ground_truth": "The SLSTR Dual View swath (740 km) is narrower than OLCI (1270 km). However, the SLSTR Single View (Nadir) swath is 1400 km, which is wider than OLCI."
  },
  {
    "difficulty": "Hard",
    "capability": "Fact Retrieval",
    "filtering_test": "technical_nuance",
    "question": "What is the Sentinel-3 'Synergy' (SYN) product?",
    "ground_truth": "The SYN product combines information from both the OLCI and SLSTR instruments to provide improved surface reflectance and aerosol retrieval."
  },

  # ===================================================================
  # 🚀 CATEGORY 6: FUTURE & EXPANSION MISSIONS
  # ===================================================================
  {
    "difficulty": "Medium",
    "capability": "Fact Retrieval",
    "filtering_test": "expansion_mission",
    "question": "What is the spectral bandwidth and ground resolution of the CHIME mission?",
    "ground_truth": "CHIME has a spectral bandwidth of ≤10 nm and a ground resolution of 30 m."
  },
  {
    "difficulty": "Medium",
    "capability": "Fact Retrieval",
    "filtering_test": "expansion_mission",
    "question": "What is the unique operation mode of the Poseidon-4 altimeter on Sentinel-6?",
    "ground_truth": "Poseidon-4 uses an 'interleaved' mode (Open Burst), allowing it to simultaneously provide low-resolution mode (LRM) and SAR mode measurements."
  },
  
  # ===================================================================
  # ⚔️ CATEGORY 7: CROSS-MISSION & COMPLEX REASONING
  # ===================================================================
  {
    "difficulty": "Hard",
    "capability": "Multi-hop Reasoning",
    "filtering_test": "cross_mission_comparison",
    "question": "Compare the bandwidth of the water vapour absorption band in Sentinel-2 (Band 9) vs Sentinel-3 OLCI (Band 19). Which is narrower?",
    "ground_truth": "Sentinel-3 OLCI Band 19 (10 nm width) is narrower than Sentinel-2 Band 9 (20 nm width)."
  },
  {
    "difficulty": "Medium",
    "capability": "Fact Retrieval",
    "filtering_test": "cross_mission_comparison",
    "question": "What are the differences between Sentinel-1 and Sentinel-2 resolution capabilities?",
    "ground_truth": "Sentinel-1 (Radar) resolutions range from 5-40 m depending on mode. Sentinel-2 (Optical) has fixed resolutions of 10 m, 20 m, and 60 m depending on the band."
  },
  # ===================================================================
  # ⚔️ CATEGORY: HARD COMPARISONS (System's current weak spot)
  # ===================================================================
  {
    "difficulty": "Hard",
    "capability": "Multi-hop Reasoning",
    "filtering_test": "cross_mission_comparison",
    "question": "Which has a higher revisit frequency at the equator: the Sentinel-1 constellation or the Sentinel-2 constellation?",
    "ground_truth": "Sentinel-2 has a higher revisit frequency (5 days with 2 satellites) compared to Sentinel-1 (6 days with 2 satellites)."
  },
  {
    "difficulty": "Hard",
    "capability": "Multi-hop Reasoning",
    "filtering_test": "cross_mission_comparison",
    "question": "Compare the main instrument payload of Sentinel-5P versus Sentinel-4.",
    "ground_truth": "Sentinel-5P carries TROPOMI (UV-VIS-NIR-SWIR spectrometer). Sentinel-4 carries the UVN (Ultraviolet-Visible-Near-Infrared) Light spectrometer."
  },
  {
    "difficulty": "Hard",
    "capability": "Multi-hop Reasoning",
    "filtering_test": "cross_mission_comparison",
    "question": "Do Sentinel-1 and Sentinel-3 both use the same band for their altimetry measurements?",
    "ground_truth": "No. Sentinel-3 SRAL operates in Ku-band and C-band. Sentinel-1 is an imaging radar (SAR) operating in C-band, but it is not an altimeter."
  },
  {
    "difficulty": "Hard",
    "capability": "Multi-hop Reasoning",
    "filtering_test": "cross_mission_comparison",
    "question": "Which mission provides higher spatial resolution for vegetation monitoring: Sentinel-2 or Sentinel-3 OLCI?",
    "ground_truth": "Sentinel-2 provides higher resolution (10m/20m) compared to Sentinel-3 OLCI (300m)."
  },

  # ===================================================================
  # 🕵️ CATEGORY: METADATA & FILE FORMATS (Tests precision)
  # ===================================================================
  {
    "difficulty": "Medium",
    "capability": "Syntax Specificity",
    "filtering_test": "technical_nuance",
    "question": "What is the file extension used for the Sentinel-2 granule metadata file?",
    "ground_truth": "The granule metadata file uses the .xml extension (specifically MTD_TL.xml)."
  },
  {
    "difficulty": "Hard",
    "capability": "Syntax Specificity",
    "filtering_test": "naming_convention",
    "question": "In the Sentinel-1 filename convention, what does 'SLC' stand for?",
    "ground_truth": "SLC stands for Single Look Complex."
  },
  {
    "difficulty": "Hard",
    "capability": "Syntax Specificity",
    "filtering_test": "naming_convention",
    "question": "What is the maximum size (in GB) of a standard Sentinel-1 Interferometric Wide (IW) SLC product?",
    "ground_truth": "A standard Sentinel-1 IW SLC product is approximately 7-8 GB."
  },

  # ===================================================================
  # 🌍 CATEGORY: GEOGRAPHIC & ORBITAL (Tests context)
  # ===================================================================
  {
    "difficulty": "Medium",
    "capability": "Fact Retrieval",
    "filtering_test": "orbital_params",
    "question": "What is the mean local solar time at the descending node (LTDN) for Sentinel-2?",
    "ground_truth": "The LTDN for Sentinel-2 is 10:30 AM."
  },
  {
    "difficulty": "Medium",
    "capability": "Fact Retrieval",
    "filtering_test": "orbital_params",
    "question": "What is the orbital altitude of the Sentinel-6 Michael Freilich satellite?",
    "ground_truth": "Sentinel-6 orbits at an altitude of approximately 1336 km (non-sun-synchronous reference orbit)."
  },
  {
    "difficulty": "Medium",
    "capability": "Fact Retrieval",
    "filtering_test": "orbital_params",
    "question": "Does Sentinel-1 acquire data in ascending or descending passes?",
    "ground_truth": "Sentinel-1 acquires data in both ascending (south-to-north) and descending (north-to-south) passes."
  },

  # ===================================================================
  # 🛑 CATEGORY: SAFETY & HALLUCINATION (More traps)
  # ===================================================================
  {
    "difficulty": "Hard",
    "capability": "Negative Constraint",
    "filtering_test": "negative_test",
    "question": "What is the spatial resolution of the Sentinel-2 microwave radiometer?",
    "ground_truth": "Sentinel-2 does not carry a microwave radiometer. It carries only the Multi-Spectral Instrument (MSI)."
  },
  {
    "difficulty": "Hard",
    "capability": "Negative Constraint",
    "filtering_test": "negative_test",
    "question": "Can I use Sentinel-3 SLSTR data to measure cloud vertical structure?",
    "ground_truth": "No, SLSTR is a radiometer for surface temperature. Cloud vertical structure is typically measured by active instruments like the Cloud Profiling Radar (EarthCARE) or LIDAR, not SLSTR."
  },
  {
    "difficulty": "Hard",
    "capability": "Temporal Reasoning",
    "filtering_test": "status_check",
    "question": "Is the Envisat mission still providing data for Copernicus services?",
    "ground_truth": "No, the Envisat mission ended on April 8, 2012. Copernicus services now rely on the Sentinel missions."
  },
  
  # ===================================================================
  # 🧩 CATEGORY: DATA ACCESS (Practical usage)
  # ===================================================================
  {
    "difficulty": "Medium",
    "capability": "Fact Retrieval",
    "filtering_test": "practical_usage",
    "question": "Which API should I use to download Sentinel-1 data programmatically?",
    "ground_truth": "You should use the Copernicus Data Space Ecosystem (CDSE) OData or OpenSearch APIs."
  },
  {
    "difficulty": "Medium",
    "capability": "Fact Retrieval",
    "filtering_test": "practical_usage",
    "question": "What is the typical latency for Sentinel-3 Near Real Time (NRT) products?",
    "ground_truth": "Sentinel-3 NRT products are typically available within 3 hours of sensing."
  }
]


def format_context_for_llm(docs: List[Dict[str, Any]]) -> str:
    """Format retrieved documents as context for the LLM."""
    context_parts = []
    for i, doc in enumerate(docs, 1):
        title = doc.get("title", "Unknown")
        url = doc.get("url", "")
        text = doc.get("contextualized_text") or doc.get("text", "")
        
        context_parts.append(
            f"[Document {i}] {title}\n"
            f"Source: {url}\n"
            f"Content:\n{text}\n"
        )
    return "\n---\n\n".join(context_parts)

def create_rag_prompt(query: str, context: str, docs: List[Dict[str, Any]] = None) -> List[Dict[str, str]]:
    """Create a RAG prompt with query and context.
    
    Args:
        query: User question
        context: Formatted context from retrieved documents
        docs: List of retrieved documents (for detecting multiple standards)
    """
    # Import here to avoid circular dependencies
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from src.utils.prompts import build_rag_system_prompt, extract_standards_from_docs
    
    # Extract ECSS standards from documents
    standards_in_context = extract_standards_from_docs(docs) if docs else None
    
    # Build system prompt using centralized function
    system_prompt = build_rag_system_prompt(
        context=context,
        standards_in_context=standards_in_context,
    )
    
    user_prompt = f"""Context from documentation:

{context}

Question: {query}

Please provide a comprehensive answer based on the context above."""
    
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

def is_rate_limit_error(error: Exception) -> bool:
    """Check if error is a rate limit error."""
    error_str = str(error).lower()
    return (
        "rate_limit" in error_str
        or "rate limit" in error_str
        or "429" in error_str
        or "too many requests" in error_str
        or "maximum usage increase rate" in error_str
    )


def generate_rag_answer(
    query: str,
    retriever: AdvancedRetriever,
    llm,
    top_k: int = 10,
    use_hybrid: Optional[bool] = None,
    use_reranking: Optional[bool] = None,
    use_filtering: Optional[bool] = None,
    max_retries: int = 3,
    base_delay: float = 10.0,
) -> tuple[str, List[Dict[str, Any]], List[str]]:
    """Generate RAG answer with retry logic for rate limiting."""
    docs = retriever.retrieve(
        query=query,
        top_k=top_k,
        use_hybrid=use_hybrid,
        use_reranking=use_reranking,
        auto_extract_filters=use_filtering,  # None = use config default
    )
    
    contexts = [
        doc.get("contextualized_text") or doc.get("text", "")
        for doc in docs
    ]
    
    context_str = format_context_for_llm(docs)
    messages = create_rag_prompt(query, context_str, docs=docs)
    
    # Retry logic for rate limiting
    for attempt in range(max_retries):
        try:
            response = llm.invoke(messages)
            
            if hasattr(response, "content"):
                answer = response.content
            elif isinstance(response, str):
                answer = response
            elif isinstance(response, dict):
                answer = response.get("content", str(response))
            else:
                answer = str(response)
            
            return answer, docs, contexts
            
        except Exception as e:
            if is_rate_limit_error(e) and attempt < max_retries - 1:
                # Exponential backoff: 10s, 20s, 40s
                delay = base_delay * (2 ** attempt)
                logger.warning(
                    f"Rate limit error (attempt {attempt + 1}/{max_retries}): {e}\n"
                    f"Waiting {delay:.1f}s before retry..."
                )
                time.sleep(delay)
                continue
            else:
                # Re-raise if not rate limit or last attempt
                raise
    
    # Should never reach here, but just in case
    raise Exception("Failed to generate answer after retries")

@click.command()
@click.option("--top-k", "-k", type=int, default=10)
@click.option("--collection", type=str, default=None)
@click.option("--model", type=str, default=None)
@click.option("--api-key", type=str, default=None)
@click.option("--no-hybrid", is_flag=True, default=False)
@click.option("--no-reranking", is_flag=True, default=False)
@click.option("--no-filtering", is_flag=True, default=False, help="Disable metadata filtering")
@click.option("--output", "-o", type=str, default="results_evaluacion_ragas_hard.csv")
@click.option("--limit", type=int, default=None)
@click.option("--delay", type=float, default=10.0, help="Delay between requests in seconds (default: 10.0)")
@click.option("--max-retries", type=int, default=3, help="Max retries for rate limit errors (default: 3)")
def main(top_k, collection, model, api_key, no_hybrid, no_reranking, no_filtering, output, limit, delay, max_retries):
    """Evaluate RAG system using RAGAS metrics."""
    setup_logger()
    settings = get_settings()
    
    # Get API key - try eval_llm config first, then fallback to default
    eval_config = settings.llm.eval_llm
    if eval_config:
        eval_provider = eval_config.provider
        eval_model = eval_config.model
        # Get API key for eval provider
        if not api_key:
            api_key = os.getenv(f"{eval_provider.upper()}_API_KEY") or getattr(settings, f"{eval_provider}_api_key", None)
        llm_provider = eval_provider
        llm_model = model or eval_model
    else:
        # Fallback to default LLM config
        if not api_key:
            api_key = os.getenv("ANTHROPIC_API_KEY") or getattr(settings, "anthropic_api_key", None)
        llm_provider = "anthropic"
        llm_model = model or settings.llm.model
    
    if not api_key:
        logger.error("API key not found. Set ANTHROPIC_API_KEY environment variable or configure eval_llm in settings.yaml")
        sys.exit(1)
    
    logger.info("Initializing RAG components...")
    retriever = AdvancedRetriever(collection_name=collection)
    llm = get_llm(provider=llm_provider, model=llm_model, api_key=api_key, streaming=False)
    
    # Log retrieval configuration
    use_hybrid = False if no_hybrid else None
    use_reranking = False if no_reranking else None
    use_filtering = False if no_filtering else None
    
    # Determine actual values (None means use config defaults)
    actual_hybrid = use_hybrid if use_hybrid is not None else retriever.hybrid_search_enabled
    actual_reranking = use_reranking if use_reranking is not None else retriever.reranker_enabled
    actual_filtering = use_filtering if use_filtering is not None else retriever.metadata_filtering_enabled
    
    logger.info("=" * 80)
    logger.info("Retrieval Configuration:")
    logger.info(f"  Hybrid Search: {'ENABLED' if actual_hybrid else 'DISABLED'}")
    logger.info(f"  Reranking: {'ENABLED' if actual_reranking else 'DISABLED'}")
    logger.info(f"  Metadata Filtering: {'ENABLED' if actual_filtering else 'DISABLED'}")
    logger.info(f"  Top-K: {top_k}")
    logger.info("=" * 80)
    
    dataset = GOLDEN_DATASET
    if limit:
        dataset = dataset[:limit]
    
    questions, ground_truths, answers, contexts_list = [], [], [], []
    failed_questions = []
    
    logger.info(f"Processing {len(dataset)} questions with {delay}s delay between requests")
    logger.info(f"Rate limit retry: max {max_retries} attempts with exponential backoff")
    
    for i, item in enumerate(dataset, 1):
        question = item["question"]
        ground_truth = item["ground_truth"]
        
        logger.info(f"[{i}/{len(dataset)}] Processing: {question[:60]}...")
        
        try:
            answer, docs, contexts = generate_rag_answer(
                query=question,
                retriever=retriever,
                llm=llm,
                top_k=top_k,
                use_hybrid=not no_hybrid,  # Si no_hybrid=True → use_hybrid=False
                use_reranking=not no_reranking,  # Si no_reranking=True → use_reranking=False
                use_filtering=not no_filtering,  # Si no_filtering=True → use_filtering=False
                max_retries=max_retries,
                base_delay=delay,
            )
            
            questions.append(question)
            ground_truths.append(ground_truth)
            answers.append(answer)
            contexts_list.append(contexts)
            
            logger.success(f"✓ Answer generated ({len(contexts)} contexts)")
            
            # Sleep between requests to respect rate limits (except for last question)
            if i < len(dataset):
                logger.debug(f"Sleeping {delay}s to respect rate limits...")
                time.sleep(delay)
            
        except Exception as e:
            error_msg = str(e)
            if is_rate_limit_error(e):
                logger.error(
                    f"✗ Rate limit error after {max_retries} retries: {error_msg}\n"
                    f"  Consider increasing --delay or --max-retries"
                )
            else:
                logger.error(f"✗ Error: {error_msg}")
            
            failed_questions.append({"index": i, "question": question, "error": error_msg})
            continue
    
    # Report summary
    logger.info("=" * 80)
    logger.info(f"Processing complete: {len(questions)}/{len(dataset)} questions succeeded")
    if failed_questions:
        logger.warning(f"Failed questions: {len(failed_questions)}")
        for fq in failed_questions[:5]:  # Show first 5
            logger.warning(f"  Q{fq['index']}: {fq['question'][:50]}...")
        if len(failed_questions) > 5:
            logger.warning(f"  ... and {len(failed_questions) - 5} more")
    logger.info("=" * 80)
    
    if not questions:
        logger.error("No questions processed successfully. Exiting.")
        if failed_questions:
            logger.error("All questions failed. Check your API key and rate limits.")
        sys.exit(1)
    
    # Warn if many questions failed
    if len(failed_questions) > len(questions) * 0.3:  # More than 30% failed
        logger.warning(
            f"High failure rate: {len(failed_questions)}/{len(dataset)} questions failed.\n"
            f"Consider:\n"
            f"  - Increasing --delay (current: {delay}s)\n"
            f"  - Increasing --max-retries (current: {max_retries})\n"
            f"  - Checking your API rate limits"
        )
    
    # RAGAS EVALUATION SETUP
    eval_dict = {
        "question": questions,
        "answer": answers,
        "contexts": contexts_list,
        "ground_truth": ground_truths,
    }
    eval_dataset = Dataset.from_dict(eval_dict)
    
    try:
        # 1. SETUP LLM (JUDGE) for RAGAS metrics
        ragas_llm = None
        if LANGCHAIN_AVAILABLE and ChatAnthropic is not None:
            # Use eval_llm config if available, otherwise fall back to default or provided model
            eval_config = settings.llm.eval_llm
            if eval_config:
                eval_model = eval_config.model
                eval_provider = eval_config.provider
                eval_temperature = eval_config.temperature
                # Get API key for eval provider
                eval_api_key = api_key or os.getenv(f"{eval_provider.upper()}_API_KEY") or getattr(settings, f"{eval_provider}_api_key", None)
            else:
                # Fallback to provided model or default
                eval_model = model or settings.llm.model
                eval_provider = settings.llm.provider
                eval_temperature = 0.0  # Default for evaluation
                eval_api_key = api_key
            
            # Only proceed if we have an API key
            if eval_api_key:
                # Clean model name (remove provider prefix if present)
                if eval_model.startswith(f"{eval_provider}/"):
                    eval_model = eval_model.replace(f"{eval_provider}/", "")
                elif "/" in eval_model:
                    eval_model = eval_model.split("/")[-1]
                
                # Currently only support Anthropic for RAGAS LLM
                if eval_provider == "anthropic":
                    langchain_llm = ChatAnthropic(
                        model=eval_model,
                        api_key=eval_api_key,
                        temperature=eval_temperature,
                    )
                    ragas_llm = LangchainLLMWrapper(langchain_llm=langchain_llm)
                    logger.info(f"Using {eval_provider} LLM for RAGAS metrics: {eval_model}")
                else:
                    logger.warning(f"RAGAS LLM provider '{eval_provider}' not yet supported. Only 'anthropic' is supported.")
            else:
                logger.warning("No API key available for RAGAS LLM metrics. Only computing context_precision and context_recall")

        # 2. SETUP EMBEDDINGS (Use same model as retriever for accurate evaluation)
        # CRITICAL: Use the same embedding model as the retriever to ensure
        # semantic similarity scores match what the actual retrieval system uses
        if HuggingFaceEmbeddings is None:
            logger.error("langchain-huggingface not installed. Required for embeddings.")
            logger.error("Install with: uv add langchain-huggingface sentence-transformers")
            sys.exit(1)
        
        # Get embedding model from retriever (matches Qdrant collection)
        embedding_model = retriever.embed_model_name
        logger.info(f"Loading embeddings for RAGAS metrics (using retriever's model: {embedding_model})...")
        try:
            hf_embeddings = HuggingFaceEmbeddings(model_name=embedding_model)
            ragas_embeddings = LangchainEmbeddingsWrapper(embeddings=hf_embeddings)
            logger.success(f"✓ Embeddings loaded: {embedding_model}")
        except Exception as e:
            logger.error(f"Failed to load embeddings: {e}")
            logger.error("This may be due to missing sentence-transformers or network issues")
            sys.exit(1)

        # 3. CONFIGURE METRICS
        # In newer RAGAS versions, LLM and embeddings are passed to evaluate()
        # instead of using with_llm() method
        metrics_to_use = [
            context_precision, 
            context_recall,
        ]
        
        # Add LLM-based metrics if LLM is available
        if ragas_llm:
            metrics_to_use.extend([
                faithfulness,
                answer_relevancy,
            ])
            logger.info("Using all 4 metrics (including LLM-based: faithfulness, answer_relevancy)")
        else:
            logger.warning("LLM not available. Only computing context_precision and context_recall")
        
        logger.info("Running RAGAS evaluation (Sequential mode)...")
        logger.info("Note: Some OutputParserException warnings may appear - these are non-critical.")
        logger.info("RAGAS will continue evaluation and mark failed metrics as NaN.")
        
        # Suppress RAGAS parser warnings - these are expected when LLM returns slightly different JSON formats
        import warnings
        warnings.filterwarnings("ignore", category=UserWarning, module="ragas")
        
        run_config = RunConfig(max_workers=1, timeout=300)
        
        # Pass LLM and embeddings to evaluate() - RAGAS will use them for metrics that need them
        # Note: raise_exceptions=False allows evaluation to continue even if some metrics fail
        result = evaluate(
            eval_dataset,
            metrics=metrics_to_use,
            llm=ragas_llm,              # Pass LLM for faithfulness and answer_relevancy
            embeddings=ragas_embeddings, # Pass embeddings for all metrics
            run_config=run_config,
            raise_exceptions=False  # Continue evaluation even if individual metrics fail
        )
        
        print("\n" + str(result) + "\n")
        df = result.to_pandas()
        
        # Check for NaN values (which indicate failed metric evaluations)
        nan_counts = df[['context_precision', 'context_recall', 'faithfulness', 'answer_relevancy']].isna().sum()
        if nan_counts.any():
            logger.warning("Some metrics failed to evaluate (NaN values found):")
            for metric, count in nan_counts.items():
                if count > 0:
                    logger.warning(f"  - {metric}: {count} failed evaluations")
            logger.info("This is usually due to LLM returning non-standard JSON format.")
            logger.info("The evaluation continues with available metrics.")
        
        df.to_csv(output, index=False)
        logger.success(f"✓ Saved to {output}")
        
    except Exception as e:
        error_msg = str(e)
        if "OutputParserException" in error_msg or "Invalid json output" in error_msg:
            logger.warning("RAGAS encountered JSON parsing errors (non-critical):")
            logger.warning("These occur when the LLM returns slightly different JSON formats.")
            logger.warning("The evaluation should continue, but some metrics may be NaN.")
            logger.info("Consider using a more structured LLM or adjusting the RAGAS LLM configuration.")
        else:
            logger.error(f"RAGAS Error: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            sys.exit(1)

if __name__ == "__main__":
    main()