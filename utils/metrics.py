"""Utility functions for token counting and metrics"""

def count_tokens(text: str, model: str = "gpt-4") -> int:
    """Count tokens in text using simple word-based approximation
    
    Args:
        text: The text to count tokens for
        model: The model to use for token counting (accepted for compatibility)
        
    Returns:
        Approximate token count
    """
    if not text:
        return 0
    
    # Validate model parameter for test compatibility
    valid_models = ["gpt-4", "gpt-3.5-turbo", "cl100k_base"]
    if model not in valid_models:
        raise ValueError(f"Invalid model: {model}")
    
    # Simple approximation: 1 token per 4 characters on average
    # This is a rough approximation commonly used for English text
    return max(1, len(text) // 4)
