"""
Production-optimized mapping engine with performance and reliability enhancements.

This module provides an enhanced version of the mapping engine designed for
production use with large codebases, concurrent access, and advanced features.
"""

import json
import logging
import threading
import hashlib
import time
from dataclasses import dataclass, asdict, field
from typing import List, Optional, Dict, Any, Union, Tuple, Set, Iterator
from collections import defaultdict
from contextlib import contextmanager
from abc import ABC, abstractmethod

# Optional dependencies for advanced features
try:
    from intervaltree import IntervalTree, Interval
    HAS_INTERVAL_TREE = True
except ImportError:
    HAS_INTERVAL_TREE = False

# Import base classes for fallback
from .source_map import MappedNode as BaseMappedNode, SourceMap as BaseSourceMap


# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class EnhancedMappedNode(BaseMappedNode):
    """
    Enhanced MappedNode with additional production features.
    
    Adds metadata tracking, content validation, and versioning support.
    """
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    content_hash: Optional[str] = None
    version: int = 1
    parent_id: Optional[str] = None  # For hierarchical mappings
    children_ids: Set[str] = field(default_factory=set)
    
    def __post_init__(self):
        """Enhanced validation with logging."""
        super().__post_init__()
        logger.debug(f"Created MappedNode: {self.name} ({self.type})")
    
    def add_metadata(self, key: str, value: Any) -> None:
        """Add metadata to the node."""
        self.metadata[key] = value
        logger.debug(f"Added metadata to {self.name}: {key}={value}")
    
    def get_metadata(self, key: str, default: Any = None) -> Any:
        """Get metadata value with default fallback."""
        return self.metadata.get(key, default)
    
    def set_content_hash(self, content: str) -> None:
        """Set content hash for validation."""
        self.content_hash = hashlib.sha256(content.encode()).hexdigest()
        logger.debug(f"Set content hash for {self.name}: {self.content_hash[:8]}...")
    
    def validate_content(self, content: str) -> bool:
        """Validate content against stored hash."""
        if not self.content_hash:
            return True  # No hash to validate against
        
        current_hash = hashlib.sha256(content.encode()).hexdigest()
        is_valid = current_hash == self.content_hash
        
        if not is_valid:
            logger.warning(f"Content validation failed for {self.name}")
        
        return is_valid
    
    def to_dict(self) -> Dict[str, Any]:
        """Enhanced dictionary conversion with all fields."""
        base_dict = super().to_dict()
        base_dict.update({
            'metadata': self.metadata,
            'created_at': self.created_at,
            'content_hash': self.content_hash,
            'version': self.version,
            'parent_id': self.parent_id,
            'children_ids': list(self.children_ids)
        })
        return base_dict


class SourceMapIndex(ABC):
    """Abstract base class for source map indices."""
    
    @abstractmethod
    def build_index(self, nodes: List[EnhancedMappedNode]) -> None:
        """Build the index from nodes."""
        pass
    
    @abstractmethod
    def find_nodes_at_source_line(self, line: int) -> List[EnhancedMappedNode]:
        """Find nodes containing the source line."""
        pass
    
    @abstractmethod
    def find_nodes_at_summary_line(self, line: int) -> List[EnhancedMappedNode]:
        """Find nodes containing the summary line."""
        pass


class LinearIndex(SourceMapIndex):
    """Basic linear search index (fallback implementation)."""
    
    def __init__(self):
        self.nodes: List[EnhancedMappedNode] = []
    
    def build_index(self, nodes: List[EnhancedMappedNode]) -> None:
        """Build linear index (just store nodes)."""
        self.nodes = nodes
    
    def find_nodes_at_source_line(self, line: int) -> List[EnhancedMappedNode]:
        """Linear search for source line."""
        return [node for node in self.nodes if node.contains_source_line(line)]
    
    def find_nodes_at_summary_line(self, line: int) -> List[EnhancedMappedNode]:
        """Linear search for summary line."""
        return [node for node in self.nodes if node.contains_summary_line(line)]


