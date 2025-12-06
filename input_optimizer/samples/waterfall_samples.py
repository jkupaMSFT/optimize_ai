# TINY TIER SAMPLES (0-50 tokens)

# 1. Minimal function (~5 tokens)
sample1 = """def add(a, b):
    return a + b"""


# 2. Simple lambda (~8 tokens)
sample2 = """square = lambda x: x * x"""


# 3. Basic variable assignment (~12 tokens)
sample3 = """PI = 3.14159
def area(r):
    return PI * r ** 2"""


# 4. Short list comprehension (~15 tokens)
sample4 = """def evens(nums):
    return [x for x in nums if x % 2 == 0]"""


# 5. Simple class (~25 tokens)
sample5 = """class Point:
    def __init__(self, x, y):
        self.x = x
        self.y = y"""


# SMALL TIER SAMPLES (51-5000 tokens)

# 6. Function with docstring and error handling (~80 tokens)
sample6 = """def safe_divide(a, b):
    '''Safely divide two numbers, handling division by zero.'''
    try:
        return a / b
    except ZeroDivisionError:
        return float('inf') if a > 0 else float('-inf') if a < 0 else float('nan')"""


# 7. Class with properties (~150 tokens)
sample7 = """class Person:
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
    
    @age.setter
    def age(self, value):
        if value < 0:
            raise ValueError("Age cannot be negative")
        self._age = value
    
    def __str__(self):
        return f"Person(name='{self.full_name}', age={self.age})"
"""


# 8. Async function with error handling (~200 tokens)
sample8 = """import asyncio
import aiohttp

async def fetch_data(url, timeout=10):
    '''Fetch data from URL with timeout and error handling.'''
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
            async with session.get(url) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    raise aiohttp.ClientResponseError(
                        request_info=response.request_info,
                        history=response.history,
                        status=response.status
                    )
    except asyncio.TimeoutError:
        return {'error': 'Request timed out'}
    except Exception as e:
        return {'error': f'Failed to fetch data: {str(e)}'}
"""


# 9. Generator with yield and complex logic (~300 tokens)
sample9 = """def fibonacci_sequence(max_value=None, max_count=None):
    '''Generate Fibonacci sequence with optional limits.'''
    a, b = 0, 1
    count = 0
    
    while True:
        if max_count and count >= max_count:
            break
        if max_value and a > max_value:
            break
            
        yield a
        a, b = b, a + b
        count += 1

def prime_fibonacci(limit=1000):
    '''Generate prime numbers from Fibonacci sequence.'''
    def is_prime(n):
        if n < 2:
            return False
        for i in range(2, int(n ** 0.5) + 1):
            if n % i == 0:
                return False
        return True
    
    for fib in fibonacci_sequence(max_value=limit):
        if is_prime(fib):
            yield fib
"""


# 10. Context manager with resource handling (~400 tokens)
sample10 = """import os
import tempfile
from contextlib import contextmanager

class FileManager:
    def __init__(self, filename, mode='r', encoding='utf-8'):
        self.filename = filename
        self.mode = mode
        self.encoding = encoding
        self.file = None
    
    def __enter__(self):
        try:
            self.file = open(self.filename, self.mode, encoding=self.encoding)
            return self.file
        except IOError as e:
            raise IOError(f"Failed to open {self.filename}: {e}")
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.file:
            self.file.close()
        if exc_type:
            print(f"Exception occurred: {exc_val}")
        return False

@contextmanager
def temporary_file(suffix='.tmp', content=None):
    '''Create a temporary file with optional content.'''
    fd, path = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(fd, 'w') as f:
            if content:
                f.write(content)
        yield path
    finally:
        if os.path.exists(path):
            os.unlink(path)
"""


# 11. Decorator with logging and timing (~600 tokens)
sample11 = """import functools
import time
import logging

def retry_on_failure(max_attempts=3, delay=1.0, backoff_factor=2.0):
    '''Decorator that retries function calls on failure with exponential backoff.'''
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            current_delay = delay
            
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt == max_attempts - 1:
                        break
                    
                    logging.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {current_delay}s...")
                    time.sleep(current_delay)
                    current_delay *= backoff_factor
            
            raise last_exception
        return wrapper
    return decorator

@retry_on_failure(max_attempts=5, delay=0.5)
def unreliable_api_call():
    import random
    if random.random() < 0.7:
        raise ConnectionError("API temporarily unavailable")
    return {"status": "success", "data": "important_data"}
"""


