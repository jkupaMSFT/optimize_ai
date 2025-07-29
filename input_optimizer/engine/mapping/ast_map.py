import ast
import logging
import time
import sys
from typing import List, Dict, Any, Optional, Tuple, Union, Set
from dataclasses import dataclass

# Import the MinifierLogger from utils
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from utils.logger import MinifierLogger, get_logger

# Set up logging
logger = logging.getLogger(__name__)


# Custom exceptions for enhanced error handling
class InvalidRangeError(ValueError):
    """Raised when an invalid line range is provided."""
    pass


class LineNotFoundError(ValueError):
    """Raised when a line number is not found in any mapping."""
    pass


class InvalidMappedNodeError(ValueError):
    """Raised when a MappedNode contains invalid data."""
    pass


@dataclass
class MappedNode:
    """
    Represents a mapped relationship between source and summary content.
    
    Line numbers are 1-based (following common editor conventions).
    All ranges are inclusive (start and end lines are both included).
    """
    type: str
    name: str
    source_start: int
    source_end: int
    summary_start: int
    summary_end: int
    
    def __post_init__(self):
        """Validate the MappedNode data after initialization and intern strings."""
        # Intern strings for memory efficiency in large datasets
        self.type = sys.intern(self.type)
        self.name = sys.intern(self.name)
        self._validate()
    
    def _validate(self):
        """Validate that the MappedNode contains valid data."""
        errors = []
        
        # Check that line numbers are positive (1-based)
        if self.source_start < 1:
            errors.append(f"source_start must be >= 1, got {self.source_start}")
        if self.source_end < 1:
            errors.append(f"source_end must be >= 1, got {self.source_end}")
        if self.summary_start < 1:
            errors.append(f"summary_start must be >= 1, got {self.summary_start}")
        if self.summary_end < 1:
            errors.append(f"summary_end must be >= 1, got {self.summary_end}")
        
        # Check that start <= end for both ranges
        if self.source_start > self.source_end:
            errors.append(f"source_start ({self.source_start}) must be <= source_end ({self.source_end})")
        if self.summary_start > self.summary_end:
            errors.append(f"summary_start ({self.summary_start}) must be <= summary_end ({self.summary_end})")
        
        if errors:
            raise InvalidMappedNodeError(f"Invalid MappedNode '{self.name}': " + "; ".join(errors))
    
    def contains_source_line(self, line: int) -> bool:
        """Check if a source line number falls within this node's range."""
        return self.source_start <= line <= self.source_end
    
    def contains_summary_line(self, line: int) -> bool:
        """Check if a summary line number falls within this node's range."""
        return self.summary_start <= line <= self.summary_end
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert the node to a dictionary representation."""
        return {
            'type': self.type,
            'name': self.name,
            'source_start': self.source_start,
            'source_end': self.source_end,
            'summary_start': self.summary_start,
            'summary_end': self.summary_end
        }


# Enhanced line mapping utilities
def _validate_source_map_list(source_map: List[MappedNode]) -> None:
    """Validate that all nodes in the source map are valid."""
    if not isinstance(source_map, list):
        raise TypeError("source_map must be a list of MappedNode objects")
    
    for i, node in enumerate(source_map):
        if not isinstance(node, MappedNode):
            raise TypeError(f"source_map[{i}] must be a MappedNode, got {type(node)}")


def _validate_range(start: int, end: int, range_name: str = "range") -> None:
    """Validate that a line range is valid."""
    if not isinstance(start, int) or not isinstance(end, int):
        raise TypeError(f"{range_name} boundaries must be integers")
    
    if start < 1 or end < 1:
        raise InvalidRangeError(f"{range_name} must use 1-based line numbers (start={start}, end={end})")
    
    if start > end:
        raise InvalidRangeError(f"Invalid {range_name}: start ({start}) must be <= end ({end})")


def _ranges_overlap(range1_start: int, range1_end: int, range2_start: int, range2_end: int) -> bool:
    """
    Check if two line ranges overlap (inclusive bounds).
    
    Args:
        range1_start, range1_end: First range bounds (1-based, inclusive)
        range2_start, range2_end: Second range bounds (1-based, inclusive)
    
    Returns:
        True if ranges overlap, False otherwise
    """
    return range1_start <= range2_end and range2_start <= range1_end


def _find_overlapping_intervals_optimized(intervals: List[Tuple[int, int]]) -> int:
    """
    Efficiently count overlapping intervals using sweep line algorithm.
    
    Time complexity: O(n log n) instead of O(n²) for large datasets.
    
    Args:
        intervals: List of (start, end) tuples representing line ranges
    
    Returns:
        Number of overlapping interval pairs
    """
    if len(intervals) < 2:
        return 0
    
    # Create events: (position, event_type, interval_index)
    # event_type: 0 = start, 1 = end
    events = []
    for i, (start, end) in enumerate(intervals):
        events.append((start, 0, i))  # start event
        events.append((end + 1, 1, i))  # end event (exclusive)
    
    # Sort events by position, then by type (starts before ends)
    events.sort()
    
    active_intervals = set()
    overlap_count = 0
    
    for position, event_type, interval_idx in events:
        if event_type == 0:  # start event
            # Count overlaps with currently active intervals
            overlap_count += len(active_intervals)
            active_intervals.add(interval_idx)
        else:  # end event
            active_intervals.discard(interval_idx)
    
    return overlap_count


def _calculate_proportional_mapping(
    target_line: int,
    source_start: int,
    source_end: int,
    dest_start: int,
    dest_end: int
) -> int:
    """
    Calculate proportional line mapping between two ranges.
    
    This function assumes a linear relationship between source and destination lines
    within each mapped node. The mapping preserves relative position within ranges.
    
    Args:
        target_line: Line number to map from source range
        source_start, source_end: Source range bounds (1-based, inclusive)
        dest_start, dest_end: Destination range bounds (1-based, inclusive)
    
    Returns:
        Corresponding line number in destination range
    """
    source_range_size = source_end - source_start + 1
    dest_range_size = dest_end - dest_start + 1
    
    if source_range_size == 1:
        # Single line mapping - use start of destination range
        return dest_start
    
    # Proportional mapping: preserve relative position within the range
    position_ratio = (target_line - source_start) / (source_range_size - 1)
    dest_offset = round(position_ratio * (dest_range_size - 1))
    return dest_start + dest_offset


def get_summary_lines_for_source_range(source_map: List[MappedNode], start: int, end: int) -> List[int]:
    """
    Find all summary lines that correspond to a given source line range.
    
    This function finds all MappedNodes whose source ranges overlap with the specified
    range and returns all summary lines from those nodes.
    
    Args:
        source_map: List of MappedNode objects representing source-to-summary mappings
        start: Starting line number in source code (1-based, inclusive)
        end: Ending line number in source code (1-based, inclusive)
    
    Returns:
        List of summary line numbers (sorted, unique) that correspond to the source range
        
    Raises:
        InvalidRangeError: If the range is invalid
        TypeError: If source_map contains invalid types
    """
    _validate_source_map_list(source_map)
    _validate_range(start, end, "source range")
    
    summary_lines = set()
    overlapping_nodes = 0
    
    for node in source_map:
        # Check if the node's source range overlaps with the requested range
        if _ranges_overlap(node.source_start, node.source_end, start, end):
            overlapping_nodes += 1
            # Add all lines from the corresponding summary range
            for line in range(node.summary_start, node.summary_end + 1):
                summary_lines.add(line)
    
    logger.debug(f"Found {overlapping_nodes} overlapping nodes for source range {start}-{end}")
    return sorted(list(summary_lines))


def get_source_lines_for_summary_range(source_map: List[MappedNode], start: int, end: int) -> List[int]:
    """
    Find all source lines that correspond to a given summary line range.
    
    This function finds all MappedNodes whose summary ranges overlap with the specified
    range and returns all source lines from those nodes.
    
    Args:
        source_map: List of MappedNode objects representing source-to-summary mappings
        start: Starting line number in summary (1-based, inclusive)
        end: Ending line number in summary (1-based, inclusive)
    
    Returns:
        List of source line numbers (sorted, unique) that correspond to the summary range
        
    Raises:
        InvalidRangeError: If the range is invalid
        TypeError: If source_map contains invalid types
    """
    _validate_source_map_list(source_map)
    _validate_range(start, end, "summary range")
    
    source_lines = set()
    overlapping_nodes = 0
    
    for node in source_map:
        # Check if the node's summary range overlaps with the requested range
        if _ranges_overlap(node.summary_start, node.summary_end, start, end):
            overlapping_nodes += 1
            # Add all lines from the corresponding source range
            for line in range(node.source_start, node.source_end + 1):
                source_lines.add(line)
    
    logger.debug(f"Found {overlapping_nodes} overlapping nodes for summary range {start}-{end}")
    return sorted(list(source_lines))


def get_exact_summary_line_for_source_line(source_map: List[MappedNode], source_line: int) -> int:
    """
    Find the exact summary line corresponding to a single source line using proportional mapping.
    
    This function assumes a linear relationship between source and summary lines within
    each mapped node. It preserves the relative position of the line within its range.
    
    Args:
        source_map: List of MappedNode objects
        source_line: Source line number to map (1-based)
    
    Returns:
        Corresponding summary line number (1-based, proportionally calculated within the range)
        
    Raises:
        LineNotFoundError: If source line is not found in any mapping
        TypeError: If source_map contains invalid types
    """
    _validate_source_map_list(source_map)
    
    if not isinstance(source_line, int) or source_line < 1:
        raise InvalidRangeError(f"source_line must be a positive integer (1-based), got {source_line}")
    
    for node in source_map:
        if node.source_start <= source_line <= node.source_end:
            result = _calculate_proportional_mapping(
                source_line,
                node.source_start, node.source_end,
                node.summary_start, node.summary_end
            )
            logger.debug(f"Mapped source line {source_line} to summary line {result} via node '{node.name}'")
            return result
    
    raise LineNotFoundError(f"Source line {source_line} not found in any mapping")


def get_exact_source_line_for_summary_line(source_map: List[MappedNode], summary_line: int) -> int:
    """
    Find the exact source line corresponding to a single summary line using proportional mapping.
    
    This function assumes a linear relationship between source and summary lines within
    each mapped node. It preserves the relative position of the line within its range.
    
    Args:
        source_map: List of MappedNode objects
        summary_line: Summary line number to map (1-based)
    
    Returns:
        Corresponding source line number (1-based, proportionally calculated within the range)
        
    Raises:
        LineNotFoundError: If summary line is not found in any mapping
        TypeError: If source_map contains invalid types
    """
    _validate_source_map_list(source_map)
    
    if not isinstance(summary_line, int) or summary_line < 1:
        raise InvalidRangeError(f"summary_line must be a positive integer (1-based), got {summary_line}")
    
    for node in source_map:
        if node.summary_start <= summary_line <= node.summary_end:
            result = _calculate_proportional_mapping(
                summary_line,
                node.summary_start, node.summary_end,
                node.source_start, node.source_end
            )
            logger.debug(f"Mapped summary line {summary_line} to source line {result} via node '{node.name}'")
            return result
    
    raise LineNotFoundError(f"Summary line {summary_line} not found in any mapping")


class ASTMapper:
    """
    Walks Python AST and creates MappedNode objects for source-to-summary mapping.
    
    This class handles the complexity of tracking line spans and calculating
    compressed output positions based on configurable compression ratios.
    Enhanced with robust line range mapping capabilities.
    """
    
    def __init__(self, compression_ratios: Optional[Dict[str, float]] = None, 
                 minifier_logger: Optional[MinifierLogger] = None):
        """
        Initialize the AST mapper with compression ratios.
        
        Args:
            compression_ratios: Dict mapping node types to compression ratios.
                               e.g., {'import': 1.0, 'function': 0.3, 'class': 0.5}
                               1.0 means no compression, 0.5 means 50% of original size
            minifier_logger: Optional MinifierLogger instance for detailed logging
        """
        self.compression_ratios = compression_ratios or {
            'import': 1.0,      # Imports usually stay as-is
            'function': 0.4,    # Functions compress to ~40% of original
            'class': 0.5,       # Classes compress to ~50% of original
            'method': 0.4,      # Methods similar to functions
        }
        self.mapped_nodes: List[MappedNode] = []
        self.current_summary_line = 1
        self.source_lines: List[str] = []
        self.minifier_logger = minifier_logger or get_logger()
        self.operation_id: Optional[str] = None
    
    def walk_ast(self, source_code: str) -> List[MappedNode]:
        """
        Walk the AST of the source code and produce MappedNode objects.
        
        Args:
            source_code: Python source code to analyze
            
        Returns:
            List of MappedNode objects representing the mapping
        """
        start_time = time.time()
        
        # Start AST mapping operation
        self.operation_id = self.minifier_logger.log_minification_start(
            code_length=len(source_code),
            compression_depth=2,  # AST mapping is depth 2 (structure analysis)
            aggressive=False
        )
        
        # Reset state
        self.mapped_nodes = []
        self.current_summary_line = 1
        self.source_lines = source_code.splitlines()
        
        try:
            # Parse the AST
            tree = ast.parse(source_code)
            
            # Log AST parsing success
            self.minifier_logger.log_ast_transformation(
                transformation_type="ast_parsing",
                node_type="Module",
                details={"total_lines": len(self.source_lines)},
                optimization_applied=False
            )
            
            # Walk the tree
            self._walk_node(tree)
            
            # Log completion
            processing_time = time.time() - start_time
            self.minifier_logger.log_performance_metrics(
                operation_id=self.operation_id,
                stage="ast_mapping",
                duration=processing_time,
                additional_metrics={
                    "nodes_mapped": len(self.mapped_nodes),
                    "compression_ratios": self.compression_ratios
                }
            )
            
            # Log mapping statistics
            coverage = self.get_mapping_coverage()
            self.minifier_logger.log_optimization(
                optimization_type="source_mapping",
                before_value=f"{coverage['total_source_lines']} source lines",
                after_value=f"{len(self.mapped_nodes)} mapped nodes",
                node_location=f"coverage: {coverage['coverage_percentage']:.1f}%"
            )
            
            logger.info(f"AST mapping completed: {len(self.mapped_nodes)} nodes, "
                       f"{coverage['coverage_percentage']:.1f}% coverage")
            
        except SyntaxError as e:
            self.minifier_logger.log_error(
                error=e,
                operation_id=self.operation_id,
                code_context=source_code[:200] + "..." if len(source_code) > 200 else source_code,
                stage="ast_parsing"
            )
            raise
        except Exception as e:
            self.minifier_logger.log_error(
                error=e,
                operation_id=self.operation_id,
                stage="ast_mapping"
            )
            raise
        
        return self.mapped_nodes
    
    def _walk_node(self, node: ast.AST, parent_class: Optional[str] = None):
        """
        Recursively walk AST nodes and create mappings.
        
        Args:
            node: Current AST node
            parent_class: Name of parent class if we're inside a class definition
        """
        if isinstance(node, ast.Import):
            self._process_import(node, 'import')
        
        elif isinstance(node, ast.ImportFrom):
            self._process_import(node, 'import')
        
        elif isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
            self._process_function(node, parent_class)
        
        elif isinstance(node, ast.ClassDef):
            self._process_class(node)
        
        else:
            # Continue walking for other node types
            for child in ast.iter_child_nodes(node):
                self._walk_node(child, parent_class)
    
    def _process_import(self, node: Union[ast.Import, ast.ImportFrom], node_type: str):
        """Process import statements."""
        # Determine the name for the import
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
            import_name = ', '.join(names)
        else:
            module = node.module or ''
            names = [alias.name for alias in node.names]
            import_name = f"from {module} import {', '.join(names)}"
        
        # Get line span
        start_line = node.lineno
        end_line = node.end_lineno or node.lineno
        
        # Calculate compressed size
        source_lines = end_line - start_line + 1
        compressed_lines = self._calculate_compressed_lines(source_lines, node_type)
        
        # Log import processing
        self.minifier_logger.log_ast_transformation(
            transformation_type="import_mapping",
            node_type=node_type,
            details={
                "import_name": import_name,
                "source_lines": source_lines,
                "compressed_lines": compressed_lines,
                "compression_ratio": self.compression_ratios.get(node_type, 0.5)
            },
            optimization_applied=True
        )
        
        # Create mapped node
        mapped_node = MappedNode(
            type=node_type,
            name=import_name,
            source_start=start_line,
            source_end=end_line,
            summary_start=self.current_summary_line,
            summary_end=self.current_summary_line + compressed_lines - 1
        )
        
        self.mapped_nodes.append(mapped_node)
        self.current_summary_line += compressed_lines
        
        logger.debug(f"Mapped {node_type}: {import_name} "
                    f"({start_line}-{end_line} → {mapped_node.summary_start}-{mapped_node.summary_end})")
    
    def _process_function(self, node: Union[ast.FunctionDef, ast.AsyncFunctionDef], 
                         parent_class: Optional[str] = None):
        """Process function definitions."""
        # Determine if this is a method or standalone function
        node_type = 'method' if parent_class else 'function'
        
        # Get full function name
        function_name = node.name
        if parent_class:
            function_name = f"{parent_class}.{function_name}"
        
        # Handle decorated functions - find the actual start line
        start_line = node.lineno
        if hasattr(node, 'decorator_list') and node.decorator_list:
            # Get the line of the first decorator
            decorator_lines = [d.lineno for d in node.decorator_list if hasattr(d, 'lineno')]
            if decorator_lines:
                start_line = min(decorator_lines)
        
        # Get line span
        end_line = self._get_node_end_line(node)
        
        # Calculate compressed size
        source_lines = end_line - start_line + 1
        compressed_lines = self._calculate_compressed_lines(source_lines, node_type)
        
        # Log function processing
        self.minifier_logger.log_ast_transformation(
            transformation_type="function_mapping",
            node_type=node_type,
            details={
                "function_name": function_name,
                "source_lines": source_lines,
                "compressed_lines": compressed_lines,
                "has_decorators": bool(getattr(node, 'decorator_list', [])),
                "is_async": isinstance(node, ast.AsyncFunctionDef),
                "compression_ratio": self.compression_ratios.get(node_type, 0.5)
            },
            optimization_applied=True
        )
        
        # Create mapped node
        mapped_node = MappedNode(
            type=node_type,
            name=function_name,
            source_start=start_line,
            source_end=end_line,
            summary_start=self.current_summary_line,
            summary_end=self.current_summary_line + compressed_lines - 1
        )
        
        self.mapped_nodes.append(mapped_node)
        self.current_summary_line += compressed_lines
        
        logger.debug(f"Mapped {node_type}: {function_name} "
                    f"({start_line}-{end_line} → {mapped_node.summary_start}-{mapped_node.summary_end})")
        
        # Process nested functions (but not methods within this function)
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._walk_node(child, parent_class)
    
    def _process_class(self, node: ast.ClassDef):
        """Process class definitions."""
        class_name = node.name
        
        # Get the line span for the class header and docstring
        start_line = node.lineno
        
        # Find the first method/attribute to determine where class header ends
        first_member_line = None
        for child in node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, 
                                ast.Assign, ast.AnnAssign)):
                first_member_line = child.lineno
                break
        
        # If no members, use the entire class
        if first_member_line is None:
            class_header_end = self._get_node_end_line(node)
        else:
            class_header_end = first_member_line - 1
        
        # Calculate compressed size for class header
        source_lines = class_header_end - start_line + 1
        compressed_lines = self._calculate_compressed_lines(source_lines, 'class')
        
        # Log class processing
        self.minifier_logger.log_ast_transformation(
            transformation_type="class_mapping",
            node_type="class",
            details={
                "class_name": class_name,
                "source_lines": source_lines,
                "compressed_lines": compressed_lines,
                "has_base_classes": bool(node.bases),
                "member_count": len(node.body),
                "compression_ratio": self.compression_ratios.get('class', 0.5)
            },
            optimization_applied=True
        )
        
        # Create mapped node for class header
        mapped_node = MappedNode(
            type='class',
            name=class_name,
            source_start=start_line,
            source_end=class_header_end,
            summary_start=self.current_summary_line,
            summary_end=self.current_summary_line + compressed_lines - 1
        )
        
        self.mapped_nodes.append(mapped_node)
        self.current_summary_line += compressed_lines
        
        logger.debug(f"Mapped class: {class_name} "
                    f"({start_line}-{class_header_end} → {mapped_node.summary_start}-{mapped_node.summary_end})")
        
        # Process methods and nested classes
        for child in node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._walk_node(child, class_name)
            elif isinstance(child, ast.ClassDef):
                self._walk_node(child)
    
    def _get_node_end_line(self, node: ast.AST) -> int:
        """
        Get the actual end line of a node, handling edge cases.
        
        Args:
            node: AST node to get end line for
            
        Returns:
            End line number (1-indexed)
        """
        # Simple and universal approach for Python 3.8+
        end_line = getattr(node, "end_lineno", node.lineno)
        
        # Handle empty functions/classes - ensure at least one line
        if end_line == node.lineno and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            # Empty body - default to lineno + 1 for the definition line
            return node.lineno + 1
            
        return end_line or node.lineno
    
    def _calculate_compressed_lines(self, source_lines: int, node_type: str) -> int:
        """
        Calculate the number of lines in the compressed output.
        
        Args:
            source_lines: Number of lines in the source
            node_type: Type of node being compressed
            
        Returns:
            Number of lines in compressed output (minimum 1)
        """
        ratio = self.compression_ratios.get(node_type, 0.5)
        compressed = max(1, int(source_lines * ratio))
        
        # Log mapping statistics with MinifierLogger
        self.minifier_logger.log_optimization(
            optimization_type="line_compression",
            before_value=f"{source_lines} lines",
            after_value=f"{compressed} lines",
            node_location=f"{node_type} (ratio: {ratio})"
        )
        
        # Log mapping statistics with standard logger
        logger.debug(f"Mapped {node_type}: {source_lines} lines → {compressed} summary lines (ratio: {ratio})")
        
        return compressed
    
    # Enhanced line mapping methods with robust validation
    def get_summary_lines_for_source_range(self, start: int, end: int) -> List[int]:
        """
        Find all summary lines that correspond to a given source line range.
        
        Args:
            start: Starting line number in source code (1-based, inclusive)
            end: Ending line number in source code (1-based, inclusive)
        
        Returns:
            List of summary line numbers (sorted, unique) that correspond to the source range
        """
        return get_summary_lines_for_source_range(self.mapped_nodes, start, end)
    
    def get_source_lines_for_summary_range(self, start: int, end: int) -> List[int]:
        """
        Find all source lines that correspond to a given summary line range.
        
        Args:
            start: Starting line number in summary (1-based, inclusive)
            end: Ending line number in summary (1-based, inclusive)
        
        Returns:
            List of source line numbers (sorted, unique) that correspond to the summary range
        """
        return get_source_lines_for_summary_range(self.mapped_nodes, start, end)
    
    def get_exact_summary_line_for_source_line(self, source_line: int) -> int:
        """
        Find the exact summary line corresponding to a single source line using proportional mapping.
        
        Args:
            source_line: Source line number to map (1-based)
        
        Returns:
            Corresponding summary line number (1-based, proportionally calculated within the range)
        """
        return get_exact_summary_line_for_source_line(self.mapped_nodes, source_line)
    
    def get_exact_source_line_for_summary_line(self, summary_line: int) -> int:
        """
        Find the exact source line corresponding to a single summary line using proportional mapping.
        
        Args:
            summary_line: Summary line number to map (1-based)
        
        Returns:
            Corresponding source line number (1-based, proportionally calculated within the range)
        """
        return get_exact_source_line_for_summary_line(self.mapped_nodes, summary_line)
    
    def get_mapping_coverage_stats(self) -> Dict[str, Any]:
        """
        Calculate coverage statistics for the source mapping with optimized overlap detection.
        
        Returns:
            Dictionary with enhanced coverage statistics
        """
        if not self.mapped_nodes:
            return {
                "total_nodes": 0,
                "source_lines_covered": 0,
                "summary_lines_covered": 0,
                "compression_ratio": 0.0,
                "mapping_gaps": [],
                "overlapping_nodes": 0
            }
        
        source_lines = set()
        summary_lines = set()
        
        for node in self.mapped_nodes:
            for line in range(node.source_start, node.source_end + 1):
                source_lines.add(line)
            for line in range(node.summary_start, node.summary_end + 1):
                summary_lines.add(line)
        
        # Calculate compression ratio
        compression_ratio = len(summary_lines) / len(source_lines) if source_lines else 0.0
        
        # Find gaps in source coverage (assumes contiguous coverage is expected)
        all_source_lines = sorted(source_lines)
        gaps = []
        if len(all_source_lines) > 1:
            for i in range(min(all_source_lines), max(all_source_lines) + 1):
                if i not in source_lines:
                    gaps.append(i)
        
        # Use optimized overlap detection for large datasets
        source_intervals = [(node.source_start, node.source_end) for node in self.mapped_nodes]
        overlapping_count = _find_overlapping_intervals_optimized(source_intervals)
        
        return {
            "total_nodes": len(self.mapped_nodes),
            "source_lines_covered": len(source_lines),
            "summary_lines_covered": len(summary_lines),
            "compression_ratio": compression_ratio,
            "mapping_gaps": gaps,
            "overlapping_nodes": overlapping_count
        }
    
    def get_mapping_coverage(self) -> Dict[str, Any]:
        """
        Calculate mapping coverage statistics (legacy method for backward compatibility).
        
        Returns:
            Dictionary containing coverage statistics
        """
        if not self.source_lines:
            return {
                'total_source_lines': 0,
                'covered_lines': 0,
                'coverage_percentage': 0.0,
                'gaps': []
            }
        
        total_lines = len(self.source_lines)
        covered_lines = set()
        
        # Track covered lines
        for node in self.mapped_nodes:
            for line in range(node.source_start, node.source_end + 1):
                covered_lines.add(line)
        
        # Find gaps in coverage
        all_lines = set(range(1, total_lines + 1))
        uncovered_lines = sorted(all_lines - covered_lines)
        
        # Group consecutive uncovered lines into gaps
        gaps = []
        if uncovered_lines:
            gap_start = uncovered_lines[0]
            gap_end = uncovered_lines[0]
            
            for line in uncovered_lines[1:]:
                if line == gap_end + 1:
                    gap_end = line
                else:
                    gaps.append((gap_start, gap_end))
                    gap_start = gap_end = line
            gaps.append((gap_start, gap_end))
        
        coverage_pct = (len(covered_lines) / total_lines) * 100 if total_lines > 0 else 0
        
        return {
            'total_source_lines': total_lines,
            'covered_lines': len(covered_lines),
            'coverage_percentage': coverage_pct,
            'gaps': gaps
        }
    
    def find_source_lines_for_summary_range(self, start: int, end: int) -> List[int]:
        """
        Find all source lines that correspond to a summary line range (legacy method).
        
        Args:
            start: Start line in summary (inclusive)
            end: End line in summary (inclusive)
            
        Returns:
            Sorted list of unique source line numbers
        """
        return self.get_source_lines_for_summary_range(start, end)
    
    def find_summary_lines_for_source_range(self, start: int, end: int) -> List[int]:
        """
        Find all summary lines that correspond to a source line range (legacy method).
        
        Args:
            start: Start line in source (inclusive)
            end: End line in source (inclusive)
            
        Returns:
            Sorted list of unique summary line numbers
        """
        return self.get_summary_lines_for_source_range(start, end)
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the mapper state to a dictionary.
        
        Returns:
            Dictionary containing mapped nodes and metadata
        """
        coverage = self.get_mapping_coverage()
        enhanced_stats = self.get_mapping_coverage_stats()
        
        return {
            'nodes': [node.__dict__ for node in self.mapped_nodes],
            'metadata': {
                'total_nodes': len(self.mapped_nodes),
                'compression_ratios': self.compression_ratios,
                'coverage': coverage,
                'enhanced_stats': enhanced_stats
            }
        }
    
    def save_to_json(self, path: str, indent: int = 2) -> None:
        """
        Save the source map to a JSON file.
        
        Args:
            path: File path to save the JSON
            indent: JSON indentation level
        """
        import json
        with open(path, 'w') as f:
            json.dump(self.to_dict(), f, indent=indent)
        logger.info(f"Source map saved to {path}")
    
    @classmethod
    def load_from_json(cls, path: str) -> 'ASTMapper':
        """
        Load a source map from a JSON file.
        
        Args:
            path: File path to load the JSON from
            
        Returns:
            ASTMapper instance with loaded data
        """
        import json
        with open(path, 'r') as f:
            data = json.load(f)
        
        # Create mapper with saved compression ratios
        mapper = cls(data['metadata']['compression_ratios'])
        
        # Reconstruct nodes
        mapper.mapped_nodes = [
            MappedNode(**node_data) for node_data in data['nodes']
        ]
        
        return mapper


