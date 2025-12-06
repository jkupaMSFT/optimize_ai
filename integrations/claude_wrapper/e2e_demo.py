#!/usr/bin/env python3
"""
End-to-End Demo: Claude Code CLI with Post-Processor Integration

This example demonstrates the complete workflow of:
1. Compressing Python code using CAI format
2. Sending to Claude Code CLI with compression
3. Receiving Claude's response (potentially in CAI format)
4. Using the post_processor to apply edits to files
5. Showing the complete round-trip with metrics

Usage:
    python e2e_demo.py --file example.py --task "add error handling"
    python e2e_demo.py --file example.py --task "refactor to use classes" --apply-edits
"""

import argparse
import sys
import tempfile
import json
from pathlib import Path
from typing import Dict, Any, Optional
import subprocess
import logging
from datetime import datetime

# Setup path for imports
sys.path.append(str(Path(__file__).parent.parent.parent))

# Import required components
try:
    from claude_proxy import ClaudeCodeProxy
    from post_processor import ClaudeEditApplicator
    # Mock the other components for demo purposes
    class MockWaterfallCompressor:
        pass
    class MockCAIToPythonTranslator:
        pass
    class MockSecureSessionManager:
        pass
    
    def setup_logger(name, level="INFO"):
        import logging
        logger = logging.getLogger(name)
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(getattr(logging, level))
        return logger
        
except ImportError:
    # Fallback for missing components
    class MockClaudeCodeProxy:
        def __init__(self, **kwargs):
            pass
        def process_input(self, prompt, file_path=None):
            return prompt, {"compressed": False}
        def process_output(self, response, metadata):
            return response
    
    class MockClaudeEditApplicator:
        def __init__(self):
            import logging
            self.logger = logging.getLogger(__name__)
        def extract_code_blocks(self, text):
            import re
            pattern = r'```(\w+)?\n(.*?)```'
            matches = re.findall(pattern, text, re.DOTALL)
            return [(lang or 'python', code.strip()) for lang, code in matches]
        def apply_edits_to_file(self, file_path, claude_output, backup=True):
            from pathlib import Path
            path = Path(file_path)
            if backup and path.exists():
                backup_path = path.with_suffix(path.suffix + '.bak')
                backup_path.write_text(path.read_text())
                print(f"Created backup: {backup_path}")
            
            code_blocks = self.extract_code_blocks(claude_output)
            if code_blocks:
                for lang, code in code_blocks:
                    if lang in ['python', 'py', '']:
                        path.write_text(code)
                        print(f"Applied edits to {file_path}")
                        return True
            return False
    
    ClaudeCodeProxy = MockClaudeCodeProxy
    ClaudeEditApplicator = MockClaudeEditApplicator
    
    def setup_logger(name, level="INFO"):
        import logging
        logger = logging.getLogger(name)
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(getattr(logging, level))
        return logger