# 12. Data processing pipeline (~800 tokens)
sample12 = """import json
import csv
from datetime import datetime
from typing import List, Dict, Any, Optional

class DataProcessor:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.processed_count = 0
        self.error_count = 0
        
    def validate_record(self, record: Dict[str, Any]) -> bool:
        '''Validate a single record against configuration rules.'''
        required_fields = self.config.get('required_fields', [])
        for field in required_fields:
            if field not in record or record[field] is None:
                return False
        
        # Type validation
        type_rules = self.config.get('type_validation', {})
        for field, expected_type in type_rules.items():
            if field in record and not isinstance(record[field], expected_type):
                try:
                    record[field] = expected_type(record[field])
                except (ValueError, TypeError):
                    return False
        
        return True
    
    def transform_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        '''Apply transformations to a record.'''
        transformed = record.copy()
        
        # Apply field mappings
        field_mappings = self.config.get('field_mappings', {})
        for old_field, new_field in field_mappings.items():
            if old_field in transformed:
                transformed[new_field] = transformed.pop(old_field)
        
        # Apply value transformations
        transformations = self.config.get('transformations', {})
        for field, transform_func in transformations.items():
            if field in transformed:
                transformed[field] = transform_func(transformed[field])
        
        # Add metadata
        transformed['processed_at'] = datetime.now().isoformat()
        transformed['processor_version'] = '1.0'
        
        return transformed
    
    def process_batch(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        '''Process a batch of records.'''
        results = []
        
        for record in records:
            try:
                if self.validate_record(record):
                    transformed = self.transform_record(record)
                    results.append(transformed)
                    self.processed_count += 1
                else:
                    self.error_count += 1
            except Exception as e:
                self.error_count += 1
                print(f"Error processing record: {e}")
        
        return results
"""


# MEDIUM TIER SAMPLES (5000-25000 tokens)

# 13. Complex web scraper with rate limiting (~2000 tokens)
sample13 = """import asyncio
import aiohttp
import time
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from typing import List, Dict, Set, Optional
import logging

class WebScraper:
    def __init__(self, base_url: str, rate_limit: float = 1.0, max_concurrent: int = 5):
        self.base_url = base_url
        self.rate_limit = rate_limit
        self.max_concurrent = max_concurrent
        self.visited_urls: Set[str] = set()
        self.scraped_data: List[Dict] = []
        self.session: Optional[aiohttp.ClientSession] = None
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.last_request_time = 0
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def _rate_limited_request(self, url: str) -> Optional[str]:
        '''Make a rate-limited HTTP request.'''
        async with self.semaphore:
            # Ensure rate limiting
            current_time = time.time()
            time_since_last = current_time - self.last_request_time
            if time_since_last < self.rate_limit:
                await asyncio.sleep(self.rate_limit - time_since_last)
            
            self.last_request_time = time.time()
            
            try:
                async with self.session.get(url, timeout=10) as response:
                    if response.status == 200:
                        return await response.text()
                    else:
                        logging.warning(f"HTTP {response.status} for {url}")
                        return None
            except Exception as e:
                logging.error(f"Error fetching {url}: {e}")
                return None
    
    def extract_links(self, html: str, base_url: str) -> List[str]:
        '''Extract all links from HTML content.'''
        soup = BeautifulSoup(html, 'html.parser')
        links = []
        
        for link in soup.find_all('a', href=True):
            href = link['href']
            full_url = urljoin(base_url, href)
            
            # Only include links from the same domain
            if urlparse(full_url).netloc == urlparse(base_url).netloc:
                links.append(full_url)
        
        return links
    
    def extract_data(self, html: str, url: str) -> Dict:
        '''Extract structured data from HTML.'''
        soup = BeautifulSoup(html, 'html.parser')
        
        # Extract title
        title_tag = soup.find('title')
        title = title_tag.text.strip() if title_tag else 'No Title'
        
        # Extract meta description
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        description = meta_desc.get('content', '') if meta_desc else ''
        
        # Extract headings
        headings = [h.text.strip() for h in soup.find_all(['h1', 'h2', 'h3'])]
        
        # Extract paragraphs
        paragraphs = [p.text.strip() for p in soup.find_all('p') if p.text.strip()]
        
        # Extract images
        images = [img.get('src') for img in soup.find_all('img') if img.get('src')]
        
        return {
            'url': url,
            'title': title,
            'description': description,
            'headings': headings,
            'paragraphs': paragraphs[:5],  # Limit to first 5 paragraphs
            'image_count': len(images),
            'scraped_at': time.time()
        }
    
    async def scrape_page(self, url: str) -> Optional[Dict]:
        '''Scrape a single page and extract data.'''
        if url in self.visited_urls:
            return None
        
        self.visited_urls.add(url)
        html = await self._rate_limited_request(url)
        
        if html:
            data = self.extract_data(html, url)
            links = self.extract_links(html, url)
            data['outbound_links'] = len(links)
            return data
        
        return None
    
    async def scrape_site(self, max_pages: int = 50) -> List[Dict]:
        '''Scrape multiple pages from the site.'''
        urls_to_visit = [self.base_url]
        
        while urls_to_visit and len(self.scraped_data) < max_pages:
            # Process URLs in batches
            batch_size = min(self.max_concurrent, len(urls_to_visit))
            current_batch = urls_to_visit[:batch_size]
            urls_to_visit = urls_to_visit[batch_size:]
            
            # Scrape batch concurrently
            tasks = [self.scrape_page(url) for url in current_batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for result in results:
                if isinstance(result, dict):
                    self.scraped_data.append(result)
                    
                    # Find new URLs to visit (implement breadth-first crawling)
                    html = await self._rate_limited_request(result['url'])
                    if html:
                        new_links = self.extract_links(html, result['url'])
                        for link in new_links:
                            if link not in self.visited_urls and link not in urls_to_visit:
                                urls_to_visit.append(link)
        
        return self.scraped_data
"""


