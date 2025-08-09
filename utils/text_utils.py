from .compression import CompressionType
from typing import Dict, Tuple, Union

# Waterfall tier thresholds - making values constant for maintainability
# These can be easily adjusted without changing the core logic
# Adjusted to align with new aggressive token thresholds (chars ≈ tokens * 4)
BASIC_THRESHOLD = 250    # ~250 chars ≈ 62 tokens (SMALL tier boundary)
STANDARD_THRESHOLD = 1000   # ~1000 chars ≈ 250 tokens (MEDIUM tier boundary)  
AGGRESSIVE_THRESHOLD = 4000  # ~4000 chars ≈ 1000 tokens (LARGE tier boundary)


def select_waterfall_tier(input_length: int) -> CompressionType:
    """
    Select compression tier based on input length using waterfall logic.
    
    This function provides a waterfall approach to compression tier selection
    with different thresholds optimized for waterfall processing.
    
    Args:
        input_length: Length of the input content in characters
        
    Returns:
        CompressionType: The appropriate compression tier
        
    Thresholds:
        - <= 250 chars: BASIC compression
        - <= 1000 chars: STANDARD compression
        - <= 4000 chars: AGGRESSIVE compression  
        - > 4000 chars: SUMMARIZE compression
    """
    if input_length <= BASIC_THRESHOLD:
        return CompressionType.BASIC
    elif input_length <= STANDARD_THRESHOLD:
        return CompressionType.STANDARD
    elif input_length <= AGGRESSIVE_THRESHOLD:
        return CompressionType.AGGRESSIVE
    else:
        return CompressionType.SUMMARIZE


def select_tier_from_enum_thresholds(input_length: int) -> CompressionType:
    """
    Alternative approach: Use the existing enum's built-in thresholds.
    
    This leverages the CompressionType.from_length() method which uses
    the enum's min_len and max_len values for threshold determination.
    """
    return CompressionType.from_length(input_length)


def get_waterfall_thresholds() -> Dict[str, Union[int, float]]:
    """Get the waterfall tier thresholds for documentation/debugging."""
    return {
        'BASIC': BASIC_THRESHOLD,
        'STANDARD': STANDARD_THRESHOLD,
        'AGGRESSIVE': AGGRESSIVE_THRESHOLD,
        'SUMMARIZE': float('inf')
    }


def get_enum_thresholds() -> Dict[str, Tuple[int, float]]:
    """Get the enum's built-in thresholds for comparison."""
    return {ct.name: (ct.min_len, ct.max_len) for ct in CompressionType}


# Test samples
def run_waterfall_tests():
    """Run test cases for the waterfall tier selection."""
    test_cases = [
        (100, CompressionType.BASIC),
        (500, CompressionType.STANDARD),
        (2000, CompressionType.AGGRESSIVE),
        (5000, CompressionType.SUMMARIZE),
        (250, CompressionType.BASIC),  # boundary
        (1000, CompressionType.STANDARD),  # boundary
        (4000, CompressionType.AGGRESSIVE),  # boundary
    ]

    print("Waterfall Tier Selection Tests:")
    print("=" * 50)
    for length, expected in test_cases:
        result = select_waterfall_tier(length)
        enum_result = select_tier_from_enum_thresholds(length)
        status = '✓' if result == expected else '✗'
        print(f"{length:>6} chars → Waterfall: {result.name:<10} | Enum: {enum_result.name:<10} {status}")
    
    print("\nWaterfall Threshold Configuration:")
    print("=" * 50)
    waterfall_thresholds = get_waterfall_thresholds()
    for tier, threshold in waterfall_thresholds.items():
        print(f"{tier:<10}: <= {threshold} chars")
    
    print("\nEnum Threshold Configuration:")
    print("=" * 50)
    enum_thresholds = get_enum_thresholds()
    for tier, (min_len, max_len) in enum_thresholds.items():
        max_display = int(max_len) if max_len != float('inf') else 'inf'
        print(f"{tier:<10}: {min_len:>4} - {max_display} chars")


if __name__ == "__main__":
    run_waterfall_tests()
