# 1. Simple function with docstring
sample1 = """def calculate_area(radius):
    #Calculate the area of a circle given its radius.
    import math
    return math.pi * radius ** 2"""


# 2. List comprehension with conditional
sample2 = """def filter_even_squares(numbers):
    return [x**2 for x in numbers if x % 2 == 0 and x > 0]"""


# 3. Class with properties and f-strings
sample3 = """class Person:
    def __init__(self, first_name, last_name, age):
        self.first_name = first_name
        self.last_name = last_name
        self._age = age
    
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"
    
    @property
    def age(self):
        return self._age
    
    def __str__(self):
        return f"Person(name='{self.full_name}', age={self.age})"
"""


# 4. Async function with try-except
sample4 = """async def fetch_data(url):
    import aiohttp
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                return await response.json()
    except Exception as e:
        print(f"Error fetching data: {e}")
        return None
"""


# 5. Nested functions and closures
sample5 = """def create_multiplier(factor):
    def multiplier(x):
        return x * factor
    return multiplier
"""


# 6. Generator with yield
sample6 = """def fibonacci_generator(n):
    a, b = 0, 1
    count = 0
    while count < n:
        yield a
        a, b = b, a + b
        count += 1
"""


# 7. Dictionary comprehension with multiple conditions
sample7 = """def process_data(items):
    return {
        item['id']: {
            'name': item['name'].upper(),
            'valid': True
        }
        for item in items
        if item.get('active', False) and len(item.get('name', '')) > 3
    }
"""


# 8. Lambda functions and map/filter
sample8 = """def transform_numbers(numbers):
    squared = list(map(lambda x: x**2, numbers))
    filtered = list(filter(lambda x: x > 10, squared))
    return sorted(filtered, key=lambda x: x % 10)
"""


# 9. Context manager class
sample9 = """class FileManager:
    def __init__(self, filename, mode='r'):
        self.filename = filename
        self.mode = mode
        self.file = None
    
    def __enter__(self):
        self.file = open(self.filename, self.mode)
        return self.file
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.file:
            self.file.close()
"""


# 10. Decorator with arguments
sample10 = """def retry(max_attempts=3, delay=1):
    def decorator(func):
        import time
        import functools
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_attempts - 1:
                        raise
                    time.sleep(delay)
            return None
        return wrapper
    return decorator
"""


# 11. Bug: Mutable default argument
sample11 = """def append_to_list(item, target_list=[]):
    # BUG: Default mutable argument creates persistent state
    target_list.append(item)
    return target_list
"""

# 12. Bug: Variable scope issue
sample12 = """def calculate_totals(prices):
    # BUG: UnboundLocalError - total referenced before assignment
    for price in prices:
        total += price
    return total
"""

# 13. Bug: Incorrect indentation
sample13 = """def process_items(items):
    results = []
    for item in items:
        if item > 0:
            results.append(item * 2)
            # BUG: This line is always executed, not just when item > 0
        print(f"Processed {item}")
    return results
"""

# 14. Bug: Off-by-one error
sample14 = """def get_middle_elements(lst):
    # BUG: Doesn't handle even-length lists correctly
    middle = len(lst) // 2
    return lst[middle - 1:middle + 1]
"""

# 15. Bug: Modifying list while iterating
sample15 = """def remove_negatives(numbers):
    # BUG: Modifying list during iteration causes skipping
    for num in numbers:
        if num < 0:
            numbers.remove(num)
    return numbers
"""

# 16. Bug: Integer division in Python 2 style
sample16 = """def calculate_average(numbers):
    # BUG: In Python 2, this would do integer division
    return sum(numbers) / len(numbers) if numbers else 0
"""

# 17. Bug: Circular import structure
sample17 = """# file: module_a.py
from module_b import function_b

def function_a():
    return function_b() + 1

# file: module_b.py
from module_a import function_a  # BUG: Circular import

def function_b():
    return 42
"""

# 18. Bug: Race condition in threading
sample18 = """import threading

counter = 0

def increment():
    global counter
    # BUG: Race condition - not thread-safe
    temp = counter
    temp += 1
    counter = temp

threads = [threading.Thread(target=increment) for _ in range(100)]
for t in threads:
    t.start()
"""

# 19. Bug: SQL injection vulnerability
sample19 = """def get_user(username, connection):
    # BUG: SQL injection vulnerability
    query = f"SELECT * FROM users WHERE username = '{username}'"
    cursor = connection.cursor()
    cursor.execute(query)
    return cursor.fetchone()
"""