# 14. Machine learning model trainer with cross-validation (~3000 tokens)
sample14 = """import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split, cross_val_score, GridSearchCV
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.svm import SVC
from sklearn.metrics import classification_report, confusion_matrix, roc_auc_score
from sklearn.pipeline import Pipeline
import joblib
import json
from typing import Dict, List, Tuple, Any, Optional
import logging

class MLModelTrainer:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.models = {}
        self.scalers = {}
        self.encoders = {}
        self.best_model = None
        self.feature_importance = {}
        self.training_history = []
        
    def load_data(self, file_path: str) -> pd.DataFrame:
        '''Load data from various file formats.'''
        if file_path.endswith('.csv'):
            return pd.read_csv(file_path)
        elif file_path.endswith('.json'):
            return pd.read_json(file_path)
        elif file_path.endswith(('.xls', '.xlsx')):
            return pd.read_excel(file_path)
        else:
            raise ValueError(f"Unsupported file format: {file_path}")
    
    def preprocess_data(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        '''Preprocess the data with cleaning and feature engineering.'''
        preprocessing_info = {}
        df_processed = df.copy()
        
        # Handle missing values
        missing_strategy = self.config.get('missing_strategy', 'drop')
        if missing_strategy == 'drop':
            original_shape = df_processed.shape
            df_processed = df_processed.dropna()
            preprocessing_info['rows_dropped'] = original_shape[0] - df_processed.shape[0]
        elif missing_strategy == 'fill':
            fill_values = self.config.get('fill_values', {})
            for column, fill_value in fill_values.items():
                if column in df_processed.columns:
                    df_processed[column].fillna(fill_value, inplace=True)
        
        # Encode categorical variables
        categorical_columns = self.config.get('categorical_columns', [])
        for column in categorical_columns:
            if column in df_processed.columns:
                if column not in self.encoders:
                    self.encoders[column] = LabelEncoder()
                    df_processed[column] = self.encoders[column].fit_transform(df_processed[column])
                else:
                    df_processed[column] = self.encoders[column].transform(df_processed[column])
        
        # Feature engineering
        feature_engineering = self.config.get('feature_engineering', [])
        for feature_config in feature_engineering:
            feature_type = feature_config.get('type')
            if feature_type == 'polynomial':
                base_columns = feature_config.get('columns', [])
                degree = feature_config.get('degree', 2)
                for col in base_columns:
                    if col in df_processed.columns:
                        df_processed[f"{col}_poly_{degree}"] = df_processed[col] ** degree
            
            elif feature_type == 'interaction':
                col1, col2 = feature_config.get('columns', [])
                if col1 in df_processed.columns and col2 in df_processed.columns:
                    df_processed[f"{col1}_{col2}_interaction"] = df_processed[col1] * df_processed[col2]
        
        # Remove outliers
        outlier_method = self.config.get('outlier_method', None)
        if outlier_method == 'iqr':
            numeric_columns = df_processed.select_dtypes(include=[np.number]).columns
            for column in numeric_columns:
                Q1 = df_processed[column].quantile(0.25)
                Q3 = df_processed[column].quantile(0.75)
                IQR = Q3 - Q1
                lower_bound = Q1 - 1.5 * IQR
                upper_bound = Q3 + 1.5 * IQR
                df_processed = df_processed[(df_processed[column] >= lower_bound) & (df_processed[column] <= upper_bound)]
        
        preprocessing_info['final_shape'] = df_processed.shape
        return df_processed, preprocessing_info
    
    def prepare_features_target(self, df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
        '''Separate features and target variable.'''
        target_column = self.config['target_column']
        feature_columns = self.config.get('feature_columns', [])
        
        if not feature_columns:
            feature_columns = [col for col in df.columns if col != target_column]
        
        X = df[feature_columns].values
        y = df[target_column].values
        
        # Scale features
        if 'scaler' not in self.__dict__ or self.scaler is None:
            self.scaler = StandardScaler()
            X = self.scaler.fit_transform(X)
        else:
            X = self.scaler.transform(X)
        
        return X, y
    
    def initialize_models(self) -> Dict[str, Any]:
        '''Initialize different ML models for comparison.'''
        models = {
            'logistic_regression': LogisticRegression(random_state=42),
            'random_forest': RandomForestClassifier(random_state=42, n_estimators=100),
            'gradient_boosting': GradientBoostingClassifier(random_state=42),
            'svm': SVC(random_state=42, probability=True)
        }
        
        # Add custom models from config
        custom_models = self.config.get('custom_models', {})
        models.update(custom_models)
        
        return models
    
    def hyperparameter_tuning(self, model, param_grid: Dict, X_train: np.ndarray, y_train: np.ndarray):
        '''Perform hyperparameter tuning using GridSearchCV.'''
        cv_folds = self.config.get('cv_folds', 5)
        scoring = self.config.get('scoring', 'accuracy')
        
        grid_search = GridSearchCV(
            model, param_grid, cv=cv_folds, scoring=scoring, n_jobs=-1, verbose=1
        )
        grid_search.fit(X_train, y_train)
        
        return grid_search.best_estimator_, grid_search.best_params_, grid_search.best_score_
    
    def train_models(self, X_train: np.ndarray, y_train: np.ndarray, X_val: np.ndarray, y_val: np.ndarray):
        '''Train multiple models and compare their performance.'''
        models = self.initialize_models()
        results = {}
        
        hyperparameter_grids = self.config.get('hyperparameter_grids', {})
        
        for name, model in models.items():
            logging.info(f"Training {name}...")
            
            # Hyperparameter tuning if grid provided
            if name in hyperparameter_grids:
                tuned_model, best_params, best_score = self.hyperparameter_tuning(
                    model, hyperparameter_grids[name], X_train, y_train
                )
                model = tuned_model
            else:
                model.fit(X_train, y_train)
            
            # Cross-validation
            cv_scores = cross_val_score(model, X_train, y_train, cv=5)
            
            # Validation performance
            val_predictions = model.predict(X_val)
            val_probabilities = model.predict_proba(X_val)[:, 1] if hasattr(model, 'predict_proba') else None
            
            # Calculate metrics
            val_accuracy = model.score(X_val, y_val)
            val_auc = roc_auc_score(y_val, val_probabilities) if val_probabilities is not None else None
            
            results[name] = {
                'model': model,
                'cv_mean': cv_scores.mean(),
                'cv_std': cv_scores.std(),
                'val_accuracy': val_accuracy,
                'val_auc': val_auc,
                'best_params': getattr(model, 'best_params_', None)
            }
            
            # Store feature importance if available
            if hasattr(model, 'feature_importances_'):
                self.feature_importance[name] = model.feature_importances_
            
            logging.info(f"{name} - CV: {cv_scores.mean():.4f} (+/- {cv_scores.std()*2:.4f}), Val Acc: {val_accuracy:.4f}")
        
        # Select best model
        best_model_name = max(results.keys(), key=lambda k: results[k]['val_accuracy'])
        self.best_model = results[best_model_name]['model']
        
        logging.info(f"Best model: {best_model_name}")
        
        return results
    
    def evaluate_model(self, model, X_test: np.ndarray, y_test: np.ndarray) -> Dict[str, Any]:
        '''Comprehensive model evaluation.'''
        predictions = model.predict(X_test)
        probabilities = model.predict_proba(X_test)[:, 1] if hasattr(model, 'predict_proba') else None
        
        # Calculate metrics
        accuracy = model.score(X_test, y_test)
        auc = roc_auc_score(y_test, probabilities) if probabilities is not None else None
        
        # Classification report
        class_report = classification_report(y_test, predictions, output_dict=True)
        
        # Confusion matrix
        conf_matrix = confusion_matrix(y_test, predictions).tolist()
        
        return {
            'accuracy': accuracy,
            'auc': auc,
            'classification_report': class_report,
            'confusion_matrix': conf_matrix,
            'predictions': predictions.tolist(),
            'probabilities': probabilities.tolist() if probabilities is not None else None
        }
    
    def save_model(self, model, file_path: str):
        '''Save trained model to disk.'''
        joblib.dump({
            'model': model,
            'scaler': self.scaler,
            'encoders': self.encoders,
            'config': self.config
        }, file_path)
        
        logging.info(f"Model saved to {file_path}")
    
    def load_model(self, file_path: str):
        '''Load trained model from disk.'''
        loaded_data = joblib.load(file_path)
        self.best_model = loaded_data['model']
        self.scaler = loaded_data['scaler']
        self.encoders = loaded_data['encoders']
        self.config = loaded_data['config']
        
        logging.info(f"Model loaded from {file_path}")
    
    def full_training_pipeline(self, data_path: str, test_size: float = 0.2, val_size: float = 0.2):
        '''Complete training pipeline from data loading to model evaluation.'''
        # Load and preprocess data
        df = self.load_data(data_path)
        df_processed, preprocessing_info = self.preprocess_data(df)
        
        # Prepare features and target
        X, y = self.prepare_features_target(df_processed)
        
        # Train-validation-test split
        X_temp, X_test, y_temp, y_test = train_test_split(X, y, test_size=test_size, random_state=42)
        val_size_adjusted = val_size / (1 - test_size)
        X_train, X_val, y_train, y_val = train_test_split(X_temp, y_temp, test_size=val_size_adjusted, random_state=42)
        
        # Train models
        training_results = self.train_models(X_train, y_train, X_val, y_val)
        
        # Evaluate best model on test set
        test_results = self.evaluate_model(self.best_model, X_test, y_test)
        
        # Store training history
        self.training_history.append({
            'preprocessing_info': preprocessing_info,
            'training_results': {k: {key: val for key, val in v.items() if key != 'model'} for k, v in training_results.items()},
            'test_results': test_results,
            'timestamp': pd.Timestamp.now().isoformat()
        })
        
        return {
            'preprocessing_info': preprocessing_info,
            'training_results': training_results,
            'test_results': test_results
        }
"""


