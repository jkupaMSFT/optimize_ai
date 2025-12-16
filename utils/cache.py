"""
Cache module for storing compression results and source maps.
"""
import json
import hashlib
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Optional, Any

class CompressionCache:
    """Simple file-based cache for compressed content"""
    
    def __init__(self, cache_dir: str = None):
        if cache_dir is None:
            # Default to project cache directory
            project_root = Path(__file__).parent.parent  # optimize_ai directory
            cache_dir = project_root / ".optimize_ai_cache"
        
        self.cache_dir = Path(cache_dir).expanduser()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl = timedelta(hours=24)  # Cache for 24 hours
    
    def _get_cache_path(self, file_path: str) -> Path:
        """Generate cache file path based on original file path"""
        hash_key = hashlib.md5(file_path.encode()).hexdigest()
        return self.cache_dir / f"{hash_key}.json"
    
    def get(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Get cached compression data"""
        cache_path = self._get_cache_path(file_path)
        
        if not cache_path.exists():
            return None
        
        try:
            with open(cache_path, 'r') as f:
                data = json.load(f)
            
            # Check TTL
            cached_time = datetime.fromisoformat(data['timestamp'])
            if datetime.now() - cached_time > self.ttl:
                cache_path.unlink()
                return None
            
            # Verify file hasn't changed
            with open(file_path, 'r') as f:
                current_hash = hash(f.read())
            
            if current_hash != data.get('original_hash'):
                cache_path.unlink()
                return None
            
            return data
            
        except Exception:
            return None
    
    def set(self, file_path: str, data: Dict[str, Any]):
        """Cache compression data"""
        cache_path = self._get_cache_path(file_path)
        
        data['timestamp'] = datetime.now().isoformat()
        data['file_path'] = file_path
        
        with open(cache_path, 'w') as f:
            json.dump(data, f, indent=2)
    
    def invalidate(self, file_path: str):
        """Remove cached data for a file"""
        cache_path = self._get_cache_path(file_path)
        if cache_path.exists():
            cache_path.unlink()
    
    def clear_all(self):
        """Clear entire cache"""
        for cache_file in self.cache_dir.glob("*.json"):
            cache_file.unlink()