# 20. Bug: Memory leak with circular references
sample20 = """class Node:
    def __init__(self, value):
        self.value = value
        self.parent = None
        self.children = []
    
    def add_child(self, child):
        # BUG: Creates circular reference without weak refs
        child.parent = self
        self.children.append(child)
"""

# 21. REST API client with rate limiting
sample21 = """import time
import requests
from functools import wraps

class APIClient:
    def __init__(self, base_url, api_key, rate_limit=60):
        self.base_url = base_url
        self.api_key = api_key
        self.rate_limit = rate_limit
        self.last_request_time = 0
    
    def _rate_limit(self):
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        if time_since_last < (60 / self.rate_limit):
            time.sleep((60 / self.rate_limit) - time_since_last)
        self.last_request_time = time.time()
    
    def get(self, endpoint, params=None):
        self._rate_limit()
        headers = {'Authorization': f'Bearer {self.api_key}'}
        response = requests.get(f"{self.base_url}/{endpoint}", 
                              headers=headers, params=params)
        response.raise_for_status()
        return response.json()
"""

# 22. Data pipeline with validation
sample22 = """import pandas as pd
from datetime import datetime
import logging

class DataPipeline:
    def __init__(self, config):
        self.config = config
        self.logger = logging.getLogger(__name__)
    
    def validate_data(self, df):
        # Check for required columns
        required_cols = self.config['required_columns']
        missing = set(required_cols) - set(df.columns)
        if missing:
            raise ValueError(f"Missing columns: {missing}")
        
        # Check data types
        for col, dtype in self.config['dtypes'].items():
            if col in df.columns and df[col].dtype != dtype:
                df[col] = df[col].astype(dtype)
        
        # Remove duplicates
        df = df.drop_duplicates(subset=self.config.get('unique_keys', None))
        
        return df
    
    def transform_data(self, df):
        # Apply transformations
        for transform in self.config['transformations']:
            df = transform(df)
        return df
    
    def run(self, input_path):
        self.logger.info(f"Starting pipeline at {datetime.now()}")
        df = pd.read_csv(input_path)
        df = self.validate_data(df)
        df = self.transform_data(df)
        return df
"""

# 23. WebSocket server with authentication
sample23 = """import asyncio
import websockets
import json
import jwt
from datetime import datetime, timedelta

class WebSocketServer:
    def __init__(self, secret_key):
        self.secret_key = secret_key
        self.clients = {}
        
    def verify_token(self, token):
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=['HS256'])
            return payload['user_id']
        except jwt.InvalidTokenError:
            return None
    
    async def handle_client(self, websocket, path):
        # Authentication
        try:
            auth_msg = await asyncio.wait_for(websocket.recv(), timeout=5.0)
            auth_data = json.loads(auth_msg)
            user_id = self.verify_token(auth_data.get('token'))
            
            if not user_id:
                await websocket.send(json.dumps({'error': 'Invalid token'}))
                return
            
            self.clients[user_id] = websocket
            await websocket.send(json.dumps({'status': 'connected'}))
            
            # Handle messages
            async for message in websocket:
                data = json.loads(message)
                await self.process_message(user_id, data)
                
        except Exception as e:
            print(f"Error: {e}")
        finally:
            if user_id in self.clients:
                del self.clients[user_id]
    
    async def broadcast(self, message, exclude_user=None):
        tasks = []
        for user_id, ws in self.clients.items():
            if user_id != exclude_user:
                tasks.append(ws.send(json.dumps(message)))
        await asyncio.gather(*tasks, return_exceptions=True)
"""

# 24. Cache decorator with TTL
sample24 = """from functools import wraps
from datetime import datetime, timedelta
import pickle

class TTLCache:
    def __init__(self, ttl_seconds=300):
        self.ttl_seconds = ttl_seconds
        self.cache = {}
    
    def get(self, key):
        if key in self.cache:
            value, expiry = self.cache[key]
            if datetime.now() < expiry:
                return value
            else:
                del self.cache[key]
        return None
    
    def set(self, key, value):
        expiry = datetime.now() + timedelta(seconds=self.ttl_seconds)
        self.cache[key] = (value, expiry)

def cached(ttl_seconds=300):
    cache = TTLCache(ttl_seconds)
    
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Create cache key from function name and arguments
            key = pickle.dumps((func.__name__, args, kwargs))
            
            # Check cache
            result = cache.get(key)
            if result is not None:
                return result
            
            # Call function and cache result
            result = func(*args, **kwargs)
            cache.set(key, result)
            return result
        return wrapper
    return decorator
"""

