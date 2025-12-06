"""
Example large Python module for demo purposes.
This module demonstrates various Python constructs that will be compressed.
"""
import os
import sys
import json
import logging
from typing import List, Dict, Optional, Union
from dataclasses import dataclass
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class DataRecord:
    """A data record with various fields."""
    id: int
    name: str
    value: float
    metadata: Dict[str, str]
    active: bool = True
    
    def __post_init__(self):
        """Validate the data record after initialization."""
        if self.value < 0:
            raise ValueError("Value must be non-negative")
        if not self.name.strip():
            raise ValueError("Name cannot be empty")

class DataProcessor:
    """A comprehensive data processor with multiple processing strategies."""
    
    def __init__(self, config_path: Optional[Path] = None):
        """Initialize the data processor with optional configuration."""
        self.config = self._load_config(config_path)
        self.processed_count = 0
        self.error_count = 0
        self.cache = {}
        
    def _load_config(self, config_path: Optional[Path]) -> Dict:
        """Load configuration from file or use defaults."""
        if config_path and config_path.exists():
            try:
                with open(config_path, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Failed to load config from {config_path}: {e}")
        
        return {
            'batch_size': 100,
            'max_retries': 3,
            'timeout': 30,
            'enable_cache': True,
            'output_format': 'json'
        }
    
    def process_single_record(self, record: DataRecord) -> Dict:
        """Process a single data record."""
        try:
            # Simulate complex processing
            result = {
                'id': record.id,
                'processed_name': record.name.upper().strip(),
                'computed_value': record.value * 2.5,
                'metadata_count': len(record.metadata),
                'processing_timestamp': self._get_timestamp()
            }
            
            # Apply custom transformations based on metadata
            if 'priority' in record.metadata:
                result['priority_score'] = self._calculate_priority_score(record)
            
            if 'category' in record.metadata:
                result['category_normalized'] = self._normalize_category(record.metadata['category'])
            
            self.processed_count += 1
            return result
            
        except Exception as e:
            logger.error(f"Error processing record {record.id}: {e}")
            self.error_count += 1
            return {'id': record.id, 'error': str(e)}
    
    def process_batch(self, records: List[DataRecord]) -> List[Dict]:
        """Process a batch of records with error handling."""
        results = []
        batch_size = self.config['batch_size']
        
        for i in range(0, len(records), batch_size):
            batch = records[i:i + batch_size]
            logger.info(f"Processing batch {i//batch_size + 1}, size: {len(batch)}")
            
            for record in batch:
                if self.config['enable_cache'] and record.id in self.cache:
                    results.append(self.cache[record.id])
                else:
                    result = self.process_single_record(record)
                    if self.config['enable_cache']:
                        self.cache[record.id] = result
                    results.append(result)
        
        return results
    
    def _calculate_priority_score(self, record: DataRecord) -> float:
        """Calculate priority score based on various factors."""
        base_score = record.value
        priority_multiplier = {
            'high': 2.0,
            'medium': 1.5,
            'low': 1.0
        }.get(record.metadata.get('priority', 'medium'), 1.0)
        
        return base_score * priority_multiplier
    
    def _normalize_category(self, category: str) -> str:
        """Normalize category names."""
        category_mapping = {
            'cat1': 'Category A',
            'cat2': 'Category B',
            'cat3': 'Category C'
        }
        return category_mapping.get(category.lower(), category.title())
    
    def _get_timestamp(self) -> str:
        """Get current timestamp as string."""
        import datetime
        return datetime.datetime.now().isoformat()
    
    def export_results(self, results: List[Dict], output_path: Path) -> None:
        """Export processing results to file."""
        try:
            if self.config['output_format'] == 'json':
                with open(output_path, 'w') as f:
                    json.dump(results, f, indent=2)
            else:
                # CSV export
                import csv
                if results:
                    fieldnames = results[0].keys()
                    with open(output_path, 'w', newline='') as f:
                        writer = csv.DictWriter(f, fieldnames=fieldnames)
                        writer.writeheader()
                        writer.writerows(results)
            
            logger.info(f"Results exported to {output_path}")
            
        except Exception as e:
            logger.error(f"Failed to export results: {e}")
            raise

def create_sample_data(count: int = 50) -> List[DataRecord]:
    """Create sample data records for testing."""
    import random
    
    names = ['Alice', 'Bob', 'Charlie', 'Diana', 'Eve', 'Frank', 'Grace', 'Henry']
    categories = ['cat1', 'cat2', 'cat3']
    priorities = ['high', 'medium', 'low']
    
    records = []
    for i in range(count):
        record = DataRecord(
            id=i + 1,
            name=random.choice(names),
            value=random.uniform(10.0, 1000.0),
            metadata={
                'category': random.choice(categories),
                'priority': random.choice(priorities),
                'source': f'system_{random.randint(1, 5)}'
            },
            active=random.choice([True, True, True, False])  # 75% active
        )
        records.append(record)
    
    return records

def main():
    """Main execution function."""
    logger.info("Starting data processing demo")
    
    # Create processor
    processor = DataProcessor()
    
    # Generate sample data
    sample_records = create_sample_data(100)
    logger.info(f"Generated {len(sample_records)} sample records")
    
    # Process the data
    results = processor.process_batch(sample_records)
    
    # Export results
    output_path = Path("processing_results.json")
    processor.export_results(results, output_path)
    
    # Print summary
    print(f"Processing complete!")
    print(f"Records processed: {processor.processed_count}")
    print(f"Errors encountered: {processor.error_count}")
    print(f"Results saved to: {output_path}")

if __name__ == "__main__":
    main()