# LARGE TIER SAMPLES (25000-60000 tokens)

# 15. Complete REST API with authentication, database, and caching (~8000 tokens)
sample15 = """import asyncio
import hashlib
import jwt
import redis
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from fastapi import FastAPI, HTTPException, Depends, status, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, EmailStr, validator
import databases
import sqlalchemy
from sqlalchemy import create_engine, MetaData, Table, Column, Integer, String, DateTime, Boolean, Text, ForeignKey
from sqlalchemy.sql import select, insert, update, delete
import bcrypt
from contextlib import asynccontextmanager

# Database configuration
DATABASE_URL = "postgresql://user:password@localhost/dbname"
database = databases.Database(DATABASE_URL)
metadata = MetaData()

# Tables
users_table = Table(
    "users",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("email", String(255), unique=True, index=True),
    Column("username", String(100), unique=True, index=True),
    Column("hashed_password", String(255)),
    Column("full_name", String(255)),
    Column("is_active", Boolean, default=True),
    Column("is_superuser", Boolean, default=False),
    Column("created_at", DateTime, default=datetime.utcnow),
    Column("updated_at", DateTime, default=datetime.utcnow, onupdate=datetime.utcnow),
)

posts_table = Table(
    "posts",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("title", String(255), index=True),
    Column("content", Text),
    Column("author_id", Integer, ForeignKey("users.id")),
    Column("is_published", Boolean, default=False),
    Column("created_at", DateTime, default=datetime.utcnow),
    Column("updated_at", DateTime, default=datetime.utcnow, onupdate=datetime.utcnow),
)

comments_table = Table(
    "comments",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("content", Text),
    Column("post_id", Integer, ForeignKey("posts.id")),
    Column("author_id", Integer, ForeignKey("users.id")),
    Column("created_at", DateTime, default=datetime.utcnow),
)

# Pydantic models
class UserBase(BaseModel):
    email: EmailStr
    username: str
    full_name: str
    
    @validator('username')
    def username_alphanumeric(cls, v):
        assert v.isalnum(), 'Username must be alphanumeric'
        return v

class UserCreate(UserBase):
    password: str
    
    @validator('password')
    def password_strength(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        if not any(c.isupper() for c in v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not any(c.islower() for c in v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not any(c.isdigit() for c in v):
            raise ValueError('Password must contain at least one digit')
        return v

class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    username: Optional[str] = None
    full_name: Optional[str] = None
    password: Optional[str] = None

class UserInDB(UserBase):
    id: int
    is_active: bool
    is_superuser: bool
    created_at: datetime
    updated_at: datetime

class PostBase(BaseModel):
    title: str
    content: str
    is_published: bool = False

class PostCreate(PostBase):
    pass

class PostUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    is_published: Optional[bool] = None

class PostInDB(PostBase):
    id: int
    author_id: int
    created_at: datetime
    updated_at: datetime

class CommentBase(BaseModel):
    content: str

class CommentCreate(CommentBase):
    post_id: int

class CommentInDB(CommentBase):
    id: int
    post_id: int
    author_id: int
    created_at: datetime

class Token(BaseModel):
    access_token: str
    token_type: str
    expires_in: int

# Authentication
SECRET_KEY = "your-secret-key-here"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

security = HTTPBearer()

class AuthManager:
    def __init__(self, secret_key: str, algorithm: str = "HS256"):
        self.secret_key = secret_key
        self.algorithm = algorithm
    
    def hash_password(self, password: str) -> str:
        """Hash a password using bcrypt."""
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
        return hashed.decode('utf-8')
    
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash."""
        return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
    
    def create_access_token(self, data: dict, expires_delta: Optional[timedelta] = None):
        """Create a JWT access token."""
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=15)
        
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        return encoded_jwt
    
    def verify_token(self, token: str) -> Optional[dict]:
        """Verify and decode a JWT token."""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            return payload
        except jwt.PyJWTError:
            return None

