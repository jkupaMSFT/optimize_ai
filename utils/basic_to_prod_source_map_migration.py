"""
Migration utility for transitioning from basic to production mapping engine.

This utility helps migrate existing mappings and provides compatibility layers.
"""

import json
import logging
import sys
import os
from typing import List, Dict, Any, Optional
from dataclasses import asdict

# Add parent directory for imports when run as script
if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import both versions
try:
    from ..engine.mapping.source_map import MappedNode as BasicMappedNode, SourceMap as BasicSourceMap
    from ..engine.mapping.source_map_production import EnhancedMappedNode, ProductionSourceMap
except ImportError:
    # For standalone execution
    from input_optimizer.engine.mapping.source_map import MappedNode as BasicMappedNode, SourceMap as BasicSourceMap
    from input_optimizer.engine.mapping.source_map_production import EnhancedMappedNode, ProductionSourceMap

logger = logging.getLogger(__name__)


class MappingMigrator:
    """
    Utility for migrating from basic to production mapping engine.
    """
    
    @staticmethod
    def migrate_node(basic_node: BasicMappedNode) -> EnhancedMappedNode:
        """
        Migrate a basic MappedNode to EnhancedMappedNode.
        
        Args:
            basic_node: Basic MappedNode instance
            
        Returns:
            EnhancedMappedNode with equivalent data
        """
        # Get basic node data
        basic_data = basic_node.to_dict()
        
        # Create enhanced node with additional fields
        enhanced_node = EnhancedMappedNode(
            type=basic_data['type'],
            name=basic_data['name'],
            source_start=basic_data['source_start'],
            source_end=basic_data['source_end'],
            summary_start=basic_data['summary_start'],
            summary_end=basic_data['summary_end']
        )
        
        # Add migration metadata
        enhanced_node.add_metadata("migrated_from_basic", True)
        enhanced_node.add_metadata("migration_version", "1.0")
        
        logger.debug(f"Migrated node: {basic_node.name}")
        return enhanced_node
    
    @staticmethod
    def migrate_source_map(basic_map: BasicSourceMap, 
                          index_type: str = "auto",
                          thread_safe: bool = True) -> ProductionSourceMap:
        """
        Migrate a basic SourceMap to ProductionSourceMap.
        
        Args:
            basic_map: Basic SourceMap instance
            index_type: Index type for production map
            thread_safe: Enable thread safety
            
        Returns:
            ProductionSourceMap with migrated data
        """
        # Migrate all nodes
        enhanced_nodes = [
            MappingMigrator.migrate_node(node) 
            for node in basic_map.nodes
        ]
        
        # Create production source map
        production_map = ProductionSourceMap(
            enhanced_nodes,
            index_type=index_type,
            thread_safe=thread_safe
        )
        
        logger.info(f"Migrated SourceMap with {len(enhanced_nodes)} nodes")
        return production_map
    
    @staticmethod
    def migrate_json_file(input_file: str, 
                         output_file: str,
                         index_type: str = "auto") -> bool:
        """
        Migrate a JSON file from basic to production format.
        
        Args:
            input_file: Path to basic format JSON file
            output_file: Path for production format JSON file
            index_type: Index type for production map
            
        Returns:
            True if migration successful, False otherwise
        """
        try:
            # Load basic format
            with open(input_file, 'r') as f:
                basic_data = json.load(f)
            
            # Create basic source map
            basic_map = BasicSourceMap.from_dict(basic_data)
            
            # Migrate to production
            production_map = MappingMigrator.migrate_source_map(
                basic_map, 
                index_type=index_type
            )
            
            # Save production format
            with open(output_file, 'w') as f:
                f.write(production_map.to_json(indent=2))
            
            logger.info(f"Successfully migrated {input_file} to {output_file}")
            return True
            
        except Exception as e:
            logger.error(f"Migration failed: {e}")
            return False
    
    @staticmethod
    def create_compatibility_wrapper(production_map: ProductionSourceMap) -> 'CompatibilitySourceMap':
        """
        Create a compatibility wrapper that provides the basic SourceMap interface.
        
        Args:
            production_map: ProductionSourceMap instance
            
        Returns:
            CompatibilitySourceMap wrapper
        """
        return CompatibilitySourceMap(production_map)