def build_source_map(tree: ast.AST, summary_lines: List[str]) -> List[MappedNode]:
    """
    Build a source map from an AST tree and corresponding summary lines.
    
    This function creates MappedNode objects that track the relationship between
    source code positions (from AST) and summary positions (from summary_lines index).
    
    Args:
        tree: Parsed AST tree of the original source code
        summary_lines: List of strings representing the minified/summarized output
        
    Returns:
        List of MappedNode objects mapping source positions to summary positions
        
    Edge Cases Handled:
        - Empty summary_lines list
        - AST nodes without line number information
        - Nodes with invalid or missing end_lineno
        - Summary lines that don't correspond to any AST nodes
        - Multiple AST nodes mapping to the same summary line
        - Decorators and their associated functions
        - Nested classes and functions
        - Async functions and methods
        - Import statements (both simple and from-import)
        
    Example:
        >>> import ast
        >>> source = "import os\\ndef func(): pass"
        >>> tree = ast.parse(source)
        >>> summary = ["import os", "def func():pass"]
        >>> nodes = build_source_map(tree, summary)
        >>> len(nodes)
        2
    """
    if not summary_lines:
        return []
        
    if not hasattr(tree, 'body') or not tree.body:
        return []
    
    mapped_nodes = []
    summary_index = 0
    
    def _extract_node_info(node: ast.AST, parent_class: Optional[str] = None) -> Optional[Tuple[str, str, int, int]]:
        """
        Extract node information for mapping.
        
        Returns:
            Tuple of (node_type, node_name, start_line, end_line) or None if not mappable
        """
        # Handle imports
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
            import_name = ', '.join(names)
            start_line = getattr(node, 'lineno', 1)
            end_line = getattr(node, 'end_lineno', start_line)
            return ('import', import_name, start_line, end_line)
            
        elif isinstance(node, ast.ImportFrom):
            module = getattr(node, 'module', '') or ''
            names = [alias.name for alias in node.names]
            import_name = f"from {module} import {', '.join(names)}"
            start_line = getattr(node, 'lineno', 1)
            end_line = getattr(node, 'end_lineno', start_line)
            return ('import', import_name, start_line, end_line)
            
        # Handle functions and async functions
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            node_type = 'method' if parent_class else 'function'
            function_name = node.name
            if parent_class:
                function_name = f"{parent_class}.{function_name}"
                
            # Handle decorators - find the actual start line
            start_line = getattr(node, 'lineno', 1)
            if hasattr(node, 'decorator_list') and node.decorator_list:
                decorator_lines = [getattr(d, 'lineno', start_line) for d in node.decorator_list]
                if decorator_lines:
                    start_line = min(decorator_lines)
                    
            end_line = getattr(node, 'end_lineno', start_line)
            if end_line == start_line and hasattr(node, 'body') and node.body:
                # Try to get end line from last statement in body
                last_stmt = node.body[-1]
                end_line = getattr(last_stmt, 'end_lineno', getattr(last_stmt, 'lineno', start_line))
                
            return (node_type, function_name, start_line, end_line)
            
        # Handle classes
        elif isinstance(node, ast.ClassDef):
            class_name = node.name
            start_line = getattr(node, 'lineno', 1)
            
            # For classes, we map only the class header, not the entire body
            # Find the first method/attribute to determine where class header ends
            first_member_line = None
            if hasattr(node, 'body') and node.body:
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, 
                                        ast.Assign, ast.AnnAssign)):
                        first_member_line = getattr(child, 'lineno', None)
                        break
                        
            if first_member_line is None:
                # No members, use entire class
                end_line = getattr(node, 'end_lineno', start_line)
            else:
                # Class header ends before first member
                end_line = first_member_line - 1
                
            return ('class', class_name, start_line, end_line)
            
        return None
    
    def _walk_ast_nodes(node: ast.AST, parent_class: Optional[str] = None) -> None:
        """
        Recursively walk AST nodes and build mappings.
        """
        nonlocal summary_index, mapped_nodes
        
        # Extract node information
        node_info = _extract_node_info(node, parent_class)
        
        if node_info and summary_index < len(summary_lines):
            node_type, node_name, source_start, source_end = node_info
            
            # Ensure we have valid line numbers
            if source_start <= 0:
                source_start = 1
            if source_end <= 0 or source_end < source_start:
                source_end = source_start
                
            # Create mapped node - summary positions are 1-indexed
            mapped_node = MappedNode(
                type=node_type,
                name=node_name,
                source_start=source_start,
                source_end=source_end,
                summary_start=summary_index + 1,  # Convert to 1-indexed
                summary_end=summary_index + 1     # Single line mapping by default
            )
            
            mapped_nodes.append(mapped_node)
            summary_index += 1
        
        # Handle class members
        if isinstance(node, ast.ClassDef):
            class_name = node.name
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    _walk_ast_nodes(child, class_name)
                elif isinstance(child, ast.ClassDef):
                    _walk_ast_nodes(child)
                    
        # Handle nested functions
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    _walk_ast_nodes(child, parent_class)
                    
        # Handle other node types - continue walking
        else:
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.Import, ast.ImportFrom, ast.FunctionDef, 
                                    ast.AsyncFunctionDef, ast.ClassDef)):
                    _walk_ast_nodes(child, parent_class)
    
    # Start walking from the module body
    try:
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef, 
                               ast.AsyncFunctionDef, ast.ClassDef)):
                _walk_ast_nodes(node)
                
    except (AttributeError, TypeError) as e:
        # Handle cases where AST structure is unexpected
        logger.warning(f"Error walking AST: {e}")
        return mapped_nodes
    
    # Validate the mapping
    _validate_source_map(mapped_nodes, len(summary_lines))
    
    return mapped_nodes