auth_manager = AuthManager(SECRET_KEY, ALGORITHM)

# Cache manager
class CacheManager:
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis_client = redis.from_url(redis_url, decode_responses=True)
    
    async def get(self, key: str) -> Optional[str]:
        """Get value from cache."""
        try:
            return self.redis_client.get(key)
        except redis.RedisError:
            return None
    
    async def set(self, key: str, value: str, expire: int = 3600):
        """Set value in cache with expiration."""
        try:
            self.redis_client.setex(key, expire, value)
        except redis.RedisError:
            pass
    
    async def delete(self, key: str):
        """Delete key from cache."""
        try:
            self.redis_client.delete(key)
        except redis.RedisError:
            pass
    
    async def get_user_cache_key(self, user_id: int) -> str:
        """Generate cache key for user data."""
        return f"user:{user_id}"
    
    async def get_post_cache_key(self, post_id: int) -> str:
        """Generate cache key for post data."""
        return f"post:{post_id}"

cache_manager = CacheManager()

# Database operations
class UserRepository:
    def __init__(self, database: databases.Database):
        self.database = database
    
    async def create_user(self, user_data: UserCreate) -> UserInDB:
        """Create a new user."""
        hashed_password = auth_manager.hash_password(user_data.password)
        
        query = insert(users_table).values(
            email=user_data.email,
            username=user_data.username,
            full_name=user_data.full_name,
            hashed_password=hashed_password
        )
        
        user_id = await self.database.execute(query)
        return await self.get_user_by_id(user_id)
    
    async def get_user_by_id(self, user_id: int) -> Optional[UserInDB]:
        """Get user by ID."""
        # Try cache first
        cache_key = await cache_manager.get_user_cache_key(user_id)
        cached_user = await cache_manager.get(cache_key)
        
        if cached_user:
            import json
            user_data = json.loads(cached_user)
            return UserInDB(**user_data)
        
        # Query database
        query = select(users_table).where(users_table.c.id == user_id)
        result = await self.database.fetch_one(query)
        
        if result:
            user = UserInDB(**result)
            # Cache the result
            import json
            await cache_manager.set(cache_key, json.dumps(user.dict()), expire=1800)
            return user
        
        return None
    
    async def get_user_by_email(self, email: str) -> Optional[UserInDB]:
        """Get user by email."""
        query = select(users_table).where(users_table.c.email == email)
        result = await self.database.fetch_one(query)
        return UserInDB(**result) if result else None
    
    async def get_user_by_username(self, username: str) -> Optional[UserInDB]:
        """Get user by username."""
        query = select(users_table).where(users_table.c.username == username)
        result = await self.database.fetch_one(query)
        return UserInDB(**result) if result else None
    
    async def update_user(self, user_id: int, user_data: UserUpdate) -> Optional[UserInDB]:
        """Update user data."""
        update_data = {k: v for k, v in user_data.dict().items() if v is not None}
        
        if 'password' in update_data:
            update_data['hashed_password'] = auth_manager.hash_password(update_data.pop('password'))
        
        update_data['updated_at'] = datetime.utcnow()
        
        query = update(users_table).where(users_table.c.id == user_id).values(**update_data)
        await self.database.execute(query)
        
        # Invalidate cache
        cache_key = await cache_manager.get_user_cache_key(user_id)
        await cache_manager.delete(cache_key)
        
        return await self.get_user_by_id(user_id)
    
    async def delete_user(self, user_id: int) -> bool:
        """Delete user."""
        query = delete(users_table).where(users_table.c.id == user_id)
        result = await self.database.execute(query)
        
        # Invalidate cache
        cache_key = await cache_manager.get_user_cache_key(user_id)
        await cache_manager.delete(cache_key)
        
        return result > 0
    
    async def list_users(self, skip: int = 0, limit: int = 100) -> List[UserInDB]:
        """List users with pagination."""
        query = select(users_table).offset(skip).limit(limit)
        results = await self.database.fetch_all(query)
        return [UserInDB(**result) for result in results]

