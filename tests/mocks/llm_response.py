"""
Mock LLM responses for testing optimize_ai functionality.
"""

MOCK_RESPONSES = {
    'compression': {
        'vscode': {
            'success': {
                'compressed_content': '''def calc(nums):
    return sum(nums)''',
                'compression_ratio': 0.65,
                'metadata': {
                    'technique': 'waterfall',
                    'original_size': 120,
                    'compressed_size': 78,
                    'stats': {
                        'variables_renamed': 2,
                        'whitespace_removed': 45,
                        'comments_removed': 1
                    }
                }
            },
            'failure': {
                'compressed_content': None,
                'compression_ratio': 1.0,
                'error': 'Compression failed: Syntax error detected',
                'metadata': {}
            }
        },
        'cursor': {
            'success': {
                'compressed_content': '''async def proc(data):
    return [x*2 for x in data if x>0]''',
                'compression_ratio': 0.58,
                'metadata': {
                    'technique': 'aggressive',
                    'original_size': 245,
                    'compressed_size': 142
                }
            }
        },
        'claude': {
            'success': {
                'compressed_content': '''class H:
    def __init__(s,v):s.v=v
    def get(s):return s.v''',
                'compression_ratio': 0.42,
                'metadata': {
                    'technique': 'extreme',
                    'original_size': 180,
                    'compressed_size': 76
                }
            }
        }
    },
    
    'translation': {
        'vscode': {
            'success': {
                'translated_content': '''def calculate_numbers(number_list):
    """Calculate sum of numbers in the list."""
    total = 0
    for number in number_list:
        total += number
    return total''',
                'confidence': 0.92,
                'metadata': {
                    'translator': 'pattern_based',
                    'improvements': [
                        'Expanded variable names',
                        'Added docstring',
                        'Improved readability'
                    ]
                }
            },
            'failure': {
                'translated_content': None,
                'confidence': 0.0,
                'error': 'Translation failed: Unrecognized pattern',
                'metadata': {}
            }
        },
        'cursor': {
            'success': {
                'translated_content': '''async def process_data(data_list):
    """Process data asynchronously and return filtered results."""
    processed_results = []
    for item in data_list:
        if item > 0:
            processed_value = item * 2
            processed_results.append(processed_value)
    return processed_results''',
                'confidence': 0.88,
                'metadata': {
                    'translator': 'ai_enhanced',
                    'async_detected': True
                }
            }
        },
        'claude': {
            'success': {
                'translated_content': '''class Handler:
    """A handler class for managing values."""
    
    def __init__(self, initial_value):
        """Initialize handler with a value."""
        self.value = initial_value
    
    def get_value(self):
        """Return the current value."""
        return self.value''',
                'confidence': 0.95,
                'metadata': {
                    'translator': 'advanced_pattern',
                    'class_methods_expanded': 2
                }
            }
        }
    },
    
    'session_responses': {
        'create_success': {
            'session_id': 'test-session-12345',
            'status': 'created',
            'agent': 'vscode',
            'file_path': '/test/sample.py'
        },
        'retrieve_success': {
            'session_id': 'test-session-12345',
            'compressed_content': 'def f():pass',
            'metadata': {'created_at': '2025-08-03T10:00:00Z'},
            'agent': 'vscode'
        },
        'not_found': {
            'session_id': None,
            'error': 'Session not found',
            'status': 'error'
        }
    },
    
    'integration_responses': {
        'vscode_file_open': {
            'status': 'success',
            'event': 'file_opened',
            'file_path': '/workspace/test.py',
            'timestamp': '2025-08-03T10:00:00Z'
        },
        'cursor_file_change': {
            'status': 'updated',
            'event': 'file_modified',
            'file_path': '/workspace/test.py',
            'changes': {
                'lines_added': 5,
                'lines_removed': 2
            }
        },
        'claude_command': {
            'status': 'intercepted',
            'command': ['claude-code', 'edit', 'test.py'],
            'action': 'redirect_to_optimize'
        }
    },
    
    'error_responses': {
        'timeout': {
            'error': 'Request timed out',
            'code': 'TIMEOUT',
            'retryable': True
        },
        'invalid_syntax': {
            'error': 'Invalid Python syntax',
            'code': 'SYNTAX_ERROR',
            'retryable': False,
            'details': 'Line 5: Missing closing parenthesis'
        },
        'file_not_found': {
            'error': 'File not found',
            'code': 'FILE_NOT_FOUND',
            'retryable': False,
            'file_path': '/nonexistent/file.py'
        },
        'compression_limit': {
            'error': 'Content too large for compression',
            'code': 'SIZE_LIMIT_EXCEEDED',
            'retryable': False,
            'max_size': 1000000,
            'actual_size': 1500000
        }
    },
    
    'benchmark_responses': {
        'small_file': {
            'compression_time': 0.05,
            'translation_time': 0.08,
            'total_time': 0.13,
            'compression_ratio': 0.7,
            'translation_confidence': 0.9
        },
        'large_file': {
            'compression_time': 0.5,
            'translation_time': 0.8,
            'total_time': 1.3,
            'compression_ratio': 0.6,
            'translation_confidence': 0.85
        },
        'complex_file': {
            'compression_time': 0.15,
            'translation_time': 0.25,
            'total_time': 0.4,
            'compression_ratio': 0.55,
            'translation_confidence': 0.92
        }
    }
}

# Helper functions for accessing mock responses
def get_compression_response(agent: str, success: bool = True):
    """Get mock compression response for specific agent."""
    responses = MOCK_RESPONSES['compression'].get(agent, {})
    key = 'success' if success else 'failure'
    return responses.get(key, {})

def get_translation_response(agent: str, success: bool = True):
    """Get mock translation response for specific agent."""
    responses = MOCK_RESPONSES['translation'].get(agent, {})
    key = 'success' if success else 'failure'
    return responses.get(key, {})

def get_integration_response(event_type: str):
    """Get mock integration response for specific event."""
    return MOCK_RESPONSES['integration_responses'].get(event_type, {})

def get_error_response(error_type: str):
    """Get mock error response for specific error type."""
    return MOCK_RESPONSES['error_responses'].get(error_type, {})

def get_benchmark_response(file_type: str):
    """Get mock benchmark response for specific file type."""
    return MOCK_RESPONSES['benchmark_responses'].get(file_type, {})
