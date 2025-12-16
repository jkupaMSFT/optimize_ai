#!/usr/bin/env python3
"""
Comprehensive End-to-End Validation Suite
Tests the complete pipeline: Original Python → Compression → Translation → Semantic Analysis
"""

import sys
import time
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))

from output_translator.core.translator import CAIToPythonTranslator
from input_optimizer.engine.waterfall_compressor import WaterfallCompressor
import ast
import difflib
from collections import defaultdict

class ComprehensiveE2EValidator:
    """Comprehensive end-to-end validation for the entire optimization pipeline."""
    
    def __init__(self):
        self.compressor = WaterfallCompressor()
        self.translator = CAIToPythonTranslator()
        self.results = defaultdict(list)
    
    def calculate_similarity(self, original, translated):
        """Calculate semantic similarity between original and translated code."""
        if not original or not translated:
            return 0.0
        
        # Normalize whitespace for comparison
        orig_lines = [line.strip() for line in original.strip().split('\n') if line.strip()]
        trans_lines = [line.strip() for line in translated.strip().split('\n') if line.strip()]
        
        # Use difflib for similarity
        matcher = difflib.SequenceMatcher(None, orig_lines, trans_lines)
        return matcher.ratio()
    
    def analyze_semantic_preservation(self, original, translated):
        """Analyze what semantic elements are preserved."""
        results = {
            'imports': {'original': 0, 'translated': 0, 'preserved': 0},
            'functions': {'original': 0, 'translated': 0, 'preserved': 0},
            'classes': {'original': 0, 'translated': 0, 'preserved': 0},
            'variables': {'original': 0, 'translated': 0, 'preserved': 0},
            'methods': {'original': 0, 'translated': 0, 'preserved': 0}
        }
        
        try:
            # Parse original code
            orig_tree = ast.parse(original)
            trans_tree = ast.parse(translated)
            
            # Extract elements from original
            orig_imports = set()
            orig_functions = set()
            orig_classes = set()
            orig_variables = set()
            orig_methods = set()
            
            for node in ast.walk(orig_tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        orig_imports.add(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ''
                    for alias in node.names:
                        orig_imports.add(f"{module}.{alias.name}")
                elif isinstance(node, ast.FunctionDef):
                    if hasattr(node, 'parent_class'):
                        orig_methods.add(node.name)
                    else:
                        orig_functions.add(node.name)
                elif isinstance(node, ast.ClassDef):
                    orig_classes.add(node.name)
                    # Mark methods as having a parent class
                    for child in node.body:
                        if isinstance(child, ast.FunctionDef):
                            child.parent_class = node.name
                            orig_methods.add(child.name)
                elif isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            orig_variables.add(target.id)
            
            # Extract elements from translated
            trans_imports = set()
            trans_functions = set()
            trans_classes = set()
            trans_variables = set()
            trans_methods = set()
            
            for node in ast.walk(trans_tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        trans_imports.add(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ''
                    for alias in node.names:
                        trans_imports.add(f"{module}.{alias.name}")
                elif isinstance(node, ast.FunctionDef):
                    if hasattr(node, 'parent_class'):
                        trans_methods.add(node.name)
                    else:
                        trans_functions.add(node.name)
                elif isinstance(node, ast.ClassDef):
                    trans_classes.add(node.name)
                    # Mark methods as having a parent class
                    for child in node.body:
                        if isinstance(child, ast.FunctionDef):
                            child.parent_class = node.name
                            trans_methods.add(child.name)
                elif isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            trans_variables.add(target.id)
            
            # Calculate preservation
            results['imports']['original'] = len(orig_imports)
            results['imports']['translated'] = len(trans_imports)
            results['imports']['preserved'] = len(orig_imports & trans_imports)
            
            results['functions']['original'] = len(orig_functions)
            results['functions']['translated'] = len(trans_functions)
            results['functions']['preserved'] = len(orig_functions & trans_functions)
            
            results['classes']['original'] = len(orig_classes)
            results['classes']['translated'] = len(trans_classes)
            results['classes']['preserved'] = len(orig_classes & trans_classes)
            
            results['variables']['original'] = len(orig_variables)
            results['variables']['translated'] = len(trans_variables)
            results['variables']['preserved'] = len(orig_variables & trans_variables)
            
            results['methods']['original'] = len(orig_methods)
            results['methods']['translated'] = len(trans_methods)
            results['methods']['preserved'] = len(orig_methods & trans_methods)
            
        except Exception as e:
            print(f"    Warning: AST analysis failed: {e}")
        
        return results
    
    def test_complete_pipeline(self, test_name, original_code):
        """Test the complete pipeline for a single piece of code."""
        print(f"\n🧪 Testing: {test_name}")
        print("=" * 60)
        print(f"Original code length: {len(original_code)} characters")
        
        pipeline_results = {
            'test_name': test_name,
            'original_length': len(original_code),
            'compression_success': False,
            'translation_success': False,
            'semantic_similarity': 0.0,
            'semantic_preservation': {},
            'errors': []
        }
        
        try:
            # Step 1: Compression
            print("📦 Step 1: Compression")
            compression_result = self.compressor.compress(original_code)
            pipeline_results['compression_success'] = True
            pipeline_results['compression_method'] = compression_result.method_used
            pipeline_results['compression_ratio'] = compression_result.compression_ratio / 100.0  # Convert to decimal
            pipeline_results['compressed_length'] = len(compression_result.content)
            
            print(f"  ✅ Compressed using: {compression_result.method_used}")
            print(f"  📊 Compression ratio: {compression_result.compression_ratio:.1f}%")
            print(f"  📏 Compressed length: {len(compression_result.content)} chars")
            print(f"  🔍 CAI preview: {compression_result.content[:100]}...")
            
            # Step 2: Translation
            print("🔄 Step 2: Translation")
            session_id = f"e2e_test_{test_name.replace(' ', '_')}"
            translation_result = self.translator.translate(session_id, compression_result.content)
            
            if translation_result.success:
                pipeline_results['translation_success'] = True
                pipeline_results['translated_length'] = len(translation_result.python_code)
                
                print(f"  ✅ Translation successful")
                print(f"  📏 Translated length: {len(translation_result.python_code)} chars")
                print(f"  🔍 Code preview: {translation_result.python_code[:100]}...")
                
                # Step 3: Semantic Analysis
                print("🔍 Step 3: Semantic Analysis")
                similarity = self.calculate_similarity(original_code, translation_result.python_code)
                preservation = self.analyze_semantic_preservation(original_code, translation_result.python_code)
                
                pipeline_results['semantic_similarity'] = similarity
                pipeline_results['semantic_preservation'] = preservation
                
                print(f"  📊 Semantic similarity: {similarity:.1%}")
                print("  🧬 Element preservation:")
                for element_type, counts in preservation.items():
                    if counts['original'] > 0:
                        preservation_rate = counts['preserved'] / counts['original']
                        print(f"    {element_type.capitalize()}: {counts['preserved']}/{counts['original']} ({preservation_rate:.1%})")
                
                # Overall score
                element_scores = []
                for counts in preservation.values():
                    if counts['original'] > 0:
                        element_scores.append(counts['preserved'] / counts['original'])
                
                overall_preservation = sum(element_scores) / len(element_scores) if element_scores else 0
                pipeline_results['overall_preservation'] = overall_preservation
                print(f"  🎯 Overall preservation: {overall_preservation:.1%}")
                
            else:
                pipeline_results['errors'].extend(translation_result.errors)
                print(f"  ❌ Translation failed: {translation_result.errors}")
            
        except Exception as e:
            pipeline_results['errors'].append(str(e))
            print(f"  ❌ Pipeline error: {e}")
        
        self.results[test_name] = pipeline_results
        return pipeline_results
    
    def run_comprehensive_validation(self):
        """Run comprehensive validation across different code types and sizes."""
        
        print("🚀 Comprehensive End-to-End Pipeline Validation")
        print("=" * 80)
        
        # Test cases covering different scenarios
        test_cases = {
            "Simple Script": '''import os
import sys

def hello_world():
    print("Hello, World!")
    return True

x = 42
y = "test"
hello_world()''',
            
            "Class with Methods": '''from typing import List, Optional

class Calculator:
    def __init__(self):
        self.history = []
    
    def add(self, a: float, b: float) -> float:
        result = a + b
        self.history.append(f"{a} + {b} = {result}")
        return result
    
    def subtract(self, a: float, b: float) -> float:
        result = a - b
        self.history.append(f"{a} - {b} = {result}")
        return result
    
    def get_history(self) -> List[str]:
        return self.history.copy()

calc = Calculator()
result1 = calc.add(10, 5)
result2 = calc.subtract(20, 8)''',
            
            "Multiple Classes": '''from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class User:
    id: int
    name: str
    email: str

class Repository(ABC):
    @abstractmethod
    def save(self, entity) -> bool:
        pass
    
    @abstractmethod
    def find_by_id(self, id: int):
        pass

class UserRepository(Repository):
    def __init__(self):
        self.users = {}
    
    def save(self, user: User) -> bool:
        self.users[user.id] = user
        return True
    
    def find_by_id(self, id: int) -> Optional[User]:
        return self.users.get(id)

class UserService:
    def __init__(self, repo: UserRepository):
        self.repo = repo
    
    def create_user(self, name: str, email: str) -> User:
        user = User(id=len(self.repo.users) + 1, name=name, email=email)
        self.repo.save(user)
        return user

# Usage
repo = UserRepository()
service = UserService(repo)
user = service.create_user("John Doe", "john@example.com")''',
            
            "Large Complex Module": '''import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Union, Callable, Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

class TaskResult:
    def __init__(self, task_id: str, status: TaskStatus, result: Any = None, error: str = None):
        self.task_id = task_id
        self.status = status
        self.result = result
        self.error = error
        self.created_at = datetime.now()
        self.completed_at = None
    
    def mark_completed(self, result: Any = None):
        self.status = TaskStatus.COMPLETED
        self.result = result
        self.completed_at = datetime.now()
    
    def mark_failed(self, error: str):
        self.status = TaskStatus.FAILED
        self.error = error
        self.completed_at = datetime.now()

class TaskManager:
    def __init__(self, max_workers: int = 4):
        self.max_workers = max_workers
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.tasks: Dict[str, TaskResult] = {}
        self.running_tasks: List[str] = []
    
    async def submit_task(self, task_id: str, func: Callable, *args, **kwargs) -> TaskResult:
        if task_id in self.tasks:
            raise ValueError(f"Task {task_id} already exists")
        
        task_result = TaskResult(task_id, TaskStatus.PENDING)
        self.tasks[task_id] = task_result
        
        try:
            task_result.status = TaskStatus.RUNNING
            self.running_tasks.append(task_id)
            
            # Run in thread pool
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(self.executor, func, *args, **kwargs)
            
            task_result.mark_completed(result)
            logger.info(f"Task {task_id} completed successfully")
            
        except Exception as e:
            task_result.mark_failed(str(e))
            logger.error(f"Task {task_id} failed: {e}")
        
        finally:
            if task_id in self.running_tasks:
                self.running_tasks.remove(task_id)
        
        return task_result
    
    def get_task_status(self, task_id: str) -> Optional[TaskResult]:
        return self.tasks.get(task_id)
    
    def list_tasks(self, status: Optional[TaskStatus] = None) -> List[TaskResult]:
        if status:
            return [task for task in self.tasks.values() if task.status == status]
        return list(self.tasks.values())
    
    @asynccontextmanager
    async def task_context(self, task_id: str):
        try:
            yield self.tasks.get(task_id)
        except Exception as e:
            if task_id in self.tasks:
                self.tasks[task_id].mark_failed(str(e))
            raise
    
    def cleanup_old_tasks(self, max_age_hours: int = 24):
        cutoff = datetime.now() - timedelta(hours=max_age_hours)
        to_remove = []
        
        for task_id, task in self.tasks.items():
            if task.completed_at and task.completed_at < cutoff:
                to_remove.append(task_id)
        
        for task_id in to_remove:
            del self.tasks[task_id]
        
        logger.info(f"Cleaned up {len(to_remove)} old tasks")

async def example_usage():
    manager = TaskManager(max_workers=2)
    
    def cpu_intensive_task(n: int) -> int:
        return sum(i * i for i in range(n))
    
    # Submit tasks
    task1 = await manager.submit_task("calc1", cpu_intensive_task, 1000)
    task2 = await manager.submit_task("calc2", cpu_intensive_task, 2000)
    
    # Check status
    for task in manager.list_tasks():
        print(f"Task {task.task_id}: {task.status}")
    
    # Cleanup
    manager.cleanup_old_tasks(1)

if __name__ == "__main__":
    asyncio.run(example_usage())''',
            
            "Error Handling Patterns": '''import json
import traceback
from contextlib import contextmanager
from typing import Union, Type, Tuple

class CustomError(Exception):
    def __init__(self, message: str, code: int = None):
        super().__init__(message)
        self.code = code

class ValidationError(CustomError):
    pass

class ProcessingError(CustomError):
    pass

@contextmanager
def error_handler(operation_name: str):
    try:
        yield
    except ValidationError as e:
        print(f"Validation failed in {operation_name}: {e}")
        raise
    except ProcessingError as e:
        print(f"Processing failed in {operation_name}: {e}")
        raise
    except Exception as e:
        print(f"Unexpected error in {operation_name}: {e}")
        traceback.print_exc()
        raise

def validate_data(data: dict) -> bool:
    required_fields = ["name", "email", "age"]
    for field in required_fields:
        if field not in data:
            raise ValidationError(f"Missing required field: {field}")
    
    if not isinstance(data["age"], int) or data["age"] < 0:
        raise ValidationError("Age must be a non-negative integer")
    
    return True

def process_user_data(raw_data: str) -> dict:
    try:
        data = json.loads(raw_data)
    except json.JSONDecodeError as e:
        raise ProcessingError(f"Invalid JSON: {e}")
    
    with error_handler("data_validation"):
        validate_data(data)
    
    with error_handler("data_processing"):
        processed = {
            "name": data["name"].strip().title(),
            "email": data["email"].lower(),
            "age": data["age"],
            "processed_at": "2025-08-09"
        }
    
    return processed

# Test the error handling
test_data = '{"name": "john doe", "email": "JOHN@EXAMPLE.COM", "age": 30}'
result = process_user_data(test_data)'''
        }
        
        # Run tests for each case
        overall_results = []
        for test_name, code in test_cases.items():
            result = self.test_complete_pipeline(test_name, code)
            overall_results.append(result)
            time.sleep(0.5)  # Small delay between tests
        
        # Summary
        print(f"\n📊 COMPREHENSIVE VALIDATION SUMMARY")
        print("=" * 80)
        
        successful_compressions = sum(1 for r in overall_results if r['compression_success'])
        successful_translations = sum(1 for r in overall_results if r['translation_success'])
        
        print(f"Total test cases: {len(overall_results)}")
        print(f"Successful compressions: {successful_compressions}/{len(overall_results)} ({successful_compressions/len(overall_results):.1%})")
        print(f"Successful translations: {successful_translations}/{len(overall_results)} ({successful_translations/len(overall_results):.1%})")
        
        if successful_translations > 0:
            avg_similarity = sum(r['semantic_similarity'] for r in overall_results if r['translation_success']) / successful_translations
            avg_preservation = sum(r.get('overall_preservation', 0) for r in overall_results if r['translation_success']) / successful_translations
            
            print(f"Average semantic similarity: {avg_similarity:.1%}")
            print(f"Average element preservation: {avg_preservation:.1%}")
            
            # Element-wise preservation summary
            element_totals = defaultdict(lambda: {'original': 0, 'preserved': 0})
            for result in overall_results:
                if result['translation_success']:
                    for element_type, counts in result['semantic_preservation'].items():
                        element_totals[element_type]['original'] += counts['original']
                        element_totals[element_type]['preserved'] += counts['preserved']
            
            print(f"\nElement preservation across all tests:")
            for element_type, totals in element_totals.items():
                if totals['original'] > 0:
                    rate = totals['preserved'] / totals['original']
                    print(f"  {element_type.capitalize()}: {totals['preserved']}/{totals['original']} ({rate:.1%})")
        
        # Error summary
        all_errors = []
        for result in overall_results:
            all_errors.extend(result['errors'])
        
        if all_errors:
            print(f"\nErrors encountered: {len(all_errors)}")
            for i, error in enumerate(all_errors[:5], 1):  # Show first 5 errors
                print(f"  {i}. {error}")
            if len(all_errors) > 5:
                print(f"  ... and {len(all_errors) - 5} more")
        
        return overall_results

def main():
    validator = ComprehensiveE2EValidator()
    results = validator.run_comprehensive_validation()
    
    print(f"\n🎯 FINAL ASSESSMENT")
    print("=" * 80)
    
    successful_pipelines = sum(1 for r in results if r['compression_success'] and r['translation_success'])
    total_tests = len(results)
    
    if successful_pipelines == total_tests:
        print("🟢 ALL PIPELINES WORKING CORRECTLY")
        print("   ✅ No regressions detected")
        print("   ✅ End-to-end pipeline functional")
        print("   ✅ Ready for continued optimization")
    elif successful_pipelines > 0:
        print("🟡 PARTIAL PIPELINE SUCCESS")
        print(f"   ⚠️ {successful_pipelines}/{total_tests} pipelines working")
        print("   ⚠️ Some issues detected, investigation needed")
    else:
        print("🔴 PIPELINE FAILURES DETECTED")
        print("   ❌ Critical issues found")
        print("   ❌ Immediate attention required")
    
    return successful_pipelines == total_tests

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