class PostRepository:
    def __init__(self, database: databases.Database):
        self.database = database
    
    async def create_post(self, post_data: PostCreate, author_id: int) -> PostInDB:
        """Create a new post."""
        query = insert(posts_table).values(
            title=post_data.title,
            content=post_data.content,
            is_published=post_data.is_published,
            author_id=author_id
        )
        
        post_id = await self.database.execute(query)
        return await self.get_post_by_id(post_id)
    
    async def get_post_by_id(self, post_id: int) -> Optional[PostInDB]:
        """Get post by ID."""
        # Try cache first
        cache_key = await cache_manager.get_post_cache_key(post_id)
        cached_post = await cache_manager.get(cache_key)
        
        if cached_post:
            import json
            post_data = json.loads(cached_post)
            return PostInDB(**post_data)
        
        # Query database
        query = select(posts_table).where(posts_table.c.id == post_id)
        result = await self.database.fetch_one(query)
        
        if result:
            post = PostInDB(**result)
            # Cache the result
            import json
            await cache_manager.set(cache_key, json.dumps(post.dict()), expire=1800)
            return post
        
        return None
    
    async def update_post(self, post_id: int, post_data: PostUpdate, user_id: int) -> Optional[PostInDB]:
        """Update post data."""
        # Check if user owns the post
        existing_post = await self.get_post_by_id(post_id)
        if not existing_post or existing_post.author_id != user_id:
            return None
        
        update_data = {k: v for k, v in post_data.dict().items() if v is not None}
        update_data['updated_at'] = datetime.utcnow()
        
        query = update(posts_table).where(posts_table.c.id == post_id).values(**update_data)
        await self.database.execute(query)
        
        # Invalidate cache
        cache_key = await cache_manager.get_post_cache_key(post_id)
        await cache_manager.delete(cache_key)
        
        return await self.get_post_by_id(post_id)
    
    async def delete_post(self, post_id: int, user_id: int) -> bool:
        """Delete post."""
        # Check if user owns the post
        existing_post = await self.get_post_by_id(post_id)
        if not existing_post or existing_post.author_id != user_id:
            return False
        
        query = delete(posts_table).where(posts_table.c.id == post_id)
        result = await self.database.execute(query)
        
        # Invalidate cache
        cache_key = await cache_manager.get_post_cache_key(post_id)
        await cache_manager.delete(cache_key)
        
        return result > 0
    
    async def list_posts(self, skip: int = 0, limit: int = 100, published_only: bool = True) -> List[PostInDB]:
        """List posts with pagination."""
        query = select(posts_table)
        
        if published_only:
            query = query.where(posts_table.c.is_published == True)
        
        query = query.offset(skip).limit(limit).order_by(posts_table.c.created_at.desc())
        results = await self.database.fetch_all(query)
        return [PostInDB(**result) for result in results]
    
    async def get_posts_by_author(self, author_id: int, skip: int = 0, limit: int = 100) -> List[PostInDB]:
        """Get posts by author."""
        query = select(posts_table).where(posts_table.c.author_id == author_id).offset(skip).limit(limit).order_by(posts_table.c.created_at.desc())
        results = await self.database.fetch_all(query)
        return [PostInDB(**result) for result in results]