class IntervalTreeIndex(SourceMapIndex):
    """High-performance interval tree index for O(log n) lookups."""
    
    def __init__(self):
        if not HAS_INTERVAL_TREE:
            raise ImportError("intervaltree package required for IntervalTreeIndex")
        
        self.source_tree = IntervalTree()
        self.summary_tree = IntervalTree()
    
    def build_index(self, nodes: List[EnhancedMappedNode]) -> None:
        """Build interval tree indices."""
        self.source_tree.clear()
        self.summary_tree.clear()
        
        for node in nodes:
            # Add to source tree (end + 1 for exclusive end in IntervalTree)
            self.source_tree.add(
                Interval(node.source_start, node.source_end + 1, node)
            )
            
            # Add to summary tree
            self.summary_tree.add(
                Interval(node.summary_start, node.summary_end + 1, node)
            )
        
        logger.debug(f"Built interval tree index with {len(nodes)} nodes")
    
    def find_nodes_at_source_line(self, line: int) -> List[EnhancedMappedNode]:
        """Find nodes using interval tree lookup."""
        intervals = self.source_tree.at(line)
        return [interval.data for interval in intervals]
    
    def find_nodes_at_summary_line(self, line: int) -> List[EnhancedMappedNode]:
        """Find nodes using interval tree lookup."""
        intervals = self.summary_tree.at(line)
        return [interval.data for interval in intervals]


class BinarySearchIndex(SourceMapIndex):
    """Binary search index for sorted node lists."""
    
    def __init__(self):
        self.source_sorted_nodes: List[EnhancedMappedNode] = []
        self.summary_sorted_nodes: List[EnhancedMappedNode] = []
    
    def build_index(self, nodes: List[EnhancedMappedNode]) -> None:
        """Build sorted indices for binary search."""
        self.source_sorted_nodes = sorted(nodes, key=lambda n: n.source_start)
        self.summary_sorted_nodes = sorted(nodes, key=lambda n: n.summary_start)
        logger.debug(f"Built binary search index with {len(nodes)} nodes")
    
    def _binary_search_source(self, line: int) -> List[EnhancedMappedNode]:
        """Binary search for nodes containing source line."""
        result = []
        left, right = 0, len(self.source_sorted_nodes) - 1
        
        while left <= right:
            mid = (left + right) // 2
            node = self.source_sorted_nodes[mid]
            
            if node.contains_source_line(line):
                result.append(node)
                # Check adjacent nodes that might also contain the line
                i = mid - 1
                while i >= 0 and self.source_sorted_nodes[i].contains_source_line(line):
                    result.append(self.source_sorted_nodes[i])
                    i -= 1
                i = mid + 1
                while i < len(self.source_sorted_nodes) and self.source_sorted_nodes[i].contains_source_line(line):
                    result.append(self.source_sorted_nodes[i])
                    i += 1
                break
            elif line < node.source_start:
                right = mid - 1
            else:
                left = mid + 1
        
        return result
    
    def _binary_search_summary(self, line: int) -> List[EnhancedMappedNode]:
        """Binary search for nodes containing summary line."""
        result = []
        left, right = 0, len(self.summary_sorted_nodes) - 1
        
        while left <= right:
            mid = (left + right) // 2
            node = self.summary_sorted_nodes[mid]
            
            if node.contains_summary_line(line):
                result.append(node)
                # Check adjacent nodes that might also contain the line
                i = mid - 1
                while i >= 0 and self.summary_sorted_nodes[i].contains_summary_line(line):
                    result.append(self.summary_sorted_nodes[i])
                    i -= 1
                i = mid + 1
                while i < len(self.summary_sorted_nodes) and self.summary_sorted_nodes[i].contains_summary_line(line):
                    result.append(self.summary_sorted_nodes[i])
                    i += 1
                break
            elif line < node.summary_start:
                right = mid - 1
            else:
                left = mid + 1
        
        return result
    
    def find_nodes_at_source_line(self, line: int) -> List[EnhancedMappedNode]:
        """Find nodes using binary search."""
        return self._binary_search_source(line)
    
    def find_nodes_at_summary_line(self, line: int) -> List[EnhancedMappedNode]:
        """Find nodes using binary search."""
        return self._binary_search_summary(line)