class CompatibilitySourceMap:
    """
    Compatibility wrapper that provides BasicSourceMap interface over ProductionSourceMap.
    
    This allows existing code to work with the production engine without changes.
    """
    
    def __init__(self, production_map: ProductionSourceMap):
        """
        Initialize wrapper around production map.
        
        Args:
            production_map: The underlying ProductionSourceMap
        """
        self._production_map = production_map
    
    @property
    def nodes(self) -> List[BasicMappedNode]:
        """Get nodes in basic format."""
        basic_nodes = []
        for enhanced_node in self._production_map.nodes:
            # Convert enhanced node to basic node
            basic_node = BasicMappedNode(
                type=enhanced_node.type,
                name=enhanced_node.name,
                source_start=enhanced_node.source_start,
                source_end=enhanced_node.source_end,
                summary_start=enhanced_node.summary_start,
                summary_end=enhanced_node.summary_end
            )
            basic_nodes.append(basic_node)
        return basic_nodes
    
    def add_node(self, node: BasicMappedNode):
        """Add a basic node (converted to enhanced)."""
        enhanced_node = MappingMigrator.migrate_node(node)
        self._production_map.add_node(enhanced_node)
    
    def find_summary_for_source_line(self, line: int) -> Optional[BasicMappedNode]:
        """Find node for source line (returns basic format)."""
        enhanced_node = self._production_map.find_summary_for_source_line(line)
        if not enhanced_node:
            return None
        
        return BasicMappedNode(
            type=enhanced_node.type,
            name=enhanced_node.name,
            source_start=enhanced_node.source_start,
            source_end=enhanced_node.source_end,
            summary_start=enhanced_node.summary_start,
            summary_end=enhanced_node.summary_end
        )
    
    def find_source_for_summary_line(self, line: int) -> Optional[BasicMappedNode]:
        """Find node for summary line (returns basic format)."""
        enhanced_node = self._production_map.find_source_for_summary_line(line)
        if not enhanced_node:
            return None
        
        return BasicMappedNode(
            type=enhanced_node.type,
            name=enhanced_node.name,
            source_start=enhanced_node.source_start,
            source_end=enhanced_node.source_end,
            summary_start=enhanced_node.summary_start,
            summary_end=enhanced_node.summary_end
        )
    
    def get_summary_line_for_source_line(self, source_line: int) -> Optional[int]:
        """Get summary line for source line."""
        return self._production_map.get_summary_line_for_source_line(source_line)
    
    def get_source_line_for_summary_line(self, summary_line: int) -> Optional[int]:
        """Get source line for summary line."""
        return self._production_map.get_source_line_for_summary_line(summary_line)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to basic format dictionary."""
        return {
            'nodes': [node.to_dict() for node in self.nodes],
            'node_count': len(self.nodes)
        }
    
    def to_json(self, indent: Optional[int] = None) -> str:
        """Convert to basic format JSON."""
        return json.dumps(self.to_dict(), indent=indent)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CompatibilitySourceMap':
        """Create from basic format dictionary."""
        basic_map = BasicSourceMap.from_dict(data)
        production_map = MappingMigrator.migrate_source_map(basic_map)
        return cls(production_map)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'CompatibilitySourceMap':
        """Create from basic format JSON."""
        basic_map = BasicSourceMap.from_json(json_str)
        production_map = MappingMigrator.migrate_source_map(basic_map)
        return cls(production_map)
    
    def __len__(self) -> int:
        """Get number of nodes."""
        return len(self._production_map)
    
    def __iter__(self):
        """Iterate over basic format nodes."""
        return iter(self.nodes)
    
    def __repr__(self) -> str:
        """String representation."""
        return f"CompatibilitySourceMap(nodes={len(self)})"
    
    # Production features accessible through wrapper
    def get_production_metrics(self) -> Dict[str, Any]:
        """Access production-only metrics."""
        return self._production_map.get_metrics()
    
    def get_enhanced_nodes(self) -> List[EnhancedMappedNode]:
        """Access enhanced nodes directly."""
        return self._production_map.nodes


def demonstrate_migration():
    """Demonstrate migration from basic to production mapping."""
    print("Migration Demonstration")
    print("=" * 50)
    
    # Create basic mapping
    basic_nodes = [
        BasicMappedNode("function", "calc", 1, 10, 1, 3),
        BasicMappedNode("class", "Processor", 15, 45, 5, 12),
    ]
    basic_map = BasicSourceMap(basic_nodes)
    
    print(f"Basic map nodes: {len(basic_map)}")
    print(f"Basic node type: {type(basic_map.nodes[0])}")
    
    # Migrate to production
    production_map = MappingMigrator.migrate_source_map(basic_map)
    
    print(f"Production map nodes: {len(production_map)}")
    print(f"Enhanced node type: {type(production_map.nodes[0])}")
    print(f"Enhanced node metadata: {production_map.nodes[0].metadata}")
    
    # Use compatibility wrapper
    compat_map = MappingMigrator.create_compatibility_wrapper(production_map)
    
    print(f"Compatibility map nodes: {len(compat_map)}")
    print(f"Compatibility node type: {type(compat_map.nodes[0])}")
    
    # Test functionality
    basic_result = compat_map.find_summary_for_source_line(5)
    print(f"Lookup result: {basic_result.name if basic_result else 'None'}")
    
    # Access production features
    metrics = compat_map.get_production_metrics()
    print(f"Production metrics available: {bool(metrics)}")
    
    print("\nMigration completed successfully!")


if __name__ == "__main__":
    demonstrate_migration()