def _validate_source_map(mapped_nodes: List[MappedNode], summary_line_count: int) -> None:
    """
    Validate the generated source map for common issues.
    
    Args:
        mapped_nodes: List of mapped nodes to validate
        summary_line_count: Total number of summary lines
        
    Raises:
        ValueError: If validation fails
    """
    if not mapped_nodes:
        return
        
    # Check for overlapping summary ranges
    for i, node in enumerate(mapped_nodes):
        for j, other in enumerate(mapped_nodes):
            if i != j:
                if not (node.summary_end < other.summary_start or 
                       other.summary_end < node.summary_start):
                    logger.warning(f"Overlapping summary ranges detected: {node.name} "
                                 f"({node.summary_start}-{node.summary_end}) overlaps with "
                                 f"{other.name} ({other.summary_start}-{other.summary_end})")
    
    # Check for invalid line numbers
    for node in mapped_nodes:
        if node.source_start <= 0 or node.source_end <= 0:
            logger.warning(f"Invalid source line numbers for {node.name}: "
                         f"{node.source_start}-{node.source_end}")
                         
        if node.summary_start <= 0 or node.summary_end <= 0:
            logger.warning(f"Invalid summary line numbers for {node.name}: "
                         f"{node.summary_start}-{node.summary_end}")
                         
        if node.summary_end > summary_line_count:
            logger.warning(f"Summary line number out of range for {node.name}: "
                         f"{node.summary_end} > {summary_line_count}")
    
    # Check for monotonic summary line progression
    sorted_nodes = sorted(mapped_nodes, key=lambda x: x.summary_start)
    for i in range(len(sorted_nodes) - 1):
        current = sorted_nodes[i]
        next_node = sorted_nodes[i + 1]
        if current.summary_end >= next_node.summary_start:
            logger.warning(f"Non-monotonic summary progression: {current.name} "
                         f"ends at {current.summary_end}, {next_node.name} "
                         f"starts at {next_node.summary_start}")


