"""
Mapping engine for tracking relationships between source and summary content.

This module provides data models and utilities for maintaining bidirectional
mappings between original source content and its compressed/summarized versions.
"""

import json
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Any, Union


@dataclass
class MappedNode:
    """
    Represents a mapped relationship between source and summary content.
    
    Attributes:
        type: The type of content node (e.g., 'function', 'class', 'comment', 'block')
        name: Human-readable name or identifier for the node
        source_start: Starting line number in the original source (1-indexed)
        source_end: Ending line number in the original source (1-indexed)
        summary_start: Starting line number in the summary/compressed version (1-indexed)
        summary_end: Ending line number in the summary/compressed version (1-indexed)
    """
    type: str
    name: str
    source_start: int
    source_end: int
    summary_start: int
    summary_end: int
    
    def __post_init__(self):
        """Validate the node data after initialization."""
        if self.source_start <= 0 or self.source_end <= 0:
            raise ValueError("Source line numbers must be positive (1-indexed)")
        if self.summary_start <= 0 or self.summary_end <= 0:
            raise ValueError("Summary line numbers must be positive (1-indexed)")
        if self.source_start > self.source_end:
            raise ValueError("Source start line must be <= end line")
        if self.summary_start > self.summary_end:
            raise ValueError("Summary start line must be <= end line")
    
    def contains_source_line(self, line: int) -> bool:
        """Check if a source line number falls within this node's range."""
        return self.source_start <= line <= self.source_end
    
    def contains_summary_line(self, line: int) -> bool:
        """Check if a summary line number falls within this node's range."""
        return self.summary_start <= line <= self.summary_end
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert the node to a dictionary representation."""
        return asdict(self)


class SourceMap:
    """
    Container for managing bidirectional mappings between source and summary content.
    
    This class provides efficient lookup capabilities for finding corresponding
    content between original source and its compressed/summarized versions.
    """
    
    def __init__(self, nodes: Optional[List[MappedNode]] = None):
        """
        Initialize the SourceMap with optional nodes.
        
        Args:
            nodes: List of MappedNode objects to initialize the map with
        """
        self.nodes: List[MappedNode] = nodes or []
        self._validate_nodes()
    
    def _validate_nodes(self):
        """Validate that nodes don't have overlapping ranges."""
        # Sort nodes by source_start for validation
        sorted_nodes = sorted(self.nodes, key=lambda n: n.source_start)
        
        for i in range(len(sorted_nodes) - 1):
            current = sorted_nodes[i]
            next_node = sorted_nodes[i + 1]
            
            # Check for overlapping source ranges
            if current.source_end >= next_node.source_start:
                raise ValueError(
                    f"Overlapping source ranges detected: "
                    f"{current.name} ({current.source_start}-{current.source_end}) "
                    f"overlaps with {next_node.name} ({next_node.source_start}-{next_node.source_end})"
                )
        
        # Sort nodes by summary_start for validation
        sorted_summary_nodes = sorted(self.nodes, key=lambda n: n.summary_start)
        
        for i in range(len(sorted_summary_nodes) - 1):
            current = sorted_summary_nodes[i]
            next_node = sorted_summary_nodes[i + 1]
            
            # Check for overlapping summary ranges
            if current.summary_end >= next_node.summary_start:
                raise ValueError(
                    f"Overlapping summary ranges detected: "
                    f"{current.name} ({current.summary_start}-{current.summary_end}) "
                    f"overlaps with {next_node.name} ({next_node.summary_start}-{next_node.summary_end})"
                )
    
    def add_node(self, node: MappedNode):
        """
        Add a new node to the source map.
        
        Args:
            node: The MappedNode to add
            
        Raises:
            ValueError: If the node creates overlapping ranges
        """
        # Temporarily add the node to validate
        temp_nodes = self.nodes + [node]
        temp_map = SourceMap(temp_nodes)
        
        # If validation passes, add the node
        self.nodes.append(node)
    
    def find_summary_for_source_line(self, line: int) -> Optional[MappedNode]:
        """
        Find the mapped node that contains the given source line number.
        
        Args:
            line: Source line number to look up (1-indexed)
            
        Returns:
            MappedNode if found, None otherwise
        """
        for node in self.nodes:
            if node.contains_source_line(line):
                return node
        return None
    
    def find_source_for_summary_line(self, line: int) -> Optional[MappedNode]:
        """
        Find the mapped node that contains the given summary line number.
        
        Args:
            line: Summary line number to look up (1-indexed)
            
        Returns:
            MappedNode if found, None otherwise
        """
        for node in self.nodes:
            if node.contains_summary_line(line):
                return node
        return None
    
    def get_summary_line_for_source_line(self, source_line: int) -> Optional[int]:
        """
        Get the corresponding summary line number for a source line.
        
        This provides a proportional mapping within the found node's range.
        
        Args:
            source_line: Source line number (1-indexed)
            
        Returns:
            Corresponding summary line number, or None if not found
        """
        node = self.find_summary_for_source_line(source_line)
        if not node:
            return None
        
        # Calculate proportional position within the node
        source_offset = source_line - node.source_start
        source_range = node.source_end - node.source_start
        summary_range = node.summary_end - node.summary_start
        
        if source_range == 0:
            return node.summary_start
        
        # Proportional mapping
        summary_offset = int((source_offset / source_range) * summary_range)
        return node.summary_start + summary_offset
    
    def get_source_line_for_summary_line(self, summary_line: int) -> Optional[int]:
        """
        Get the corresponding source line number for a summary line.
        
        This provides a proportional mapping within the found node's range.
        
        Args:
            summary_line: Summary line number (1-indexed)
            
        Returns:
            Corresponding source line number, or None if not found
        """
        node = self.find_source_for_summary_line(summary_line)
        if not node:
            return None
        
        # Calculate proportional position within the node
        summary_offset = summary_line - node.summary_start
        summary_range = node.summary_end - node.summary_start
        source_range = node.source_end - node.source_start
        
        if summary_range == 0:
            return node.source_start
        
        # Proportional mapping
        source_offset = int((summary_offset / summary_range) * source_range)
        return node.source_start + source_offset
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the SourceMap to a dictionary representation.
        
        Returns:
            Dictionary containing the source map data
        """
        return {
            'nodes': [node.to_dict() for node in self.nodes],
            'node_count': len(self.nodes)
        }
    
    def to_json(self, indent: Optional[int] = None) -> str:
        """
        Convert the SourceMap to a JSON string.
        
        Args:
            indent: Number of spaces for JSON indentation (None for compact)
            
        Returns:
            JSON string representation of the source map
        """
        return json.dumps(self.to_dict(), indent=indent)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SourceMap':
        """
        Create a SourceMap from a dictionary representation.
        
        Args:
            data: Dictionary containing source map data
            
        Returns:
            SourceMap instance
        """
        nodes = [MappedNode(**node_data) for node_data in data.get('nodes', [])]
        return cls(nodes)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'SourceMap':
        """
        Create a SourceMap from a JSON string.
        
        Args:
            json_str: JSON string containing source map data
            
        Returns:
            SourceMap instance
        """
        data = json.loads(json_str)
        return cls.from_dict(data)
    
    def get_nodes_by_type(self, node_type: str) -> List[MappedNode]:
        """
        Get all nodes of a specific type.
        
        Args:
            node_type: The type of nodes to filter by
            
        Returns:
            List of nodes matching the specified type
        """
        return [node for node in self.nodes if node.type == node_type]
    
    def get_coverage_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the mapping coverage.
        
        Returns:
            Dictionary containing coverage statistics
        """
        if not self.nodes:
            return {
                'total_nodes': 0,
                'source_lines_covered': 0,
                'summary_lines_covered': 0,
                'node_types': {}
            }
        
        source_lines = set()
        summary_lines = set()
        node_types = {}
        
        for node in self.nodes:
            # Count covered lines
            source_lines.update(range(node.source_start, node.source_end + 1))
            summary_lines.update(range(node.summary_start, node.summary_end + 1))
            
            # Count node types
            node_types[node.type] = node_types.get(node.type, 0) + 1
        
        return {
            'total_nodes': len(self.nodes),
            'source_lines_covered': len(source_lines),
            'summary_lines_covered': len(summary_lines),
            'node_types': node_types
        }
    
    def __len__(self) -> int:
        """Return the number of nodes in the source map."""
        return len(self.nodes)
    
    def __iter__(self):
        """Iterate over the nodes in the source map."""
        return iter(self.nodes)
    
    def __repr__(self) -> str:
        """String representation of the SourceMap."""
        return f"SourceMap(nodes={len(self.nodes)})"