# Dependencies
async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> UserInDB:
    """Get current authenticated user."""
    token = credentials.credentials
    payload = auth_manager.verify_token(token)
    
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user_repo = UserRepository(database)
    user = await user_repo.get_user_by_id(int(user_id))
    
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    
    return user

async def get_current_active_superuser(current_user: UserInDB = Depends(get_current_user)) -> UserInDB:
    """Get current authenticated superuser."""
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    return current_user

# Application lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await database.connect()
    logging.info("Database connected")
    
    yield
    
    # Shutdown
    await database.disconnect()
    logging.info("Database disconnected")

# FastAPI app
app = FastAPI(
    title="Blog API",
    description="A comprehensive blog API with authentication, caching, and rate limiting",
    version="1.0.0",
    lifespan=lifespan
)

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["localhost", "127.0.0.1", "*.yourdomain.com"]
)

# Rate limiting middleware
class RateLimitMiddleware:
    def __init__(self, app, calls: int = 100, period: int = 60):
        self.app = app
        self.calls = calls
        self.period = period
    
    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            client_ip = scope["client"][0]
            cache_key = f"rate_limit:{client_ip}"
            
            current_requests = await cache_manager.get(cache_key)
            if current_requests is None:
                await cache_manager.set(cache_key, "1", expire=self.period)
            else:
                requests_count = int(current_requests)
                if requests_count >= self.calls:
                    response = {
                        "type": "http.response.start",
                        "status": 429,
                        "headers": [(b"content-type", b"application/json")],
                    }
                    await send(response)
                    await send({
                        "type": "http.response.body",
                        "body": b'{"detail": "Rate limit exceeded"}',
                    })
                    return
                else:
                    await cache_manager.set(cache_key, str(requests_count + 1), expire=self.period)
        
        await self.app(scope, receive, send)