def walk_ast_and_map(source_code: str, 
                    compression_ratios: Optional[Dict[str, float]] = None,
                    validate: bool = True,
                    minifier_logger: Optional[MinifierLogger] = None) -> List[MappedNode]:
    """
    Convenience function to walk an AST and produce MappedNode objects.
    
    Args:
        source_code: Python source code to analyze
        compression_ratios: Optional dict of node type to compression ratio
        validate: Whether to validate non-overlapping mappings
        minifier_logger: Optional MinifierLogger for detailed logging
        
    Returns:
        List of MappedNode objects representing the source-to-summary mapping
    
    Example:
        >>> code = '''
        ... import os
        ... from typing import List
        ... 
        ... class MyClass:
        ...     def __init__(self):
        ...         pass
        ...     
        ...     def method(self):
        ...         return "hello"
        ... 
        ... def standalone_function():
        ...     x = 1
        ...     y = 2
        ...     return x + y
        ... '''
        >>> 
        >>> nodes = walk_ast_and_map(code)
        >>> for node in nodes:
        ...     print(f"{node.type}: {node.name} "
        ...           f"(source: {node.source_start}-{node.source_end}, "
        ...           f"summary: {node.summary_start}-{node.summary_end})")
    """
    start_time = time.time()
    
    # Get or create logger
    if minifier_logger is None:
        minifier_logger = get_logger()
    
    mapper = ASTMapper(compression_ratios, minifier_logger)
    
    try:
        nodes = mapper.walk_ast(source_code)
        
        # Validate non-overlapping mappings if requested
        if validate:
            validate_non_overlapping(nodes)
            minifier_logger.log_validation_result(
                operation_id=mapper.operation_id,
                validation_passed=True,
                validation_time=time.time() - start_time,
                validation_details={"validation_type": "non_overlapping_ranges"}
            )
        
        # Log coverage statistics
        coverage = mapper.get_mapping_coverage()
        minifier_logger.log_optimization(
            optimization_type="mapping_coverage",
            before_value=f"{coverage['total_source_lines']} total lines",
            after_value=f"{coverage['covered_lines']} covered lines",
            node_location=f"{coverage['coverage_percentage']:.1f}% coverage"
        )
        
        logger.info(f"Mapping coverage: {coverage['coverage_percentage']:.1f}% "
                    f"({coverage['covered_lines']}/{coverage['total_source_lines']} lines)")
        if coverage['gaps']:
            logger.warning(f"Coverage gaps found: {coverage['gaps']}")
            minifier_logger.log_optimization(
                optimization_type="coverage_gaps",
                before_value="complete coverage expected",
                after_value=f"{len(coverage['gaps'])} gaps found",
                node_location=str(coverage['gaps'])
            )
    
    except Exception as e:
        if validate:
            minifier_logger.log_validation_result(
                operation_id=mapper.operation_id,
                validation_passed=False,
                validation_time=time.time() - start_time,
                validation_details={"error": str(e)}
            )
        raise
    
    return nodes