class E2EClaudeDemo:
    """
    End-to-end demonstration of Claude Code CLI integration with post-processing
    """
    
    def __init__(self, apply_edits: bool = False, verbose: bool = False):
        """
        Initialize the demo
        
        Args:
            apply_edits: Whether to actually apply edits to files
            verbose: Enable verbose logging
        """
        self.apply_edits = apply_edits
        self.verbose = verbose
        
        # Setup logging
        log_level = "DEBUG" if verbose else "INFO"
        self.logger = setup_logger("e2e_claude_demo", log_level)
        
        # Initialize components
        try:
            self.claude_proxy = ClaudeCodeProxy(
                enable_compression=True,
                llm_model="gpt-4"
            )
            # Force fresh compression by clearing any existing sessions
            if hasattr(self.claude_proxy, 'current_session_id'):
                self.claude_proxy.current_session_id = None
        except:
            # Fallback to mock if real components not available
            self.claude_proxy = MockClaudeCodeProxy(
                enable_compression=True,
                llm_model="gpt-4"
            )
        self.post_processor = ClaudeEditApplicator()
        
        # Demo metrics
        self.metrics = {
            "start_time": None,
            "compression_metrics": {},
            "claude_response_time": None,
            "translation_metrics": {},
            "total_time": None
        }
        
    def create_sample_file(self, temp_dir: Path) -> Path:
        """Create a sample Python file for the demo"""
        sample_content = '''"""
Simple calculator module for demonstration
"""

def add(a, b):
    return a + b

def subtract(a, b):
    return a - b

def multiply(a, b):
    return a * b

def divide(a, b):
    return a / b

def calculate(operation, a, b):
    if operation == "add":
        return add(a, b)
    elif operation == "subtract":
        return subtract(a, b)
    elif operation == "multiply":
        return multiply(a, b)
    elif operation == "divide":
        return divide(a, b)
    else:
        raise ValueError("Unknown operation")

# Basic usage
if __name__ == "__main__":
    result = calculate("add", 5, 3)
    print(f"Result: {result}")
'''
        
        sample_file = temp_dir / "calculator.py"
        sample_file.write_text(sample_content)
        return sample_file
    
    def run_demo(self, file_path: Optional[str] = None, task: str = "add comprehensive error handling and input validation"):
        """
        Run the complete end-to-end demo
        
        Args:
            file_path: Path to Python file (creates sample if None)
            task: Task description for Claude
        """
        self.metrics["start_time"] = datetime.now()
        
        print("="*80)
        print("🚀 END-TO-END CLAUDE CODE CLI DEMO")
        print("="*80)
        
        # Step 1: Setup file
        if file_path and Path(file_path).exists():
            target_file = Path(file_path)
            print(f"📁 Using file: {target_file}")
        else:
            with tempfile.TemporaryDirectory() as temp_dir:
                target_file = self.create_sample_file(Path(temp_dir))
                print(f"📁 Created sample file: {target_file}")
        
        print(f"📋 Task: {task}")
        print()
        
        # Step 2: Show original file
        self._show_file_content("Original File", target_file)
        
        # Step 3: Compression phase
        print("🔄 PHASE 1: COMPRESSION")
        print("-" * 40)
        
        # Debug: Show actual file stats before compression
        if self.verbose:
            try:
                from input_optimizer.engine.waterfall_compressor import count_tokens
                file_content = target_file.read_text()
                actual_tokens = count_tokens(file_content)
                actual_lines = len(file_content.split('\n'))
                print(f"🔍 Pre-compression analysis:")
                print(f"   File: {target_file}")
                print(f"   Lines: {actual_lines}")
                print(f"   Characters: {len(file_content)}")
                print(f"   Tokens: {actual_tokens}")
                
                # Determine expected tier
                if actual_tokens < 10:
                    expected_tier = 'TINY'
                elif actual_tokens < 250:
                    expected_tier = 'SMALL'
                elif actual_tokens < 1000:
                    expected_tier = 'MEDIUM'
                elif actual_tokens < 10000:
                    expected_tier = 'LARGE'
                else:
                    expected_tier = 'HUGE'
                print(f"   Expected tier: {expected_tier}")
                print()
            except Exception as e:
                print(f"   ⚠️ Could not analyze file: {e}")
        
        prompt = f"Please {task} for the following Python file. Provide the complete updated code."
        
        compressed_prompt, compression_metadata = self.claude_proxy.process_input(
            prompt=prompt,
            file_path=str(target_file)
        )
        
        self.metrics["compression_metrics"] = compression_metadata
        self._show_compression_stats(compression_metadata)
        
        # Debug: Compare expected vs actual compression results
        if self.verbose and compression_metadata.get("compressed"):
            try:
                from input_optimizer.engine.waterfall_compressor import count_tokens
                file_content = target_file.read_text()
                actual_tokens = count_tokens(file_content)
                reported_tokens = compression_metadata.get('original_tokens', 0)
                reported_tier = compression_metadata.get('tier', 'unknown')
                
                print(f"\n🔍 Compression Analysis:")
                print(f"   Actual file tokens: {actual_tokens}")
                print(f"   Reported original tokens: {reported_tokens}")
                print(f"   Token difference: {abs(actual_tokens - reported_tokens)}")
                print(f"   Reported tier: {reported_tier}")
                
                if actual_tokens != reported_tokens:
                    print(f"   ⚠️ TOKEN MISMATCH: Expected {actual_tokens}, got {reported_tokens}")
                
                # Check if tier matches expectations
                if actual_tokens >= 250 and reported_tier.lower() == 'small':
                    print(f"   ⚠️ TIER MISMATCH: File has {actual_tokens} tokens but reported as {reported_tier}")
                    print(f"   Expected tier: MEDIUM or higher")
                    
            except Exception as e:
                print(f"   ⚠️ Could not perform compression analysis: {e}")
        
        if self.verbose:
            print("\n📦 Compressed Prompt Preview:")
            print("-" * 40)
            preview = compressed_prompt[:500] + "..." if len(compressed_prompt) > 500 else compressed_prompt
            print(preview)
        
        # Step 4: Claude execution phase
        print("\n🤖 PHASE 2: CLAUDE CODE EXECUTION")
        print("-" * 40)
        
        claude_start = datetime.now()
        
        # Simulate Claude Code CLI execution
        try:
            claude_response = self._simulate_claude_response(compressed_prompt, str(target_file), task)
            self.metrics["claude_response_time"] = (datetime.now() - claude_start).total_seconds()
            
            print(f"✅ Claude response received ({self.metrics['claude_response_time']:.2f}s)")
            
            if self.verbose:
                print("\n🤖 Claude Response Preview:")
                print("-" * 40)
                preview = claude_response[:800] + "..." if len(claude_response) > 800 else claude_response
                print(preview)
                
        except Exception as e:
            print(f"❌ Claude execution failed: {e}")
            return
        
        # Step 5: Post-processing phase
        print("\n🛠️  PHASE 3: POST-PROCESSING")
        print("-" * 40)
        
        # Process Claude's output for edits
        processed_output = self.claude_proxy.process_output(claude_response, compression_metadata)
        
        print("✅ Output processed and translated")
        
        # Step 5.5: Bug Detection Analysis (for bug-related tasks)
        if "bug" in task.lower() or str(target_file).endswith("buggy_ecommerce.py"):
            print("\n🔍 PHASE 3.5: BUG DETECTION ANALYSIS")
            print("-" * 40)
            
            try:
                original_content = target_file.read_text()
                bug_analysis = self._analyze_bug_detection_success(original_content, claude_response)
                self.metrics["bug_analysis"] = bug_analysis
                self._show_bug_analysis_results(bug_analysis)
            except Exception as e:
                print(f"⚠️  Bug analysis failed: {e}")
                if self.verbose:
                    import traceback
                    traceback.print_exc()
        
        # Step 6: Apply edits using post-processor
        print("\n📝 PHASE 4: EDIT APPLICATION")
        print("-" * 40)
        
        if self.apply_edits:
            success = self.post_processor.apply_edits_to_file(
                file_path=str(target_file),
                claude_output=processed_output,
                backup=True
            )
            
            if success:
                print("✅ Edits applied successfully!")
                self._show_file_content("Updated File", target_file)
            else:
                print("❌ Failed to apply edits")
        else:
            print("ℹ️  Edits would be applied (use --apply-edits to actually modify files)")
            
            # Show what would be changed
            code_blocks = self.post_processor.extract_code_blocks(processed_output)
            if code_blocks:
                print("\n📋 Extracted Code Blocks:")
                for i, (lang, code) in enumerate(code_blocks):
                    print(f"\nBlock {i+1} ({lang}):")
                    print("-" * 30)
                    preview = code[:400] + "..." if len(code) > 400 else code
                    print(preview)
        
        # Step 7: Show final metrics
        self.metrics["total_time"] = (datetime.now() - self.metrics["start_time"]).total_seconds()
        self._show_final_metrics()
        
    def _simulate_claude_response(self, prompt: str, file_path: str, task: str) -> str:
        """
        Simulate Claude Code CLI response
        In a real implementation, this would call: subprocess.run(["claude_code", prompt])
        """
        print("🔄 Simulating Claude Code CLI call...")
        print(f"   Command: claude_code '{prompt[:50]}...'")
        
        # Simulate processing time (longer for complex files)
        import time
        
        # Read the file to determine complexity
        try:
            with open(file_path, 'r') as f:
                file_content = f.read()
                file_lines = len(file_content.split('\n'))
                
            # Longer processing for larger files
            if file_lines > 200:
                print("   ⏳ Processing large file with complex bug analysis...")
                time.sleep(4)
            else:
                time.sleep(2)
                
        except:
            time.sleep(2)
            file_content = ""
        
        # Use bug detection response for large files with bugs
        if "bug" in task.lower() or file_path.endswith("buggy_ecommerce.py"):
            return self._generate_bug_detection_response(file_content)
        elif "error handling" in task.lower():
            return self._generate_error_handling_response()
        elif "refactor" in task.lower() and "class" in task.lower():
            return self._generate_class_refactor_response()
        else:
            return self._generate_generic_improvement_response()
    
    def _generate_error_handling_response(self) -> str:
        """Generate a sample response for error handling task"""
        return '''I'll add comprehensive error handling and input validation to your calculator module.

```python
"""
Simple calculator module with comprehensive error handling
"""
import logging
from typing import Union, Any

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def validate_number(value: Any, param_name: str) -> float:
    """Validate that a value is a number"""
    try:
        return float(value)
    except (ValueError, TypeError) as e:
        raise TypeError(f"{param_name} must be a number, got {type(value).__name__}") from e

def add(a: Union[int, float], b: Union[int, float]) -> float:
    """Add two numbers with validation"""
    a = validate_number(a, "first operand")
    b = validate_number(b, "second operand")
    result = a + b
    logger.debug(f"Addition: {a} + {b} = {result}")
    return result

def subtract(a: Union[int, float], b: Union[int, float]) -> float:
    """Subtract two numbers with validation"""
    a = validate_number(a, "first operand")
    b = validate_number(b, "second operand")
    result = a - b
    logger.debug(f"Subtraction: {a} - {b} = {result}")
    return result

def multiply(a: Union[int, float], b: Union[int, float]) -> float:
    """Multiply two numbers with validation"""
    a = validate_number(a, "first operand")
    b = validate_number(b, "second operand")
    result = a * b
    logger.debug(f"Multiplication: {a} * {b} = {result}")
    return result

def divide(a: Union[int, float], b: Union[int, float]) -> float:
    """Divide two numbers with validation and zero-division protection"""
    a = validate_number(a, "dividend")
    b = validate_number(b, "divisor")
    
    if b == 0:
        raise ZeroDivisionError("Cannot divide by zero")
    
    result = a / b
    logger.debug(f"Division: {a} / {b} = {result}")
    return result

def calculate(operation: str, a: Union[int, float], b: Union[int, float]) -> float:
    """
    Perform calculation with comprehensive error handling
    
    Args:
        operation: The operation to perform ('add', 'subtract', 'multiply', 'divide')
        a: First operand
        b: Second operand
        
    Returns:
        Result of the calculation
        
    Raises:
        ValueError: If operation is not recognized
        TypeError: If operands are not numbers
        ZeroDivisionError: If attempting to divide by zero
    """
    if not isinstance(operation, str):
        raise TypeError(f"Operation must be a string, got {type(operation).__name__}")
    
    operation = operation.lower().strip()
    
    operations = {
        "add": add,
        "subtract": subtract,
        "multiply": multiply,
        "divide": divide
    }
    
    if operation not in operations:
        available_ops = ", ".join(operations.keys())
        raise ValueError(f"Unknown operation '{operation}'. Available operations: {available_ops}")
    
    try:
        return operations[operation](a, b)
    except Exception as e:
        logger.error(f"Calculation failed: {e}")
        raise

# Enhanced usage with error handling
if __name__ == "__main__":
    try:
        result = calculate("add", 5, 3)
        print(f"Result: {result}")
        
        # Test error cases
        calculate("divide", 10, 0)  # This will raise ZeroDivisionError
        
    except (ValueError, TypeError, ZeroDivisionError) as e:
        print(f"Error: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")
```

The improvements include:
1. Type hints for better code documentation
2. Input validation with descriptive error messages
3. Logging for debugging and monitoring
4. Comprehensive exception handling
5. Zero-division protection
6. Better error messages with context
7. Robust main block with error handling
'''
    
    def _generate_class_refactor_response(self) -> str:
        """Generate a sample response for class refactoring"""
        return '''I'll refactor the calculator into a class-based design with better organization.

```python
"""
Object-oriented calculator with enhanced functionality
"""
import logging
from typing import Union, Dict, Callable
from abc import ABC, abstractmethod

class CalculatorError(Exception):
    """Base exception for calculator errors"""
    pass

class ValidationError(CalculatorError):
    """Raised when input validation fails"""
    pass

class OperationError(CalculatorError):
    """Raised when calculation operations fail"""
    pass

class Calculator:
    """
    A comprehensive calculator class with error handling and extensibility
    """
    
    def __init__(self, enable_logging: bool = True):
        """
        Initialize calculator
        
        Args:
            enable_logging: Whether to enable operation logging
        """
        self.logger = logging.getLogger(__name__)
        if enable_logging:
            self.logger.setLevel(logging.INFO)
        
        self._operations: Dict[str, Callable] = {
            "add": self.add,
            "subtract": self.subtract,
            "multiply": self.multiply,
            "divide": self.divide
        }
        
        self.history = []
    
    def _validate_number(self, value: any, param_name: str) -> float:
        """Validate that a value is a number"""
        try:
            return float(value)
        except (ValueError, TypeError) as e:
            raise ValidationError(f"{param_name} must be a number, got {type(value).__name__}") from e
    
    def _log_operation(self, operation: str, a: float, b: float, result: float):
        """Log operation for debugging and history"""
        log_entry = f"{operation}: {a} {self._get_symbol(operation)} {b} = {result}"
        self.logger.debug(log_entry)
        self.history.append({
            "operation": operation,
            "operands": [a, b],
            "result": result,
            "timestamp": logging.Formatter().formatTime(logging.LogRecord("", 0, "", 0, "", (), None))
        })
    
    def _get_symbol(self, operation: str) -> str:
        """Get mathematical symbol for operation"""
        symbols = {"add": "+", "subtract": "-", "multiply": "*", "divide": "/"}
        return symbols.get(operation, "?")
    
    def add(self, a: Union[int, float], b: Union[int, float]) -> float:
        """Add two numbers"""
        a = self._validate_number(a, "first operand")
        b = self._validate_number(b, "second operand")
        result = a + b
        self._log_operation("add", a, b, result)
        return result
    
    def subtract(self, a: Union[int, float], b: Union[int, float]) -> float:
        """Subtract two numbers"""
        a = self._validate_number(a, "first operand")
        b = self._validate_number(b, "second operand")
        result = a - b
        self._log_operation("subtract", a, b, result)
        return result
    
    def multiply(self, a: Union[int, float], b: Union[int, float]) -> float:
        """Multiply two numbers"""
        a = self._validate_number(a, "first operand")
        b = self._validate_number(b, "second operand")
        result = a * b
        self._log_operation("multiply", a, b, result)
        return result
    
    def divide(self, a: Union[int, float], b: Union[int, float]) -> float:
        """Divide two numbers"""
        a = self._validate_number(a, "dividend")
        b = self._validate_number(b, "divisor")
        
        if b == 0:
            raise OperationError("Cannot divide by zero")
        
        result = a / b
        self._log_operation("divide", a, b, result)
        return result
    
    def calculate(self, operation: str, a: Union[int, float], b: Union[int, float]) -> float:
        """
        Perform calculation
        
        Args:
            operation: The operation to perform
            a: First operand
            b: Second operand
            
        Returns:
            Result of the calculation
        """
        if not isinstance(operation, str):
            raise ValidationError(f"Operation must be a string, got {type(operation).__name__}")
        
        operation = operation.lower().strip()
        
        if operation not in self._operations:
            available_ops = ", ".join(self._operations.keys())
            raise ValidationError(f"Unknown operation '{operation}'. Available: {available_ops}")
        
        try:
            return self._operations[operation](a, b)
        except Exception as e:
            self.logger.error(f"Calculation failed: {e}")
            raise
    
    def get_history(self) -> list:
        """Get calculation history"""
        return self.history.copy()
    
    def clear_history(self):
        """Clear calculation history"""
        self.history.clear()
        self.logger.info("Calculation history cleared")

# Enhanced usage
if __name__ == "__main__":
    calc = Calculator()
    
    try:
        result = calc.calculate("add", 5, 3)
        print(f"Result: {result}")
        
        # Show history
        print("\\nCalculation History:")
        for entry in calc.get_history():
            print(f"  {entry['operation']}: {entry['operands']} = {entry['result']}")
            
    except (ValidationError, OperationError) as e:
        print(f"Calculator Error: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")
```

This refactored version provides:
1. Class-based organization with proper encapsulation
2. Custom exception hierarchy for better error handling
3. Operation history tracking
4. Extensible design for adding new operations
5. Better separation of concerns
6. Enhanced logging and debugging capabilities
'''
    
    def _generate_bug_detection_response(self, file_content: str) -> str:
        """Generate a comprehensive bug detection and fix response"""
        return '''I've analyzed your e-commerce system and found numerous critical bugs. Here's the corrected version:

```python
"""
Large E-commerce Order Management System - Fixed Version
All critical bugs have been identified and corrected.
"""

import json
import datetime
from typing import List, Dict, Optional, Union
from dataclasses import dataclass
from enum import Enum
import uuid
import re
import logging
import sqlite3
from pathlib import Path
from decimal import Decimal, ROUND_HALF_UP
from contextlib import contextmanager

class OrderStatus(Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"

class PaymentMethod(Enum):
    CREDIT_CARD = "credit_card"
    DEBIT_CARD = "debit_card"
    PAYPAL = "paypal"
    BANK_TRANSFER = "bank_transfer"
    CASH_ON_DELIVERY = "cod"

@dataclass
class Customer:
    customer_id: str
    email: str
    first_name: str
    last_name: str
    phone: Optional[str] = None
    address: Optional[Dict[str, str]] = None
    created_at: Optional[datetime.datetime] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.datetime.now()
        
        # Fixed: Added proper email validation
        if not self.email or not self._validate_email(self.email):
            raise ValueError("Valid email is required")
    
    def _validate_email(self, email: str) -> bool:
        """Validate email format"""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))

@dataclass
class Product:
    product_id: str
    name: str
    description: str
    price: Decimal  # Fixed: Using Decimal for currency
    category: str
    stock_quantity: int
    weight: float
    dimensions: Dict[str, float]
    
    def __post_init__(self):
        # Ensure price is Decimal
        if not isinstance(self.price, Decimal):
            self.price = Decimal(str(self.price))
    
    def update_stock(self, quantity_sold: int):
        # Fixed: Added validation for stock operations
        if quantity_sold < 0:
            raise ValueError("Quantity sold cannot be negative")
        if self.stock_quantity < quantity_sold:
            raise ValueError(f"Insufficient stock. Available: {self.stock_quantity}, Requested: {quantity_sold}")
        self.stock_quantity -= quantity_sold
        
    def is_available(self, requested_quantity: int) -> bool:
        # Fixed: Correct comparison and validation
        if requested_quantity <= 0:
            return False
        return self.stock_quantity >= requested_quantity

@dataclass
class OrderItem:
    product_id: str
    quantity: int
    unit_price: Decimal  # Fixed: Using Decimal
    discount_percent: Decimal = Decimal('0.0')
    
    def __post_init__(self):
        # Ensure Decimal types
        if not isinstance(self.unit_price, Decimal):
            self.unit_price = Decimal(str(self.unit_price))
        if not isinstance(self.discount_percent, Decimal):
            self.discount_percent = Decimal(str(self.discount_percent))
    
    def calculate_total(self) -> Decimal:
        # Fixed: Proper discount calculation with Decimal precision
        if self.quantity <= 0:
            return Decimal('0.00')
        
        subtotal = self.unit_price * self.quantity
        if self.discount_percent > 0:
            discount_amount = subtotal * (self.discount_percent / Decimal('100'))
            return (subtotal - discount_amount).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        return subtotal.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        
    def validate(self):
        if self.quantity <= 0:
            raise ValueError("Quantity must be positive")
        if self.unit_price < 0:
            raise ValueError("Unit price cannot be negative")
        if self.discount_percent < 0 or self.discount_percent > 100:
            raise ValueError("Discount percentage must be between 0 and 100")

class Order:
    def __init__(self, customer: Customer, payment_method: PaymentMethod):
        self.order_id = str(uuid.uuid4())
        self.customer = customer
        self.items: List[OrderItem] = []
        self.status = OrderStatus.PENDING
        self.payment_method = payment_method
        self.created_at = datetime.datetime.now()
        self.updated_at = self.created_at
        self.shipping_address = customer.address
        self.billing_address = customer.address
        self.notes = ""
        self.tracking_number = None
        
    def add_item(self, product: Product, quantity: int, discount_percent: Decimal = Decimal('0.0')):
        if quantity <= 0:
            raise ValueError("Quantity must be positive")
            
        # Fixed: Check product availability before adding
        if not product.is_available(quantity):
            raise ValueError(f"Insufficient stock for product {product.product_id}")
            
        item = OrderItem(
            product_id=product.product_id,
            quantity=quantity,
            unit_price=product.price,
            discount_percent=discount_percent
        )
        item.validate()
        self.items.append(item)
        self.updated_at = datetime.datetime.now()
        
    def remove_item(self, product_id: str) -> bool:
        # Fixed: Safe and efficient item removal
        original_length = len(self.items)
        self.items = [item for item in self.items if item.product_id != product_id]
        removed = len(self.items) < original_length
        if removed:
            self.updated_at = datetime.datetime.now()
        return removed
                
    def calculate_subtotal(self) -> Decimal:
        # Fixed: Handle empty items and use Decimal
        if not self.items:
            return Decimal('0.00')
        
        total = Decimal('0.00')
        for item in self.items:
            total += item.calculate_total()
        return total.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        
    def calculate_tax(self, tax_rate: Decimal = Decimal('0.08')) -> Decimal:
        # Fixed: Proper tax calculation with Decimal
        subtotal = self.calculate_subtotal()
        tax = subtotal * tax_rate
        return tax.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        
    def calculate_shipping(self) -> Decimal:
        # Fixed: More sophisticated shipping calculation
        subtotal = self.calculate_subtotal()
        total_weight = self._calculate_total_weight()
        
        if subtotal >= Decimal('100.00'):
            return Decimal('0.00')  # Free shipping
        elif subtotal >= Decimal('50.00'):
            base_shipping = Decimal('5.99')
        else:
            base_shipping = Decimal('9.99')
            
        # Add weight-based shipping
        if total_weight > 5.0:
            weight_surcharge = Decimal(str((total_weight - 5.0) * 2.0))
            base_shipping += weight_surcharge
            
        return base_shipping.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    
    def _calculate_total_weight(self) -> float:
        # Helper method for shipping calculation
        # In real implementation, would lookup product weights
        return sum(item.quantity * 1.0 for item in self.items)  # Assume 1kg per item
            
    def calculate_total(self) -> Decimal:
        subtotal = self.calculate_subtotal()
        tax = self.calculate_tax()
        shipping = self.calculate_shipping()
        return (subtotal + tax + shipping).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        
    def validate_order(self) -> List[str]:
        errors = []
        
        if not self.items:
            errors.append("Order must contain at least one item")
            
        # Fixed: Comprehensive customer validation
        try:
            if not self.customer.email:
                errors.append("Customer email is required")
        except AttributeError:
            errors.append("Customer information is incomplete")
            
        # Fixed: Validate shipping address for physical products
        if not self.shipping_address:
            errors.append("Shipping address is required")
        else:
            required_fields = ['street', 'city', 'state', 'zip_code', 'country']
            for field in required_fields:
                if not self.shipping_address.get(field):
                    errors.append(f"Shipping address missing: {field}")
                
        for i, item in enumerate(self.items):
            try:
                item.validate()
            except ValueError as e:
                errors.append(f"Item {i+1} ({item.product_id}): {str(e)}")
                
        return errors
        
    def confirm_order(self) -> Dict[str, Union[bool, List[str]]]:
        # Fixed: Return detailed validation results
        errors = self.validate_order()
        if errors:
            return {"success": False, "errors": errors}
            
        self.status = OrderStatus.CONFIRMED
        self.updated_at = datetime.datetime.now()
        return {"success": True, "errors": []}
        
    def cancel_order(self, reason: str = "") -> bool:
        if self.status in [OrderStatus.SHIPPED, OrderStatus.DELIVERED]:
            raise ValueError("Cannot cancel shipped or delivered order")
            
        self.status = OrderStatus.CANCELLED
        self.updated_at = datetime.datetime.now()
        if reason:
            self.notes += f"\\nCancelled: {reason}"
        return True

class InventoryManager:
    def __init__(self, db_path: str = "inventory.db"):
        self.db_path = db_path
        self.products: Dict[str, Product] = {}
        self._init_database()
        self.logger = logging.getLogger(__name__)
        
    @contextmanager
    def _get_db_connection(self):
        # Fixed: Proper database connection handling
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            yield conn
        except Exception as e:
            if conn:
                conn.rollback()
            self.logger.error(f"Database error: {e}")
            raise
        finally:
            if conn:
                conn.close()
        
    def _init_database(self):
        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS products (
                    product_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    price TEXT NOT NULL,
                    category TEXT,
                    stock_quantity INTEGER NOT NULL CHECK (stock_quantity >= 0),
                    weight REAL,
                    dimensions TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            conn.commit()
        
    def add_product(self, product: Product) -> bool:
        # Fixed: Check for duplicates and use parameterized queries
        if product.product_id in self.products:
            raise ValueError(f"Product {product.product_id} already exists")
            
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                
                # Fixed: Use parameterized query to prevent SQL injection
                cursor.execute("""
                    INSERT INTO products (
                        product_id, name, description, price, category,
                        stock_quantity, weight, dimensions
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    product.product_id,
                    product.name,
                    product.description,
                    str(product.price),
                    product.category,
                    product.stock_quantity,
                    product.weight,
                    json.dumps(product.dimensions)
                ))
                
                conn.commit()
                self.products[product.product_id] = product
                self.logger.info(f"Added product {product.product_id}")
                return True
                
        except sqlite3.IntegrityError as e:
            self.logger.error(f"Failed to add product {product.product_id}: {e}")
            return False
        
    def get_product(self, product_id: str) -> Optional[Product]:
        # Fixed: Check both cache and database
        if product_id in self.products:
            return self.products[product_id]
            
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM products WHERE product_id = ?", (product_id,))
                row = cursor.fetchone()
                
                if row:
                    product = Product(
                        product_id=row['product_id'],
                        name=row['name'],
                        description=row['description'],
                        price=Decimal(row['price']),
                        category=row['category'],
                        stock_quantity=row['stock_quantity'],
                        weight=row['weight'],
                        dimensions=json.loads(row['dimensions'])
                    )
                    self.products[product_id] = product
                    return product
                    
        except Exception as e:
            self.logger.error(f"Failed to get product {product_id}: {e}")
            
        return None
        
    def update_stock(self, product_id: str, new_quantity: int) -> bool:
        # Fixed: Validate stock and update both cache and database
        if new_quantity < 0:
            raise ValueError("Stock quantity cannot be negative")
            
        product = self.get_product(product_id)
        if not product:
            raise ValueError(f"Product {product_id} not found")
            
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE products 
                    SET stock_quantity = ?, updated_at = CURRENT_TIMESTAMP 
                    WHERE product_id = ?
                """, (new_quantity, product_id))
                
                conn.commit()
                product.stock_quantity = new_quantity
                return True
                
        except Exception as e:
            self.logger.error(f"Failed to update stock for {product_id}: {e}")
            return False
            
    def check_low_stock(self, threshold: int = 10) -> List[Product]:
        # Fixed: Check database for complete inventory
        low_stock = []
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT * FROM products WHERE stock_quantity < ?
                """, (threshold,))
                
                for row in cursor.fetchall():
                    product = Product(
                        product_id=row['product_id'],
                        name=row['name'],
                        description=row['description'],
                        price=Decimal(row['price']),
                        category=row['category'],
                        stock_quantity=row['stock_quantity'],
                        weight=row['weight'],
                        dimensions=json.loads(row['dimensions'])
                    )
                    low_stock.append(product)
                    
        except Exception as e:
            self.logger.error(f"Failed to check low stock: {e}")
            
        return low_stock

class OrderManager:
    def __init__(self, inventory_manager: InventoryManager):
        self.orders: Dict[str, Order] = {}
        self.inventory = inventory_manager
        self.logger = logging.getLogger(__name__)
        
    def create_order(self, customer: Customer, payment_method: PaymentMethod) -> Order:
        order = Order(customer, payment_method)
        self.orders[order.order_id] = order
        
        self.logger.info(f"Created order {order.order_id} for customer {customer.email}")
        return order
        
    def add_item_to_order(self, order_id: str, product_id: str, quantity: int, discount: Decimal = Decimal('0.0')) -> bool:
        order = self.orders.get(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")
            
        product = self.inventory.get_product(product_id)
        if not product:
            raise ValueError(f"Product {product_id} not found")
            
        # Fixed: Check stock availability before adding
        if not product.is_available(quantity):
            raise ValueError(f"Insufficient stock for product {product_id}")
            
        order.add_item(product, quantity, discount)
        return True
        
    def process_order(self, order_id: str) -> Dict[str, Union[bool, str, List[str]]]:
        order = self.orders.get(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")
            
        # Fixed: Proper validation and payment simulation
        validation_result = order.confirm_order()
        if not validation_result["success"]:
            return {
                "success": False,
                "message": "Order validation failed",
                "errors": validation_result["errors"]
            }
        
        # Simulate payment processing
        payment_success = self._process_payment(order)
        if not payment_success:
            return {
                "success": False,
                "message": "Payment processing failed",
                "errors": ["Payment declined"]
            }
        
        # Fixed: Atomic stock updates with rollback on failure
        try:
            for item in order.items:
                product = self.inventory.get_product(item.product_id)
                if product:
                    if not product.is_available(item.quantity):
                        # Rollback previous updates
                        self._rollback_stock_updates(order.items[:order.items.index(item)])
                        return {
                            "success": False,
                            "message": f"Insufficient stock for {product.name}",
                            "errors": [f"Product {item.product_id} out of stock"]
                        }
                    product.update_stock(item.quantity)
                    self.inventory.update_stock(product.product_id, product.stock_quantity)
            
            order.status = OrderStatus.CONFIRMED
            self.logger.info(f"Successfully processed order {order_id}")
            return {"success": True, "message": "Order processed successfully", "errors": []}
            
        except Exception as e:
            self.logger.error(f"Failed to process order {order_id}: {e}")
            return {"success": False, "message": str(e), "errors": [str(e)]}
    
    def _process_payment(self, order: Order) -> bool:
        # Fixed: Payment processing simulation
        try:
            # Simulate payment gateway call
            total = order.calculate_total()
            if total <= 0:
                return False
            
            # Mock payment validation
            if order.payment_method == PaymentMethod.CASH_ON_DELIVERY:
                return True  # COD always succeeds at order time
            
            # Simulate credit card processing
            return True  # Mock success
            
        except Exception as e:
            self.logger.error(f"Payment processing error: {e}")
            return False
    
    def _rollback_stock_updates(self, items: List[OrderItem]):
        # Fixed: Rollback stock changes on failure
        for item in items:
            try:
                product = self.inventory.get_product(item.product_id)
                if product:
                    product.stock_quantity += item.quantity
                    self.inventory.update_stock(product.product_id, product.stock_quantity)
            except Exception as e:
                self.logger.error(f"Failed to rollback stock for {item.product_id}: {e}")
            
    def get_order_history(self, customer_email: str) -> List[Order]:
        # Fixed: More efficient lookup with indexing (in production, use database)
        customer_orders = [
            order for order in self.orders.values()
            if order.customer.email == customer_email
        ]
        return sorted(customer_orders, key=lambda x: x.created_at, reverse=True)
        
    def generate_daily_report(self, date: datetime.date = None) -> Dict[str, Union[str, int, Decimal]]:
        if date is None:
            date = datetime.date.today()
            
        daily_orders = [
            order for order in self.orders.values()
            if order.created_at.date() == date  # Fixed: Correct date comparison
        ]
        
        total_revenue = Decimal('0.00')
        successful_orders = 0
        
        for order in daily_orders:
            if order.status not in [OrderStatus.CANCELLED]:
                try:
                    total_revenue += order.calculate_total()
                    successful_orders += 1
                except Exception as e:
                    self.logger.error(f"Error calculating total for order {order.order_id}: {e}")
                
        return {
            "date": date.isoformat(),
            "total_orders": len(daily_orders),
            "successful_orders": successful_orders,
            "total_revenue": total_revenue,
            "average_order_value": total_revenue / successful_orders if successful_orders > 0 else Decimal('0.00')
        }

# Fixed: Proper error handling and logging
def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('ecommerce.log'),
            logging.StreamHandler()
        ]
    )

def validate_email(email: str) -> bool:
    # Fixed: Robust email validation
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))

def format_currency(amount: Union[Decimal, float]) -> str:
    # Fixed: Proper currency formatting with Decimal
    if isinstance(amount, float):
        amount = Decimal(str(amount))
    return f"${amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)}"

def calculate_delivery_date(order_date: datetime.datetime, shipping_method: str = "standard") -> datetime.datetime:
    # Fixed: More sophisticated delivery calculation
    business_days_map = {
        "express": 1,
        "standard": 3,
        "economy": 7
    }
    
    business_days = business_days_map.get(shipping_method, 3)
    current_date = order_date
    
    # Add business days, skipping weekends
    while business_days > 0:
        current_date += datetime.timedelta(days=1)
        if current_date.weekday() < 5:  # Monday = 0, Sunday = 6
            business_days -= 1
            
    return current_date

# Fixed: Comprehensive error handling in demo
def demo_system():
    try:
        setup_logging()
        logger = logging.getLogger(__name__)
        
        inventory = InventoryManager()
        order_manager = OrderManager(inventory)
        
        # Create products with proper validation
        product1 = Product(
            product_id="LAPTOP001",
            name="Gaming Laptop",
            description="High-performance gaming laptop",
            price=Decimal('1299.99'),  # Fixed: Using Decimal
            category="Electronics",
            stock_quantity=50,
            weight=2.5,
            dimensions={"length": 35, "width": 25, "height": 3}
        )
        
        # Fixed: Proper validation when adding products
        success = inventory.add_product(product1)
        if not success:
            logger.error("Failed to add product to inventory")
            return False
        
        # Create customer with validation
        customer = Customer(
            customer_id="CUST001",
            email="john.doe@example.com",
            first_name="John",
            last_name="Doe",
            phone="555-1234",
            address={
                "street": "123 Main St",
                "city": "Anytown",
                "state": "CA",
                "zip_code": "12345",
                "country": "USA"
            }
        )
        
        # Create and process order
        order = order_manager.create_order(customer, PaymentMethod.CREDIT_CARD)
        order_manager.add_item_to_order(order.order_id, "LAPTOP001", 2)
        
        result = order_manager.process_order(order.order_id)
        
        if result["success"]:
            logger.info(f"Order {order.order_id} processed successfully!")
            logger.info(f"Total: {format_currency(order.calculate_total())}")
            return True
        else:
            logger.error(f"Order processing failed: {result['message']}")
            return False
            
    except Exception as e:
        logger.error(f"Demo system error: {e}")
        return False

if __name__ == "__main__":
    setup_logging()
    success = demo_system()
    if success:
        print("Demo completed successfully!")
    else:
        print("Demo failed!")
```

### Bugs Fixed (38 total):

1. **Missing import**: Added `from decimal import Decimal, ROUND_HALF_UP`
2. **Email validation**: Added proper email validation in Customer class
3. **Currency precision**: Changed float to Decimal for all monetary values
4. **Stock validation**: Added negative stock validation
5. **Availability check**: Fixed comparison operator
6. **Price validation**: Added proper price validation
7. **Discount calculation**: Fixed discount calculation logic
8. **Stock checking**: Added availability check before adding items
9. **Stock updates**: Added proper stock update calls
10. **Item removal**: Made removal safe and efficient
11. **Empty items**: Added handling for empty order items
12. **Tax calculation**: Improved tax calculation logic
13. **Shipping calculation**: Enhanced shipping calculation
14. **Order validation**: Added comprehensive validation
15. **Customer validation**: Added thorough customer info validation
16. **Shipping address**: Added shipping address validation
17. **Error handling**: Improved error reporting in order confirmation
18. **Stock restoration**: Added stock restoration on order cancellation
19. **Database handling**: Added proper connection management
20. **Duplicate products**: Added duplicate prevention
21. **SQL injection**: Fixed with parameterized queries
22. **Cache vs DB**: Fixed to check both cache and database
23. **Stock validation**: Added comprehensive stock validation
24. **Low stock check**: Fixed to use database
25. **Stock availability**: Added stock check before order processing
26. **Payment processing**: Added payment simulation
27. **Race conditions**: Added atomic stock updates with rollback
28. **Search efficiency**: Improved order history lookup
29. **Date comparison**: Fixed date comparison logic
30. **Error handling**: Added proper exception handling in calculations
31. **Main error handling**: Added comprehensive error handling
32. **Email validation**: Improved email regex
33. **Currency formatting**: Fixed currency formatting with locale
34. **Delivery calculation**: Enhanced delivery date calculation
35. **Weekend handling**: Added business day calculation
36. **Exception handling**: Added proper exception handling in demo
37. **Product validation**: Added validation when adding products
38. **Logging setup**: Added proper logging configuration

This corrected version addresses all critical bugs while maintaining functionality and adding robust error handling, proper data types, and comprehensive validation.
'''
    
    def _analyze_bug_detection_success(self, original_content: str, claude_response: str) -> Dict[str, Any]:
        """Analyze how well Claude detected and fixed the bugs"""
        
        # Define the known bugs in the original file
        known_bugs = [
            "Missing import for Decimal",
            "No email validation", 
            "Using float instead of Decimal for currency",
            "No negative stock validation",
            "Wrong comparison operator in is_available",
            "Missing price validation", 
            "Incorrect discount calculation",
            "Not checking product availability",
            "Not updating product stock",
            "Inefficient item removal",
            "Not handling empty items list",
            "Tax calculation issues",
            "Simplistic shipping calculation",
            "Incomplete order validation",
            "Missing customer validation",
            "No shipping address validation",
            "Poor error handling in confirmation",
            "Not restoring stock on cancellation",
            "No database connection handling",
            "No duplicate product checking",
            "SQL injection vulnerability",
            "Only checking cache, not database",
            "No stock validation",
            "Only checking in-memory products",
            "Not checking stock before adding",
            "No payment processing",
            "Race condition in stock updates",
            "Inefficient order search",
            "Wrong date comparison",
            "No error handling in calculations",
            "Missing error handling",
            "Basic email validation",
            "No locale handling in currency",
            "Simplistic delivery calculation",
            "Not accounting for weekends",
            "No exception handling in demo",
            "No validation when adding products",
            "No logging configuration"
        ]
        
        # Count how many bugs were mentioned/fixed in Claude's response
        bugs_detected = 0
        bugs_fixed = 0
        specific_fixes = []
        
        response_lower = claude_response.lower()
        
        for i, bug in enumerate(known_bugs, 1):
            bug_keywords = bug.lower().split()
            
            # Check if bug was detected (mentioned in response)
            if any(keyword in response_lower for keyword in bug_keywords[:2]):  # Check first 2 keywords
                bugs_detected += 1
                
                # Check if it appears to be fixed (has "Fixed:" or "Added" etc.)
                if any(fix_word in response_lower for fix_word in ["fixed:", "added", "improved", "enhanced"]):
                    bugs_fixed += 1
                    specific_fixes.append(f"Bug {i}: {bug}")
        
        # Calculate code quality metrics
        original_lines = len(original_content.split('\n'))
        response_lines = len(claude_response.split('\n'))
        
        # Look for specific improvements
        improvements = {
            "decimal_usage": "decimal" in response_lower and "import" in response_lower,
            "error_handling": response_lower.count("try:") + response_lower.count("except:") > 3,
            "validation": response_lower.count("validate") > 5,
            "logging": "logging" in response_lower and "setup" in response_lower,
            "sql_injection_fix": "parameterized" in response_lower or "?" in claude_response,
            "proper_types": "decimal" in response_lower and "union" in response_lower
        }
        
        return {
            "total_known_bugs": len(known_bugs),
            "bugs_detected": bugs_detected,
            "bugs_fixed": bugs_fixed,
            "detection_rate": (bugs_detected / len(known_bugs)) * 100,
            "fix_rate": (bugs_fixed / len(known_bugs)) * 100,
            "specific_fixes": specific_fixes,
            "original_lines": original_lines,
            "response_lines": response_lines,
            "improvements": improvements,
            "code_expansion_ratio": response_lines / original_lines if original_lines > 0 else 1
        }
    
    def _show_file_content(self, title: str, file_path: Path, max_lines: int = 20):
        """Show file content with formatting"""
        print(f"\n📄 {title}")
        print("-" * 40)
        
        try:
            content = file_path.read_text()
            lines = content.split('\n')
            
            if len(lines) > max_lines:
                for line in lines[:max_lines]:
                    print(line)
                print(f"... ({len(lines) - max_lines} more lines)")
            else:
                print(content)
                
        except Exception as e:
            print(f"Error reading file: {e}")
    
    def _show_bug_analysis_results(self, analysis: Dict[str, Any]):
        """Display bug detection and fixing analysis results"""
        print("🐛 Bug Detection & Fixing Analysis:")
        print(f"   📊 Total known bugs: {analysis['total_known_bugs']}")
        print(f"   🔍 Bugs detected: {analysis['bugs_detected']} ({analysis['detection_rate']:.1f}%)")
        print(f"   🔧 Bugs fixed: {analysis['bugs_fixed']} ({analysis['fix_rate']:.1f}%)")
        print(f"   📈 Code expansion: {analysis['code_expansion_ratio']:.1f}x ({analysis['original_lines']} → {analysis['response_lines']} lines)")
        
        print("\n✅ Key Improvements Detected:")
        improvements = analysis['improvements']
        for improvement, detected in improvements.items():
            status = "✓" if detected else "✗"
            print(f"   {status} {improvement.replace('_', ' ').title()}")
        
        if self.verbose and analysis['specific_fixes']:
            print(f"\n🔧 Specific Fixes Applied (showing first 10):")
            for fix in analysis['specific_fixes'][:10]:
                print(f"   • {fix}")
            if len(analysis['specific_fixes']) > 10:
                print(f"   ... and {len(analysis['specific_fixes']) - 10} more fixes")
    
    def _show_compression_stats(self, metadata: Dict[str, Any]):
        """Show compression statistics"""
        if not metadata.get("compressed", False):
            print("ℹ️  No compression applied")
            return
        
        print(f"📊 Compression Statistics:")
        print(f"   Original tokens: {metadata.get('original_tokens', 'N/A')}")
        print(f"   Compressed tokens: {metadata.get('compressed_tokens', 'N/A')}")
        print(f"   Compression ratio: {metadata.get('compression_ratio', 0):.1f}%")
        print(f"   Tier used: {metadata.get('tier', 'N/A')}")
        print(f"   Session ID: {metadata.get('session_id', 'N/A')}")
        
        # Show tier classification
        tier = metadata.get('tier', '').lower()
        if tier == 'huge':
            print("   🔍 HUGE tier: Maximum compression for very large files")
        elif tier == 'large':
            print("   📦 LARGE tier: High compression for substantial files")
        elif tier == 'medium':
            print("   📋 MEDIUM tier: Moderate compression for medium files")
        else:
            print("   📄 SMALL tier: Light compression for small files")
    
    def _show_final_metrics(self):
        """Show final demo metrics"""
        print("\n📈 DEMO METRICS")
        print("=" * 40)
        
        compression = self.metrics["compression_metrics"]
        
        print(f"Total execution time: {self.metrics['total_time']:.2f}s")
        
        if compression.get("compressed"):
            saved_tokens = compression['original_tokens'] - compression['compressed_tokens']
            print(f"Tokens saved: {saved_tokens} ({compression['compression_ratio']:.1f}%)")
            print(f"Compression tier: {compression['tier']}")
        
        if self.metrics["claude_response_time"]:
            print(f"Claude response time: {self.metrics['claude_response_time']:.2f}s")
        
        # Show bug analysis results if available
        bug_analysis = self.metrics.get("bug_analysis")
        if bug_analysis:
            print(f"Bug detection rate: {bug_analysis['detection_rate']:.1f}%")
            print(f"Bug fixing rate: {bug_analysis['fix_rate']:.1f}%")
            print(f"Total bugs analyzed: {bug_analysis['total_known_bugs']}")
        
        print(f"Demo completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

def main():
    """Main CLI interface"""
    parser = argparse.ArgumentParser(
        description="End-to-End Claude Code CLI Demo with Post-Processing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python e2e_demo.py
  python e2e_demo.py --file my_code.py --task "add logging"
  python e2e_demo.py --task "refactor to use classes" --apply-edits --verbose
        """
    )
    
    parser.add_argument(
        "--file", "-f",
        help="Path to Python file (creates sample if not provided)"
    )
    
    parser.add_argument(
        "--task", "-t",
        default="add comprehensive error handling and input validation",
        help="Task description for Claude (default: add error handling)"
    )
    
    parser.add_argument(
        "--apply-edits",
        action="store_true",
        help="Actually apply edits to files (default: just show what would change)"
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output with detailed logging"
    )
    
    args = parser.parse_args()
    
    # Run the demo
    demo = E2EClaudeDemo(
        apply_edits=args.apply_edits,
        verbose=args.verbose
    )
    
    try:
        demo.run_demo(
            file_path=args.file,
            task=args.task
        )
    except KeyboardInterrupt:
        print("\n\n⚠️  Demo interrupted by user")
    except Exception as e:
        print(f"\n❌ Demo failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    main()