# 25. Database connection pool
sample25 = """import psycopg2
from psycopg2 import pool
from contextlib import contextmanager
import logging

class DatabasePool:
    def __init__(self, minconn=1, maxconn=10, **kwargs):
        self.pool = psycopg2.pool.ThreadedConnectionPool(
            minconn, maxconn, **kwargs
        )
        self.logger = logging.getLogger(__name__)
    
    @contextmanager
    def get_connection(self):
        conn = None
        try:
            conn = self.pool.getconn()
            yield conn
            conn.commit()
        except Exception as e:
            if conn:
                conn.rollback()
            self.logger.error(f"Database error: {e}")
            raise
        finally:
            if conn:
                self.pool.putconn(conn)
    
    def execute_query(self, query, params=None):
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                return cursor.fetchall()
    
    def close(self):
        self.pool.closeall()
"""

# 26. Event-driven system with observers
sample26 = """from typing import Dict, List, Callable
from collections import defaultdict
import asyncio

class EventBus:
    def __init__(self):
        self._handlers: Dict[str, List[Callable]] = defaultdict(list)
        self._async_handlers: Dict[str, List[Callable]] = defaultdict(list)
    
    def on(self, event: str, handler: Callable):
        if asyncio.iscoroutinefunction(handler):
            self._async_handlers[event].append(handler)
        else:
            self._handlers[event].append(handler)
    
    def off(self, event: str, handler: Callable):
        if handler in self._handlers[event]:
            self._handlers[event].remove(handler)
        if handler in self._async_handlers[event]:
            self._async_handlers[event].remove(handler)
    
    async def emit(self, event: str, *args, **kwargs):
        # Handle sync handlers
        for handler in self._handlers[event]:
            handler(*args, **kwargs)
        
        # Handle async handlers
        tasks = [
            handler(*args, **kwargs)
            for handler in self._async_handlers[event]
        ]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

# Usage example
bus = EventBus()

@bus.on('user_login')
async def log_login(user_id):
    print(f"User {user_id} logged in")

@bus.on('user_login') 
def update_last_seen(user_id):
    # Update database
    pass
"""

# 27. File watcher with debouncing
sample27 = """import os
import time
from pathlib import Path
from threading import Timer
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class DebouncedFileHandler(FileSystemEventHandler):
    def __init__(self, callback, delay=1.0):
        self.callback = callback
        self.delay = delay
        self._timer = None
        self._pending_events = set()
    
    def _debounced_callback(self):
        events = list(self._pending_events)
        self._pending_events.clear()
        self.callback(events)
    
    def _handle_event(self, event):
        self._pending_events.add((event.event_type, event.src_path))
        
        if self._timer:
            self._timer.cancel()
        
        self._timer = Timer(self.delay, self._debounced_callback)
        self._timer.start()
    
    def on_modified(self, event):
        if not event.is_directory:
            self._handle_event(event)
    
    def on_created(self, event):
        self._handle_event(event)
    
    def on_deleted(self, event):
        self._handle_event(event)

def watch_directory(path, callback, patterns=None):
    handler = DebouncedFileHandler(callback)
    observer = Observer()
    observer.schedule(handler, path, recursive=True)
    observer.start()
    return observer
"""

# 28. Retry mechanism with exponential backoff
sample28 = """import time
import random
from typing import TypeVar, Callable, Optional, Type, Tuple

T = TypeVar('T')

def retry_with_backoff(
    func: Callable[..., T],
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    exceptions: Tuple[Type[Exception], ...] = (Exception,)
) -> T:
    '''
    Retry a function with exponential backoff
    '''
    attempt = 0
    delay = base_delay
    
    while attempt < max_retries:
        try:
            return func()
        except exceptions as e:
            attempt += 1
            
            if attempt == max_retries:
                raise
            
            # Calculate next delay
            delay = min(delay * exponential_base, max_delay)
            
            # Add jitter to prevent thundering herd
            if jitter:
                delay *= (0.5 + random.random())
            
            print(f"Attempt {attempt} failed: {e}. Retrying in {delay:.2f}s")
            time.sleep(delay)
"""