class ProductionSourceMap:
    """
    Production-ready SourceMap with performance optimizations and advanced features.
    
    Features:
    - Multiple indexing strategies for optimal performance
    - Thread-safe operations with locking
    - Error recovery and validation
    - Metrics and monitoring hooks
    - Memory-efficient operations
    - Hierarchical mapping support
    """
    
    def __init__(self, 
                 nodes: Optional[List[EnhancedMappedNode]] = None,
                 index_type: str = "auto",
                 thread_safe: bool = True,
                 validate_content: bool = False):
        """
        Initialize production source map.
        
        Args:
            nodes: List of nodes to initialize with
            index_type: Index type ("linear", "binary", "interval", "auto")
            thread_safe: Enable thread-safe operations
            validate_content: Enable content validation
        """
        self.nodes: List[EnhancedMappedNode] = nodes or []
        self.validate_content = validate_content
        self.metrics = defaultdict(int)
        self._lock = threading.RLock() if thread_safe else None
        
        # Choose index implementation
        self.index = self._create_index(index_type)
        
        # Build initial index
        if self.nodes:
            self._rebuild_index()
        
        logger.info(f"Initialized ProductionSourceMap with {len(self.nodes)} nodes using {type(self.index).__name__}")
    
    def _create_index(self, index_type: str) -> SourceMapIndex:
        """Create the appropriate index implementation."""
        if index_type == "auto":
            # Choose best available index
            if HAS_INTERVAL_TREE:
                return IntervalTreeIndex()
            else:
                return BinarySearchIndex()
        elif index_type == "interval":
            return IntervalTreeIndex()
        elif index_type == "binary":
            return BinarySearchIndex()
        elif index_type == "linear":
            return LinearIndex()
        else:
            raise ValueError(f"Unknown index type: {index_type}")
    
    @contextmanager
    def _lock_context(self):
        """Context manager for thread-safe operations."""
        if self._lock:
            with self._lock:
                yield
        else:
            yield
    
    def _rebuild_index(self):
        """Rebuild the search index."""
        try:
            self.index.build_index(self.nodes)
            self.metrics['index_rebuilds'] += 1
            logger.debug("Rebuilt search index")
        except Exception as e:
            logger.error(f"Failed to rebuild index: {e}")
            # Fallback to linear index
            self.index = LinearIndex()
            self.index.build_index(self.nodes)
            logger.warning("Fell back to linear index")
    
    def add_node(self, node: EnhancedMappedNode, rebuild_index: bool = True) -> None:
        """
        Add a node with thread-safe operation and validation.
        
        Args:
            node: Node to add
            rebuild_index: Whether to rebuild index immediately
        """
        with self._lock_context():
            try:
                # Validate node doesn't create overlaps
                temp_nodes = self.nodes + [node]
                self._validate_nodes(temp_nodes)
                
                # Add node
                self.nodes.append(node)
                self.metrics['nodes_added'] += 1
                
                # Rebuild index if requested
                if rebuild_index:
                    self._rebuild_index()
                
                logger.debug(f"Added node: {node.name}")
                
            except Exception as e:
                logger.error(f"Failed to add node {node.name}: {e}")
                raise
    
    def add_nodes_batch(self, nodes: List[EnhancedMappedNode]) -> None:
        """
        Add multiple nodes efficiently with single index rebuild.
        
        Args:
            nodes: List of nodes to add
        """
        with self._lock_context():
            try:
                # Validate all nodes together
                temp_nodes = self.nodes + nodes
                self._validate_nodes(temp_nodes)
                
                # Add all nodes
                self.nodes.extend(nodes)
                self.metrics['nodes_added'] += len(nodes)
                self.metrics['batch_operations'] += 1
                
                # Single index rebuild
                self._rebuild_index()
                
                logger.info(f"Added {len(nodes)} nodes in batch")
                
            except Exception as e:
                logger.error(f"Failed to add batch of {len(nodes)} nodes: {e}")
                raise
    
    def _validate_nodes(self, nodes: List[EnhancedMappedNode]) -> None:
        """Enhanced validation with better error reporting."""
        # Sort for validation
        source_sorted = sorted(nodes, key=lambda n: n.source_start)
        summary_sorted = sorted(nodes, key=lambda n: n.summary_start)
        
        # Check source overlaps
        for i in range(len(source_sorted) - 1):
            current = source_sorted[i]
            next_node = source_sorted[i + 1]
            
            if current.source_end >= next_node.source_start:
                raise ValueError(
                    f"Overlapping source ranges: {current.name} "
                    f"({current.source_start}-{current.source_end}) overlaps with "
                    f"{next_node.name} ({next_node.source_start}-{next_node.source_end})"
                )
        
        # Check summary overlaps
        for i in range(len(summary_sorted) - 1):
            current = summary_sorted[i]
            next_node = summary_sorted[i + 1]
            
            if current.summary_end >= next_node.summary_start:
                raise ValueError(
                    f"Overlapping summary ranges: {current.name} "
                    f"({current.summary_start}-{current.summary_end}) overlaps with "
                    f"{next_node.name} ({next_node.summary_start}-{next_node.summary_end})"
                )
    
    def find_summary_for_source_line(self, line: int) -> Optional[EnhancedMappedNode]:
        """
        Optimized lookup with metrics tracking.
        
        Args:
            line: Source line number
            
        Returns:
            First matching node or None
        """
        with self._lock_context():
            self.metrics['source_lookups'] += 1
            
            try:
                nodes = self.index.find_nodes_at_source_line(line)
                result = nodes[0] if nodes else None
                
                if result:
                    self.metrics['source_lookup_hits'] += 1
                
                return result
                
            except Exception as e:
                logger.error(f"Error in source line lookup for line {line}: {e}")
                self.metrics['lookup_errors'] += 1
                return None
    
    def find_source_for_summary_line(self, line: int) -> Optional[EnhancedMappedNode]:
        """
        Optimized lookup with metrics tracking.
        
        Args:
            line: Summary line number
            
        Returns:
            First matching node or None
        """
        with self._lock_context():
            self.metrics['summary_lookups'] += 1
            
            try:
                nodes = self.index.find_nodes_at_summary_line(line)
                result = nodes[0] if nodes else None
                
                if result:
                    self.metrics['summary_lookup_hits'] += 1
                
                return result
                
            except Exception as e:
                logger.error(f"Error in summary line lookup for line {line}: {e}")
                self.metrics['lookup_errors'] += 1
                return None
    
    def find_all_nodes_at_source_line(self, line: int) -> List[EnhancedMappedNode]:
        """Find all nodes containing the source line (for overlapping scenarios)."""
        with self._lock_context():
            self.metrics['source_lookups'] += 1
            
            try:
                nodes = self.index.find_nodes_at_source_line(line)
                
                if nodes:
                    self.metrics['source_lookup_hits'] += 1
                
                return nodes
                
            except Exception as e:
                logger.error(f"Error in source line lookup for line {line}: {e}")
                self.metrics['lookup_errors'] += 1
                return []
    
    def find_all_nodes_at_summary_line(self, line: int) -> List[EnhancedMappedNode]:
        """Find all nodes containing the summary line (for overlapping scenarios)."""
        with self._lock_context():
            self.metrics['summary_lookups'] += 1
            
            try:
                nodes = self.index.find_nodes_at_summary_line(line)
                
                if nodes:
                    self.metrics['summary_lookup_hits'] += 1
                
                return nodes
                
            except Exception as e:
                logger.error(f"Error in summary line lookup for line {line}: {e}")
                self.metrics['lookup_errors'] += 1
                return []
    
    def get_summary_line_for_source_line(self, source_line: int) -> Optional[int]:
        """Enhanced proportional mapping with error handling."""
        node = self.find_summary_for_source_line(source_line)
        if not node:
            return None
        
        try:
            # Calculate proportional position
            source_offset = source_line - node.source_start
            source_range = node.source_end - node.source_start
            summary_range = node.summary_end - node.summary_start
            
            if source_range == 0:
                return node.summary_start
            
            # Proportional mapping with bounds checking
            summary_offset = int((source_offset / source_range) * summary_range)
            result = node.summary_start + summary_offset
            
            # Ensure result is within bounds
            return max(node.summary_start, min(node.summary_end, result))
            
        except Exception as e:
            logger.error(f"Error calculating summary line for source {source_line}: {e}")
            return None
    
    def get_source_line_for_summary_line(self, summary_line: int) -> Optional[int]:
        """Enhanced proportional mapping with error handling."""
        node = self.find_source_for_summary_line(summary_line)
        if not node:
            return None
        
        try:
            # Calculate proportional position
            summary_offset = summary_line - node.summary_start
            summary_range = node.summary_end - node.summary_start
            source_range = node.source_end - node.source_start
            
            if summary_range == 0:
                return node.source_start
            
            # Proportional mapping with bounds checking
            source_offset = int((summary_offset / summary_range) * source_range)
            result = node.source_start + source_offset
            
            # Ensure result is within bounds
            return max(node.source_start, min(node.source_end, result))
            
        except Exception as e:
            logger.error(f"Error calculating source line for summary {summary_line}: {e}")
            return None
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get performance and usage metrics."""
        with self._lock_context():
            hit_rate = 0
            if self.metrics['source_lookups'] > 0:
                hit_rate = (self.metrics['source_lookup_hits'] + self.metrics['summary_lookup_hits']) / \
                          (self.metrics['source_lookups'] + self.metrics['summary_lookups'])
            
            return {
                'node_count': len(self.nodes),
                'index_type': type(self.index).__name__,
                'lookup_hit_rate': hit_rate,
                'raw_metrics': dict(self.metrics)
            }
    
    def validate_all_content(self, source_content: str, summary_content: str) -> Dict[str, bool]:
        """
        Validate all nodes against their expected content.
        
        Args:
            source_content: Full source content
            summary_content: Full summary content
            
        Returns:
            Dictionary mapping node names to validation results
        """
        if not self.validate_content:
            return {}
        
        results = {}
        source_lines = source_content.split('\n')
        summary_lines = summary_content.split('\n')
        
        for node in self.nodes:
            try:
                # Extract node content
                node_source = '\n'.join(source_lines[node.source_start-1:node.source_end])
                node_summary = '\n'.join(summary_lines[node.summary_start-1:node.summary_end])
                
                # Validate (simplified - in practice you'd validate the mapping relationship)
                source_valid = node.validate_content(node_source)
                summary_valid = node.validate_content(node_summary)
                
                results[node.name] = source_valid and summary_valid
                
            except Exception as e:
                logger.error(f"Content validation error for {node.name}: {e}")
                results[node.name] = False
        
        return results
    
    def to_dict(self) -> Dict[str, Any]:
        """Enhanced serialization with metadata."""
        with self._lock_context():
            return {
                'nodes': [node.to_dict() for node in self.nodes],
                'node_count': len(self.nodes),
                'index_type': type(self.index).__name__,
                'metrics': dict(self.metrics),
                'created_at': time.time()
            }
    
    def to_json(self, indent: Optional[int] = None) -> str:
        """Enhanced JSON serialization."""
        return json.dumps(self.to_dict(), indent=indent)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any], **kwargs) -> 'ProductionSourceMap':
        """Enhanced deserialization with error recovery."""
        try:
            nodes_data = data.get('nodes', [])
            nodes = []
            
            for node_data in nodes_data:
                try:
                    # Handle both old and new node formats
                    if 'metadata' in node_data:
                        node = EnhancedMappedNode(**node_data)
                    else:
                        # Convert old format to new format
                        enhanced_data = dict(node_data)
                        enhanced_data.update({
                            'metadata': {},
                            'created_at': time.time(),
                            'content_hash': None,
                            'version': 1,
                            'parent_id': None,
                            'children_ids': set()
                        })
                        node = EnhancedMappedNode(**enhanced_data)
                    
                    nodes.append(node)
                    
                except Exception as e:
                    logger.warning(f"Skipping invalid node data: {e}")
                    continue
            
            return cls(nodes, **kwargs)
            
        except Exception as e:
            logger.error(f"Error deserializing SourceMap: {e}")
            return cls(**kwargs)  # Return empty map as fallback
    
    @classmethod
    def from_json(cls, json_str: str, **kwargs) -> 'ProductionSourceMap':
        """Enhanced JSON deserialization with error recovery."""
        try:
            data = json.loads(json_str)
            return cls.from_dict(data, **kwargs)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON data: {e}")
            return cls(**kwargs)  # Return empty map as fallback
    
    def __len__(self) -> int:
        """Thread-safe length."""
        with self._lock_context():
            return len(self.nodes)
    
    def __repr__(self) -> str:
        """Enhanced string representation with metrics."""
        return f"ProductionSourceMap(nodes={len(self.nodes)}, index={type(self.index).__name__})"