# app = RateLimitMiddleware(app, calls=100, period=60)

# Routes
@app.post("/auth/register", response_model=UserInDB, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserCreate):
    """Register a new user."""
    user_repo = UserRepository(database)
    
    # Check if user already exists
    existing_user = await user_repo.get_user_by_email(user_data.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    existing_user = await user_repo.get_user_by_username(user_data.username)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already taken"
        )
    
    return await user_repo.create_user(user_data)

@app.post("/auth/login", response_model=Token)
async def login(email: str, password: str):
    """Authenticate user and return access token."""
    user_repo = UserRepository(database)
    user = await user_repo.get_user_by_email(email)
    
    if not user or not auth_manager.verify_password(password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth_manager.create_access_token(
        data={"sub": str(user.id)}, expires_delta=access_token_expires
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60
    }

@app.get("/users/me", response_model=UserInDB)
async def read_users_me(current_user: UserInDB = Depends(get_current_user)):
    """Get current user information."""
    return current_user

@app.put("/users/me", response_model=UserInDB)
async def update_users_me(user_update: UserUpdate, current_user: UserInDB = Depends(get_current_user)):
    """Update current user information."""
    user_repo = UserRepository(database)
    return await user_repo.update_user(current_user.id, user_update)

@app.get("/posts", response_model=List[PostInDB])
async def read_posts(skip: int = 0, limit: int = 100):
    """Get list of published posts."""
    post_repo = PostRepository(database)
    return await post_repo.list_posts(skip=skip, limit=limit, published_only=True)

@app.post("/posts", response_model=PostInDB, status_code=status.HTTP_201_CREATED)
async def create_post(post_data: PostCreate, current_user: UserInDB = Depends(get_current_user)):
    """Create a new post."""
    post_repo = PostRepository(database)
    return await post_repo.create_post(post_data, current_user.id)

@app.get("/posts/{post_id}", response_model=PostInDB)
async def read_post(post_id: int):
    """Get a specific post."""
    post_repo = PostRepository(database)
    post = await post_repo.get_post_by_id(post_id)
    
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found"
        )
    
    if not post.is_published:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found"
        )
    
    return post

@app.put("/posts/{post_id}", response_model=PostInDB)
async def update_post(post_id: int, post_data: PostUpdate, current_user: UserInDB = Depends(get_current_user)):
    """Update a post."""
    post_repo = PostRepository(database)
    updated_post = await post_repo.update_post(post_id, post_data, current_user.id)
    
    if not updated_post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found or you don't have permission to update it"
        )
    
    return updated_post

@app.delete("/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_post(post_id: int, current_user: UserInDB = Depends(get_current_user)):
    """Delete a post."""
    post_repo = PostRepository(database)
    success = await post_repo.delete_post(post_id, current_user.id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found or you don't have permission to delete it"
        )

@app.get("/users/{user_id}/posts", response_model=List[PostInDB])
async def read_user_posts(user_id: int, skip: int = 0, limit: int = 100):
    """Get posts by a specific user."""
    post_repo = PostRepository(database)
    return await post_repo.get_posts_by_author(user_id, skip=skip, limit=limit)

# Admin routes
@app.get("/admin/users", response_model=List[UserInDB])
async def read_users(skip: int = 0, limit: int = 100, current_user: UserInDB = Depends(get_current_active_superuser)):
    """Get list of all users (admin only)."""
    user_repo = UserRepository(database)
    return await user_repo.list_users(skip=skip, limit=limit)

@app.delete("/admin/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: int, current_user: UserInDB = Depends(get_current_active_superuser)):
    """Delete a user (admin only)."""
    user_repo = UserRepository(database)
    success = await user_repo.delete_user(user_id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

@app.get("/admin/posts", response_model=List[PostInDB])
async def read_all_posts(skip: int = 0, limit: int = 100, current_user: UserInDB = Depends(get_current_active_superuser)):
    """Get list of all posts including unpublished (admin only)."""
    post_repo = PostRepository(database)
    return await post_repo.list_posts(skip=skip, limit=limit, published_only=False)

# Health check
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    try:
        # Check database connection
        await database.execute("SELECT 1")
        db_status = "healthy"
    except Exception:
        db_status = "unhealthy"
    
    try:
        # Check cache connection
        await cache_manager.set("health_check", "ok", expire=10)
        cache_status = "healthy"
    except Exception:
        cache_status = "unhealthy"
    
    return {
        "status": "healthy" if db_status == "healthy" and cache_status == "healthy" else "unhealthy",
        "database": db_status,
        "cache": cache_status,
        "timestamp": datetime.utcnow().isoformat()
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
"""