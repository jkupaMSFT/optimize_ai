# Mapping Engine

A robust data model and mapping engine for tracking bidirectional relationships between source content and its compressed/optimized versions.

## Overview

The mapping engine provides:

- **MappedNode**: A data model representing relationships between source and summary content
- **SourceMap**: A container for managing bidirectional mappings with efficient lookup capabilities
- **Full metadata tracking**: Source/summary line ranges, node types, and names
- **Serialization support**: JSON export/import for persistence
- **Validation**: Overlap detection and error handling

## Core Components

### MappedNode

A dataclass representing a mapped relationship between source and summary content.

```python
@dataclass
class MappedNode:
    type: str           # Type of content (e.g., 'function', 'class', 'comment')
    name: str           # Human-readable identifier
    source_start: int   # Starting line in source (1-indexed)
    source_end: int     # Ending line in source (1-indexed)
    summary_start: int  # Starting line in summary (1-indexed)
    summary_end: int    # Ending line in summary (1-indexed)
```

**Key Features:**

- Automatic validation of line number ranges
- Contains methods for checking line membership
- Dictionary serialization support

### SourceMap

A container for managing collections of MappedNodes with bidirectional lookup capabilities.

**Key Methods:**

- `add_node(node)` - Add a new mapping node with overlap validation
- `find_summary_for_source_line(line)` - Find node containing source line
- `find_source_for_summary_line(line)` - Find node containing summary line
- `get_summary_line_for_source_line(line)` - Get proportional summary line mapping
- `get_source_line_for_summary_line(line)` - Get proportional source line mapping
- `to_dict()` / `to_json()` - Serialization methods
- `from_dict()` / `from_json()` - Deserialization class methods

## Usage Examples

### Basic Usage

```python
from engine.mapping import MappedNode, SourceMap

# Create mapping nodes
nodes = [
    MappedNode("function", "main", 1, 10, 1, 3),
    MappedNode("class", "Calculator", 15, 45, 5, 12),
    MappedNode("comment", "header", 50, 55, 15, 16),
]

# Create source map
source_map = SourceMap(nodes)

# Bidirectional lookups
node = source_map.find_summary_for_source_line(25)  # Find node containing source line 25
summary_line = source_map.get_summary_line_for_source_line(25)  # Get corresponding summary line

node = source_map.find_source_for_summary_line(8)  # Find node containing summary line 8
source_line = source_map.get_source_line_for_summary_line(8)  # Get corresponding source line
```

### Serialization

```python
# Export to JSON
json_data = source_map.to_json(indent=2)

# Import from JSON
restored_map = SourceMap.from_json(json_data)

# Export to dictionary
map_dict = source_map.to_dict()

# Import from dictionary
restored_map = SourceMap.from_dict(map_dict)
```

### Statistics and Analysis

```python
# Get coverage statistics
stats = source_map.get_coverage_stats()
print(f"Total nodes: {stats['total_nodes']}")
print(f"Source lines covered: {stats['source_lines_covered']}")
print(f"Node types: {stats['node_types']}")

# Filter by type
functions = source_map.get_nodes_by_type("function")
classes = source_map.get_nodes_by_type("class")
```

## Proportional Mapping

The engine provides proportional mapping within node ranges. For example, if a source function spans lines 10-20 and maps to summary lines 5-7, then:

- Source line 15 (middle of range) maps to summary line 6 (middle of range)
- Source line 12 (20% into range) maps proportionally to the summary range

This ensures accurate line-by-line correspondence even when content is significantly compressed.

## Error Handling

The mapping engine includes comprehensive validation:

- **Invalid line numbers**: Must be positive (1-indexed)
- **Invalid ranges**: Start line must be ≤ end line
- **Overlapping ranges**: Nodes cannot have overlapping source or summary ranges
- **Automatic validation**: Performed during node creation and map construction

## Integration Examples

### With Compression Pipeline

```python
def compress_with_mapping(source_code: str) -> Tuple[str, SourceMap]:
    """Compress code while building a source map."""

    # Parse source code structure
    functions = parse_functions(source_code)
    classes = parse_classes(source_code)

    # Compress content
    compressed_code = compress(source_code)

    # Build mapping nodes
    nodes = []
    for func in functions:
        compressed_func = find_compressed_function(func, compressed_code)
        node = MappedNode(
            type="function",
            name=func.name,
            source_start=func.start_line,
            source_end=func.end_line,
            summary_start=compressed_func.start_line,
            summary_end=compressed_func.end_line
        )
        nodes.append(node)

    return compressed_code, SourceMap(nodes)
```

### With IDE Integration

```python
def highlight_corresponding_lines(source_map: SourceMap, selected_line: int, view: str):
    """Highlight corresponding lines in the opposite view."""

    if view == "source":
        node = source_map.find_summary_for_source_line(selected_line)
        if node:
            summary_line = source_map.get_summary_line_for_source_line(selected_line)
            highlight_summary_line(summary_line)

    elif view == "summary":
        node = source_map.find_source_for_summary_line(selected_line)
        if node:
            source_line = source_map.get_source_line_for_summary_line(selected_line)
            highlight_source_line(source_line)
```

## File Structure

```
engine/mapping.py          # Main mapping engine implementation
test_mapping.py            # Comprehensive test suite
mapping_example.py         # Integration examples
```

## Testing

Run the test suite to verify functionality:

```bash
python test_mapping.py
```

The test suite covers:

- MappedNode creation and validation
- SourceMap operations and lookups
- Bidirectional mapping accuracy
- Serialization/deserialization
- Error handling and edge cases
- Performance with various data sizes

## Performance Characteristics

- **Lookup time**: O(n) where n is the number of nodes (suitable for typical use cases)
- **Memory usage**: Linear with number of nodes and their metadata
- **Validation time**: O(n log n) during map creation due to sorting for overlap detection

For large-scale applications, consider implementing indexed lookups or tree-based structures for O(log n) performance.

## Future Enhancements

Potential improvements for specific use cases:

- **Indexed lookups**: B-tree or interval tree for faster line lookups
- **Hierarchical mapping**: Support for nested node relationships
- **Delta tracking**: Track changes between mapping versions
- **Conflict resolution**: Handle ambiguous mappings in complex scenarios
- **Metadata extensibility**: Support for custom node metadata beyond the core fields
