"""
Large E-commerce Order Management System - Buggy Version
This module contains intentional bugs for testing Claude's bug detection capabilities.
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

# Bug 1: Missing import
# from decimal import Decimal

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
    created_at: datetime.datetime = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.datetime.now()
        
        # Bug 2: No email validation
        if not self.email:
            raise ValueError("Email is required")

@dataclass
class Product:
    product_id: str
    name: str
    description: str
    price: float  # Bug 3: Should use Decimal for currency
    category: str
    stock_quantity: int
    weight: float
    dimensions: Dict[str, float]
    
    def update_stock(self, quantity_sold: int):
        # Bug 4: No validation for negative stock
        self.stock_quantity -= quantity_sold
        
    def is_available(self, requested_quantity: int) -> bool:
        # Bug 5: Wrong comparison operator
        return self.stock_quantity > requested_quantity

@dataclass
class OrderItem:
    product_id: str
    quantity: int
    unit_price: float  # Bug 6: Should use Decimal
    discount_percent: float = 0.0
    
    def calculate_total(self) -> float:
        # Bug 7: Incorrect calculation - doesn't handle discount properly
        subtotal = self.unit_price * self.quantity
        discount = subtotal * (self.discount_percent / 100)
        return subtotal - discount
        
    def validate(self):
        if self.quantity <= 0:
            raise ValueError("Quantity must be positive")
        # Bug 8: Missing price validation
        if self.unit_price < 0:
            raise ValueError("Unit price cannot be negative")

class Order:
    def __init__(self, customer: Customer, payment_method: PaymentMethod):
        self.order_id = str(uuid.uuid4())
        self.customer = customer
        self.items: List[OrderItem] = []
        self.status = OrderStatus.PENDING
        self.payment_method = payment_method
        self.created_at = datetime.datetime.now()
        self.updated_at = self.created_at
        self.shipping_address = None
        self.billing_address = None
        self.notes = ""
        self.tracking_number = None
        
    def add_item(self, product: Product, quantity: int, discount_percent: float = 0.0):
        if quantity <= 0:
            raise ValueError("Quantity must be positive")
            
        # Bug 9: Not checking if product is available
        item = OrderItem(
            product_id=product.product_id,
            quantity=quantity,
            unit_price=product.price,
            discount_percent=discount_percent
        )
        self.items.append(item)
        
        # Bug 10: Not updating product stock
        # product.update_stock(quantity)
        
    def remove_item(self, product_id: str):
        # Bug 11: Inefficient and potentially buggy removal
        for i, item in enumerate(self.items):
            if item.product_id == product_id:
                del self.items[i]
                break
                
    def calculate_subtotal(self) -> float:
        # Bug 12: Not handling empty items list
        total = 0.0
        for item in self.items:
            total += item.calculate_total()
        return total
        
    def calculate_tax(self, tax_rate: float = 0.08) -> float:
        # Bug 13: Tax calculation doesn't exclude non-taxable items
        return self.calculate_subtotal() * tax_rate
        
    def calculate_shipping(self) -> float:
        # Bug 14: Very simplistic shipping calculation
        subtotal = self.calculate_subtotal()
        if subtotal > 100:
            return 0.0
        elif subtotal > 50:
            return 5.99
        else:
            return 9.99
            
    def calculate_total(self) -> float:
        subtotal = self.calculate_subtotal()
        tax = self.calculate_tax()
        shipping = self.calculate_shipping()
        return subtotal + tax + shipping
        
    def validate_order(self) -> List[str]:
        errors = []
        
        if not self.items:
            errors.append("Order must contain at least one item")
            
        # Bug 15: Not validating customer information thoroughly
        if not self.customer.email:
            errors.append("Customer email is required")
            
        # Bug 16: Not checking shipping address for physical products
        
        for item in self.items:
            try:
                item.validate()
            except ValueError as e:
                errors.append(f"Item {item.product_id}: {str(e)}")
                
        return errors
        
    def confirm_order(self) -> bool:
        errors = self.validate_order()
        if errors:
            # Bug 17: Should raise exception or return detailed error info
            return False
            
        self.status = OrderStatus.CONFIRMED
        self.updated_at = datetime.datetime.now()
        return True
        
    def cancel_order(self, reason: str = ""):
        if self.status in [OrderStatus.SHIPPED, OrderStatus.DELIVERED]:
            raise ValueError("Cannot cancel shipped or delivered order")
            
        # Bug 18: Not restoring product stock when cancelling
        self.status = OrderStatus.CANCELLED
        self.updated_at = datetime.datetime.now()
        self.notes += f"\nCancelled: {reason}"

class InventoryManager:
    def __init__(self, db_path: str = "inventory.db"):
        self.db_path = db_path
        self.products: Dict[str, Product] = {}
        self._init_database()
        
    def _init_database(self):
        # Bug 19: No proper database connection handling
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS products (
                product_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                price REAL NOT NULL,
                category TEXT,
                stock_quantity INTEGER NOT NULL,
                weight REAL,
                dimensions TEXT
            )
        """)
        
        conn.commit()
        conn.close()
        
    def add_product(self, product: Product):
        # Bug 20: Not checking for duplicate product IDs
        self.products[product.product_id] = product
        
        # Bug 21: SQL injection vulnerability
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute(f"""
            INSERT INTO products VALUES (
                '{product.product_id}',
                '{product.name}',
                '{product.description}',
                {product.price},
                '{product.category}',
                {product.stock_quantity},
                {product.weight},
                '{json.dumps(product.dimensions)}'
            )
        """)
        
        conn.commit()
        conn.close()
        
    def get_product(self, product_id: str) -> Optional[Product]:
        # Bug 22: Only checking in-memory cache, not database
        return self.products.get(product_id)
        
    def update_stock(self, product_id: str, new_quantity: int):
        product = self.get_product(product_id)
        if product:
            # Bug 23: No validation for negative stock
            product.stock_quantity = new_quantity
        else:
            raise ValueError(f"Product {product_id} not found")
            
    def check_low_stock(self, threshold: int = 10) -> List[Product]:
        # Bug 24: Only checking in-memory products
        low_stock = []
        for product in self.products.values():
            if product.stock_quantity < threshold:
                low_stock.append(product)
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
        
    def add_item_to_order(self, order_id: str, product_id: str, quantity: int, discount: float = 0.0):
        order = self.orders.get(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")
            
        product = self.inventory.get_product(product_id)
        if not product:
            raise ValueError(f"Product {product_id} not found")
            
        # Bug 25: Not checking stock availability before adding
        order.add_item(product, quantity, discount)
        
    def process_order(self, order_id: str) -> bool:
        order = self.orders.get(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")
            
        # Bug 26: No payment processing simulation
        if order.confirm_order():
            # Update inventory
            for item in order.items:
                product = self.inventory.get_product(item.product_id)
                if product:
                    # Bug 27: Race condition - multiple orders could deplete stock
                    product.update_stock(item.quantity)
            
            self.logger.info(f"Processed order {order_id}")
            return True
        else:
            self.logger.error(f"Failed to process order {order_id}")
            return False
            
    def get_order_history(self, customer_email: str) -> List[Order]:
        # Bug 28: Inefficient linear search
        customer_orders = []
        for order in self.orders.values():
            if order.customer.email == customer_email:
                customer_orders.append(order)
        return customer_orders
        
    def generate_daily_report(self, date: datetime.date = None) -> Dict[str, Union[int, float]]:
        if date is None:
            date = datetime.date.today()
            
        daily_orders = []
        for order in self.orders.values():
            # Bug 29: Wrong date comparison
            if order.created_at.date() == date:
                daily_orders.append(order)
                
        total_revenue = 0.0
        total_orders = len(daily_orders)
        
        for order in daily_orders:
            if order.status != OrderStatus.CANCELLED:
                # Bug 30: Not handling potential calculation errors
                total_revenue += order.calculate_total()
                
        return {
            "date": date.isoformat(),
            "total_orders": total_orders,
            "total_revenue": total_revenue,
            "average_order_value": total_revenue / total_orders if total_orders > 0 else 0
        }

# Bug 31: Missing proper error handling in main functions
def validate_email(email: str) -> bool:
    # Bug 32: Very basic email validation
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return re.match(pattern, email) is not None

def format_currency(amount: float) -> str:
    # Bug 33: No proper locale handling
    return f"${amount:.2f}"

def calculate_delivery_date(order_date: datetime.datetime, shipping_method: str = "standard") -> datetime.datetime:
    # Bug 34: Overly simplistic delivery calculation
    if shipping_method == "express":
        days_to_add = 1
    elif shipping_method == "standard":
        days_to_add = 3
    else:
        days_to_add = 7
        
    # Bug 35: Not accounting for weekends or holidays
    return order_date + datetime.timedelta(days=days_to_add)

# Example usage with bugs
def demo_system():
    # Bug 36: No proper exception handling in demo
    inventory = InventoryManager()
    order_manager = OrderManager(inventory)
    
    # Create some products
    product1 = Product(
        product_id="LAPTOP001",
        name="Gaming Laptop",
        description="High-performance gaming laptop",
        price=1299.99,  # Bug: Should use Decimal
        category="Electronics",
        stock_quantity=50,
        weight=2.5,
        dimensions={"length": 35, "width": 25, "height": 3}
    )
    
    # Bug 37: No validation when adding products
    inventory.add_product(product1)
    
    # Create customer
    customer = Customer(
        customer_id="CUST001",
        email="john.doe@example.com",  # Bug: No email validation called
        first_name="John",
        last_name="Doe",
        phone="555-1234"
    )
    
    # Create order
    order = order_manager.create_order(customer, PaymentMethod.CREDIT_CARD)
    
    # Add items
    order_manager.add_item_to_order(order.order_id, "LAPTOP001", 2)
    
    # Process order
    success = order_manager.process_order(order.order_id)
    
    if success:
        print(f"Order {order.order_id} processed successfully!")
        print(f"Total: {format_currency(order.calculate_total())}")
    else:
        print("Order processing failed!")

if __name__ == "__main__":
    # Bug 38: No logging configuration
    demo_system()