# 29. Configuration manager with environment support
sample29 = """import os
import json
import yaml
from typing import Any, Dict, Optional
from pathlib import Path

class ConfigManager:
    def __init__(self, config_path: str, env_prefix: str = "APP"):
        self.config_path = Path(config_path)
        self.env_prefix = env_prefix
        self._config = self._load_config()
        self._apply_env_overrides()
    
    def _load_config(self) -> Dict[str, Any]:
        if self.config_path.suffix == '.json':
            with open(self.config_path) as f:
                return json.load(f)
        elif self.config_path.suffix in ['.yml', '.yaml']:
            with open(self.config_path) as f:
                return yaml.safe_load(f)
        else:
            raise ValueError(f"Unsupported config format: {self.config_path.suffix}")
    
    def _apply_env_overrides(self):
        '''Override config values with environment variables'''
        for key in self._flatten_dict(self._config):
            env_var = f"{self.env_prefix}_{key.upper().replace('.', '_')}"
            if env_var in os.environ:
                self._set_nested(key, os.environ[env_var])
    
    def _flatten_dict(self, d: Dict, parent_key: str = '') -> Dict[str, Any]:
        items = []
        for k, v in d.items():
            new_key = f"{parent_key}.{k}" if parent_key else k
            if isinstance(v, dict):
                items.extend(self._flatten_dict(v, new_key).items())
            else:
                items.append((new_key, v))
        return dict(items)
    
    def _set_nested(self, key: str, value: str):
        keys = key.split('.')
        d = self._config
        for k in keys[:-1]:
            d = d.setdefault(k, {})
        
        # Try to preserve type
        if keys[-1] in d:
            old_value = d[keys[-1]]
            if isinstance(old_value, bool):
                d[keys[-1]] = value.lower() in ['true', '1', 'yes']
            elif isinstance(old_value, int):
                d[keys[-1]] = int(value)
            elif isinstance(old_value, float):
                d[keys[-1]] = float(value)
            else:
                d[keys[-1]] = value
        else:
            d[keys[-1]] = value
    
    def get(self, key: str, default: Any = None) -> Any:
        keys = key.split('.')
        d = self._config
        for k in keys:
            if isinstance(d, dict) and k in d:
                d = d[k]
            else:
                return default
        return d
"""

# 30. Task queue with priority
sample30 = """import heapq
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from queue import PriorityQueue
import uuid

@dataclass(order=True)
class Task:
    priority: int
    func: Callable = field(compare=False)
    args: tuple = field(default=(), compare=False)
    kwargs: dict = field(default_factory=dict, compare=False)
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()), compare=False)
    created_at: float = field(default_factory=time.time, compare=False)

class PriorityTaskQueue:
    def __init__(self, num_workers: int = 4):
        self.queue = PriorityQueue()
        self.workers = []
        self.running = False
        self.num_workers = num_workers
        self.results = {}
        self._lock = threading.Lock()
    
    def submit(self, func: Callable, *args, priority: int = 5, **kwargs) -> str:
        task = Task(priority=priority, func=func, args=args, kwargs=kwargs)
        self.queue.put(task)
        return task.task_id
    
    def _worker(self):
        while self.running:
            try:
                task = self.queue.get(timeout=1)
                try:
                    result = task.func(*task.args, **task.kwargs)
                    with self._lock:
                        self.results[task.task_id] = {
                            'status': 'completed',
                            'result': result,
                            'completed_at': time.time()
                        }
                except Exception as e:
                    with self._lock:
                        self.results[task.task_id] = {
                            'status': 'failed',
                            'error': str(e),
                            'completed_at': time.time()
                        }
                finally:
                    self.queue.task_done()
            except:
                continue
    
    def start(self):
        self.running = True
        for _ in range(self.num_workers):
            worker = threading.Thread(target=self._worker)
            worker.daemon = True
            worker.start()
            self.workers.append(worker)
    
    def stop(self):
        self.running = False
        for worker in self.workers:
            worker.join()
    
    def get_result(self, task_id: str, timeout: Optional[float] = None) -> Any:
        start_time = time.time()
        while True:
            with self._lock:
                if task_id in self.results:
                    return self.results[task_id]
            
            if timeout and (time.time() - start_time) > timeout:
                raise TimeoutError(f"Task {task_id} did not complete within {timeout}s")
            
            time.sleep(0.1)
"""