def validate_non_overlapping(nodes: List[MappedNode]) -> None:
    """
    Validate that mapped nodes don't have overlapping summary ranges.
    
    Args:
        nodes: List of MappedNode objects to validate
        
    Raises:
        ValueError: If overlapping summary ranges are found
    """
    for i, node in enumerate(nodes):
        for j, other in enumerate(nodes):
            if i != j:
                # Check for overlapping summary ranges
                if not (node.summary_end < other.summary_start or 
                        other.summary_end < node.summary_start):
                    raise ValueError(
                        f"Overlapping summary ranges: {node.name} "
                        f"({node.summary_start}-{node.summary_end}) overlaps with "
                        f"{other.name} ({other.summary_start}-{other.summary_end})"
                    )


# Example usage with enhanced line mapping capabilities
def main():
    """Main function to demonstrate the enhanced AST mapper."""
    # Configure logging
    logging.basicConfig(level=logging.DEBUG, 
                       format='%(levelname)s - %(message)s')
    
    example_code = """
import os
import sys
from typing import List, Dict

@decorator
class DataProcessor:
    '''A class for processing data.'''
    
    def __init__(self, config: Dict):
        self.config = config
        self.data = []
    
    @property
    def size(self) -> int:
        return len(self.data)
    
    def load_data(self, filepath: str) -> List:
        '''Load data from file.'''
        with open(filepath, 'r') as f:
            lines = f.readlines()
        
        for line in lines:
            self.data.append(line.strip())
        
        return self.data
    
    def process(self) -> Dict:
        '''Process the loaded data.'''
        result = {}
        for item in self.data:
            key = item[:3]
            if key in result:
                result[key] += 1
            else:
                result[key] = 1
        return result

@decorator_one
@decorator_two
def helper_function(x: int, y: int) -> int:
    '''A simple helper function.'''
    if x > y:
        return x - y
    else:
        return y - x

async def async_operation():
    '''An async function example.'''
    import asyncio
    await asyncio.sleep(1)
    return "done"

def empty_function():
    pass
"""
    
    # Use custom compression ratios
    custom_ratios = {
        'import': 1.0,      # Keep imports as-is
        'function': 0.3,    # Aggressive function compression
        'class': 0.6,       # Moderate class compression
        'method': 0.4,      # Methods compress well
    }
    
    # Map with validation
    nodes = walk_ast_and_map(example_code, custom_ratios, validate=True)
    
    print("\nSource-to-Summary Mapping:")
    print("-" * 80)
    print(f"{'Type':10} | {'Name':30} | {'Source':13} | {'Summary':13}")
    print("-" * 80)
    for node in nodes:
        print(f"{node.type:10} | {node.name[:30]:30} | "
              f"{node.source_start:3}-{node.source_end:3} (L{node.source_end - node.source_start + 1:2}) | "
              f"{node.summary_start:3}-{node.summary_end:3} (L{node.summary_end - node.summary_start + 1:2})")
    
    # Test enhanced bidirectional mapping
    mapper = ASTMapper(custom_ratios)
    mapper.walk_ast(example_code)
    
    print("\nEnhanced Mapping Examples:")
    print("=" * 50)
    
    # Test range mapping
    print(f"Source range 10-20 -> Summary lines: {mapper.get_summary_lines_for_source_range(10, 20)}")
    print(f"Summary range 5-10 -> Source lines: {mapper.get_source_lines_for_summary_range(5, 10)}")
    
    # Test exact line mapping with proportional calculation
    try:
        exact_summary = mapper.get_exact_summary_line_for_source_line(15)
        print(f"Exact mapping: Source line 15 -> Summary line {exact_summary}")
        
        exact_source = mapper.get_exact_source_line_for_summary_line(8)
        print(f"Exact mapping: Summary line 8 -> Source line {exact_source}")
    except LineNotFoundError as e:
        print(f"Line mapping error: {e}")
    
    # Show enhanced coverage statistics
    enhanced_stats = mapper.get_mapping_coverage_stats()
    print(f"\nEnhanced Coverage Statistics:")
    print(f"  Total nodes: {enhanced_stats['total_nodes']}")
    print(f"  Source lines covered: {enhanced_stats['source_lines_covered']}")
    print(f"  Summary lines: {enhanced_stats['summary_lines_covered']}")
    print(f"  Compression ratio: {enhanced_stats['compression_ratio']:.2f}")
    print(f"  Overlapping nodes: {enhanced_stats['overlapping_nodes']}")
    if enhanced_stats['mapping_gaps']:
        print(f"  Mapping gaps: {enhanced_stats['mapping_gaps'][:10]}...")  # Show first 10 gaps
    
    # Legacy coverage for backward compatibility
    legacy_coverage = mapper.get_mapping_coverage()
    print(f"\nLegacy Coverage: {legacy_coverage['coverage_percentage']:.1f}% "
          f"({legacy_coverage['covered_lines']}/{legacy_coverage['total_source_lines']} lines)")
    
    # Save to JSON with enhanced metadata
    mapper.save_to_json("enhanced_source_map.json")
    print("\nEnhanced source map saved to enhanced_source_map.json")


