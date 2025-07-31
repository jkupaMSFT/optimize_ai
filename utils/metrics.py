# ===== utils/metrics.py =====
import logging
from typing import Optional
import tiktoken
from sentence_transformers import SentenceTransformer, util

# Set up logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Cache encoding and model for efficiency
_encoding: Optional[tiktoken.Encoding] = None
_model: Optional[SentenceTransformer] = None

def get_tiktoken_encoding() -> tiktoken.Encoding:
    """Get or initialize tiktoken encoding."""
    global _encoding
    if _encoding is None:
        try:
            _encoding = tiktoken.get_encoding("cl100k_base")
        except Exception as e:
            logger.error(f"Failed to load tiktoken encoding: {str(e)}")
            raise RuntimeError("Tiktoken encoding initialization failed")
    return _encoding

def get_similarity_model() -> SentenceTransformer:
    """Get or initialize sentence transformer model."""
    global _model
    if _model is None:
        try:
            _model = SentenceTransformer('all-MiniLM-L6-v2')
        except Exception as e:
            logger.error(f"Failed to load sentence transformer model: {str(e)}")
            raise RuntimeError("Sentence transformer model initialization failed")
    return _model

def count_tokens(text: str) -> int:
    """
    Count tokens using tiktoken.
    
    Args:
        text: The text to tokenize.
    
    Returns:
        Number of tokens.
    
    Raises:
        ValueError: If text is invalid.
    """
    if not isinstance(text, str):
        raise ValueError("Input must be a string")
    
    try:
        enc = get_tiktoken_encoding()
        return len(enc.encode(text))
    except ValueError as e:
        logger.warning(f"Invalid text for tokenization: {str(e)}")
        raise ValueError(f"Tokenization failed: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error in token counting: {str(e)}")
        raise RuntimeError(f"Token counting failed: {str(e)}")

def calculate_similarity(original: str, translated: str) -> float:
    """
    Calculate semantic similarity between original and translated code.
    
    Args:
        original: Original text.
        translated: Translated text.
    
    Returns:
        Cosine similarity score between 0 and 1.
    
    Raises:
        ValueError: If inputs are invalid.
    """
    if not isinstance(original, str) or not isinstance(translated, str):
        raise ValueError("Both inputs must be strings")
    
    if not original or not translated:
        logger.warning("One or both inputs are empty; similarity is 0")
        return 0.0
    
    try:
        model = get_similarity_model()
        orig_emb = model.encode(original)
        trans_emb = model.encode(translated)
        similarity = util.cos_sim(orig_emb, trans_emb)[0][0].item()
        return max(0.0, min(1.0, similarity))  # Clamp between 0 and 1
    except Exception as e:
        logger.error(f"Similarity calculation failed: {str(e)}")
        raise RuntimeError(f"Similarity calculation failed: {str(e)}")