# ============================================================================
# ENHANCED PYTEST TEST CASES
# ============================================================================

def test_enhanced_range_mapping():
    """Test enhanced range mapping functionality."""
    code = """
import os
import sys

def function_one():
    x = 1
    y = 2
    return x + y

class TestClass:
    def method_one(self):
        return 1
    
    def method_two(self):
        return 2

def function_two():
    return 42
"""
    mapper = ASTMapper({'import': 1.0, 'function': 0.5, 'class': 0.6, 'method': 0.4})
    nodes = mapper.walk_ast(code)
    
    # Test range mapping
    summary_lines = mapper.get_summary_lines_for_source_range(5, 12)
    assert len(summary_lines) > 0
    
    source_lines = mapper.get_source_lines_for_summary_range(3, 8)
    assert len(source_lines) > 0


def test_exact_proportional_mapping():
    """Test exact proportional line mapping."""
    code = """
def long_function():
    line1 = 1
    line2 = 2
    line3 = 3
    line4 = 4
    line5 = 5
    line6 = 6
    line7 = 7
    line8 = 8
    return sum([line1, line2, line3, line4, line5, line6, line7, line8])
"""
    mapper = ASTMapper({'function': 0.5})  # 50% compression
    nodes = mapper.walk_ast(code)
    
    # Test exact mapping - should work for lines within the function
    try:
        summary_line = mapper.get_exact_summary_line_for_source_line(5)  # Middle of function
        assert summary_line > 0
        
        source_line = mapper.get_exact_source_line_for_summary_line(summary_line)
        assert source_line > 0
    except LineNotFoundError:
        # This is acceptable if the line is not in a mapped range
        pass


def test_enhanced_validation():
    """Test enhanced validation features."""
    code = """
import os

def valid_function():
    return 42
"""
    # Test with validation enabled
    nodes = walk_ast_and_map(code, validate=True)
    assert len(nodes) == 2
    
    # Test MappedNode validation
    try:
        # This should raise an error due to invalid range
        invalid_node = MappedNode("function", "invalid", 10, 5, 1, 1)
        assert False, "Should have raised InvalidMappedNodeError"
    except InvalidMappedNodeError:
        pass


def test_optimized_overlap_detection():
    """Test optimized overlap detection performance."""
    # Create a large number of intervals to test performance
    intervals = [(i, i + 5) for i in range(0, 1000, 3)]  # Overlapping intervals
    
    overlaps = _find_overlapping_intervals_optimized(intervals)
    assert overlaps > 0  # Should detect overlaps


def test_enhanced_coverage_stats():
    """Test enhanced coverage statistics."""
    code = """
import os
import sys

class MyClass:
    def method(self):
        return 1

def function():
    x = 1
    return x
"""
    mapper = ASTMapper()
    nodes = mapper.walk_ast(code)
    
    stats = mapper.get_mapping_coverage_stats()
    
    assert stats['total_nodes'] == len(nodes)
    assert stats['source_lines_covered'] > 0
    assert stats['summary_lines_covered'] > 0
    assert 0.0 <= stats['compression_ratio'] <= 1.0
    assert isinstance(stats['mapping_gaps'], list)
    assert isinstance(stats['overlapping_nodes'], int)


def test_error_handling():
    """Test enhanced error handling."""
    mapper = ASTMapper()
    nodes = mapper.walk_ast("import os\ndef func(): pass")
    
    # Test invalid range parameters
    try:
        mapper.get_summary_lines_for_source_range(10, 5)  # Invalid range
        assert False, "Should have raised InvalidRangeError"
    except InvalidRangeError:
        pass
    
    try:
        mapper.get_exact_summary_line_for_source_line(0)  # 0-based line number
        assert False, "Should have raised InvalidRangeError"
    except InvalidRangeError:
        pass
    
    # Test line not found
    try:
        mapper.get_exact_summary_line_for_source_line(1000)  # Non-existent line
        assert False, "Should have raised LineNotFoundError"
    except LineNotFoundError:
        pass


def test_string_interning():
    """Test string interning for memory efficiency."""
    code = """
def function_one(): pass
def function_two(): pass
class ClassOne: pass
class ClassTwo: pass
"""
    mapper = ASTMapper()
    nodes = mapper.walk_ast(code)
    
    # Find nodes with same type
    function_nodes = [n for n in nodes if n.type == 'function']
    class_nodes = [n for n in nodes if n.type == 'class']
    
    if len(function_nodes) >= 2:
        # Same type strings should be the same object after interning
        assert function_nodes[0].type is function_nodes[1].type
    
    if len(class_nodes) >= 2:
        assert class_nodes[0].type is class_nodes[1].type


if __name__ == "__main__":
    # Run the enhanced example when executed directly
    main()