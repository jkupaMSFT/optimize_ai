# optimize_ai/input_optimizer/engine/cai3_structures.py
"""
Enhanced CAI3 structures for 70-90% compression.
Key improvements:
1. Ultra-compact LITE serialization format
2. Enhanced metadata for local compressions
3. Pool reference system for strings/constants
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Set
from enum import Enum
import hashlib
import json
import logging
from pathlib import Path

class BodyFidelity(Enum):
    """Fidelity levels for method bodies"""
    B0 = "skeleton"  # No body, just signature
    B1 = "flow"      # Dense FLOW language representation
    B2 = "ast"       # Full AST (rarely used)

class NodeType(Enum):
    """CAI3 node types"""
    CLASS = "C"
    METHOD = "M"
    FUNCTION = "F"
    IMPORT = "I"

class PatchOperation(Enum):
    """CAI3 patch operation types"""
    # Original operations
    RB = "RB"  # Replace Body - replaces entire method/function body
    AM = "AM"  # Add Method - adds a new method to a class
    DM = "DM"  # Delete Method - removes a method from a class
    
    # Surgical edit operations
    IL = "IL"  # Insert Line(s) at specific position
    RL = "RL"  # Replace Line(s) at specific position
    DL = "DL"  # Delete Line(s) at specific position

@dataclass
class CAI3Node:
    """Enhanced node with compression metadata"""
    cid: str  # Unique identifier (e.g., "fn_1a2c")
    type: NodeType  # Node type
    name: str  # Original name
    short_name: str  # Compressed name (e.g., "vr" for "validate_record")
    signature: str  # Ultra-compact signature (e.g., "(r)->b")
    body_fidelity: BodyFidelity = BodyFidelity.B0
    body_content: Optional[str] = None  # Dense FLOW content
    span: Optional[Tuple[int, int]] = None  # Line numbers
    byte_span: Optional[Tuple[int, int]] = None  # Byte offsets
    context_hash: Optional[str] = None  # Hash of surrounding context
    parent_cid: Optional[str] = None  # Parent class/module
    metadata: Dict = field(default_factory=dict)  # Includes local_compressions

@dataclass
class CAI3Full:
    """Complete representation stored locally - never sent to LLM"""
    nodes: List[CAI3Node]
    imports: List[str]  # Full import statements
    pools: Dict[str, str]  # String/constant pools (e.g., "s0" -> "required_fields")
    bound_hashes: Dict[str, str]  # cid -> content hash
    span_hashes: Dict[str, str]  # cid -> span hash (SH)
    source_path: str
    python_version: str = "3.11"
    file_hash: str = ""  # Hash of original file
    compression_stats: Dict = field(default_factory=dict)
    hash_to_value: Dict[str, str] = field(default_factory=dict)  # Hash reference mapping (e.g., "#911" -> "database_url")
    
    def to_json(self) -> str:
        """Serialize to JSON for caching"""
        return json.dumps({
            'nodes': [
                {
                    'cid': n.cid,
                    'type': n.type.value,
                    'name': n.name,
                    'short_name': n.short_name,
                    'signature': n.signature,
                    'body_fidelity': n.body_fidelity.value,
                    'body_content': n.body_content,
                    'span': n.span,
                    'byte_span': n.byte_span,
                    'context_hash': n.context_hash,
                    'parent_cid': n.parent_cid,
                    'metadata': n.metadata
                }
                for n in self.nodes
            ],
            'imports': self.imports,
            'pools': self.pools,
            'bound_hashes': self.bound_hashes,
            'span_hashes': self.span_hashes,
            'hash_to_value': self.hash_to_value,
            'source_path': self.source_path,
            'python_version': self.python_version,
            'file_hash': self.file_hash,
            'compression_stats': self.compression_stats
        }, indent=2)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'CAI3Full':
        """Deserialize from JSON"""
        data = json.loads(json_str)
        nodes = [
            CAI3Node(
                cid=n['cid'],
                type=NodeType(n['type']),
                name=n['name'],
                short_name=n['short_name'],
                signature=n['signature'],
                body_fidelity=BodyFidelity(n['body_fidelity']),
                body_content=n.get('body_content'),
                span=tuple(n['span']) if n.get('span') else None,
                byte_span=tuple(n['byte_span']) if n.get('byte_span') else None,
                context_hash=n.get('context_hash'),
                parent_cid=n.get('parent_cid'),
                metadata=n.get('metadata', {})
            )
            for n in data['nodes']
        ]
        return cls(
            nodes=nodes,
            imports=data['imports'],
            pools=data['pools'],
            bound_hashes=data['bound_hashes'],
            span_hashes=data['span_hashes'],
            hash_to_value=data.get('hash_to_value', {}),
            source_path=data['source_path'],
            python_version=data.get('python_version', '3.11'),
            file_hash=data.get('file_hash', ''),
            compression_stats=data.get('compression_stats', {})
        )

@dataclass
class CAI3Map:
    """Enhanced mapping layer with local compression support"""
    name_map: Dict[str, str]  # short -> original (includes locals with cid prefix)
    reverse_name_map: Dict[str, str]  # original -> short
    span_map: Dict[str, Tuple[int, int]]  # cid -> (start_line, end_line)
    byte_map: Dict[str, Tuple[int, int]]  # cid -> (start_byte, end_byte)
    ast_paths: Dict[str, str]  # cid -> AST path
    context_hashes: Dict[str, str]  # cid -> context hash for validation
    parent_map: Dict[str, str]  # cid -> parent_cid
    children_map: Dict[str, List[str]]  # parent_cid -> [child_cids]
    minified_source: Optional[str] = None  # Minified source used for context hash computation
    
    def to_json(self) -> str:
        """Serialize to JSON for caching"""
        return json.dumps({
            'name_map': self.name_map,
            'reverse_name_map': self.reverse_name_map,
            'span_map': self.span_map,
            'byte_map': self.byte_map,
            'ast_paths': self.ast_paths,
            'context_hashes': self.context_hashes,
            'parent_map': self.parent_map,
            'children_map': self.children_map,
            'minified_source': self.minified_source
        }, indent=2)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'CAI3Map':
        """Deserialize from JSON"""
        data = json.loads(json_str)
        return cls(
            name_map=data['name_map'],
            reverse_name_map=data['reverse_name_map'],
            span_map={k: tuple(v) for k, v in data['span_map'].items()},
            byte_map={k: tuple(v) for k, v in data['byte_map'].items()},
            ast_paths=data['ast_paths'],
            context_hashes=data['context_hashes'],
            parent_map=data['parent_map'],
            children_map=data['children_map'],
            minified_source=data.get('minified_source')  # Optional for backward compatibility
        )

@dataclass
class CAI3Lite:
    """Ultra-dense representation for LLM - 70-90% smaller"""
    header: str  # Ultra-compact: "#C3L v2 py=3.11 f=file.py"
    imports: str  # Ultra-compact: "I:j|dt:dt|t:L"
    table: List[str]  # Ultra-compact entries: "M:dp.vr" or "M:dp.vr(r)->b#0"
    bodies: List[str]  # Dense FLOW bodies for edited methods only
    config_keys: Optional[str] = None  # "K:rf,tv,fm,ts"
    chain_aliases: Optional[str] = None  # "D:g0=s.c.g|g1=tv.items|g2=dt.now"
    cid_aliases: Optional[str] = None  # "X:0=mt_5605|1=mt_961c|..."
    pools: Optional[str] = None  # "P:p0=value1;p1=value2"
    raw_blocks: Optional[str] = None  # "R:raw_id=compressed_data,..."
    
    def serialize(self) -> str:
        """Convert to ultra-dense string format for LLM"""
        lines = []
        
        # Ultra-compact header
        lines.append(self.header)
        
        # Imports, aliases, and other metadata in logical order
        if self.imports:
            lines.append(self.imports)
        if self.chain_aliases:
            lines.append(self.chain_aliases)
        if self.cid_aliases:
            lines.append(self.cid_aliases)
        if self.config_keys:
            lines.append(self.config_keys)
        if self.pools:
            lines.append(self.pools)
        if self.raw_blocks:
            lines.append(self.raw_blocks)
        
        # No blank lines in dense mode
        
        # Ultra-compact table
        for entry in self.table:
            lines.append(entry)
        
        # Dense bodies (if any)
        if self.bodies:
            # Use separator for clarity
            lines.append("---")
            lines.extend(self.bodies)
        
        return '\n'.join(lines)
    
    def serialize_verbose(self) -> str:
        """Slightly more readable format for debugging"""
        lines = []
        
        lines.append(self.header)
        
        if self.imports:
            lines.append(self.imports)
        if self.chain_aliases:
            lines.append(self.chain_aliases)
        if self.cid_aliases:
            lines.append(self.cid_aliases)
        if self.config_keys:
            lines.append(self.config_keys)
        if self.pools:
            lines.append(self.pools)
        
        lines.append("")  # Blank line
        
        # Table section
        lines.append("# Structure")
        lines.extend(self.table)
        
        # Bodies section
        if self.bodies:
            lines.append("")
            lines.append("# Bodies")
            lines.extend(self.bodies)
        
        return '\n'.join(lines)

@dataclass
class CAI3Patch:
    """Patch returned by LLM"""
    target_cid: str  # Target node cid
    operation: str  # RB (replace body), AM (add method), DM (delete method), IL (insert lines), RL (replace lines), DL (delete lines)
    body_fidelity: BodyFidelity
    body_content: str  # New dense FLOW content
    metadata: Dict = field(default_factory=dict)  # Can include line_start, line_end for surgical operations
    
    @classmethod
    def parse(cls, patch_text: str) -> List['CAI3Patch']:
        """Parse CAI3-PATCH format from LLM response"""
        patches = []
        lines = patch_text.strip().split('\n')
        
        i = 0
        while i < len(lines):
            if lines[i].startswith('#C3-PATCH'):
                i += 1
                continue
                
            # Parse patch header (e.g., "1:TGT:cid=fn_1a2c OP:RL F=B1 L=5-7" for line operations)
            if ':TGT:' in lines[i]:
                header = lines[i]
                parts = header.split()
                
                # Extract cid - make it robust
                cid_parts = [p for p in parts if 'cid=' in p]
                if not cid_parts:
                    logging.warning(f"No CID found in patch header: {header}")
                    i += 1
                    continue
                # Extract the CID value after 'cid='
                cid_part = cid_parts[0]
                if 'cid=' in cid_part:
                    cid = cid_part.split('cid=')[1]
                else:
                    logging.warning(f"Invalid CID format in patch header: {header}")
                    i += 1
                    continue
                
                # Extract operation - make it robust
                op_parts = [p for p in parts if p.startswith('OP:')]
                if not op_parts:
                    logging.warning(f"No operation found in patch header: {header}")
                    i += 1
                    continue
                operation = op_parts[0].split(':')[1]
                
                # Extract fidelity - make it robust with default
                f_parts = [p for p in parts if p.startswith('F=')]
                if f_parts:
                    try:
                        fidelity = BodyFidelity[f_parts[0].split('=')[1]]
                    except KeyError:
                        logging.warning(f"Unknown fidelity type, using B1: {f_parts[0]}")
                        fidelity = BodyFidelity.B1
                else:
                    logging.warning(f"No fidelity found in patch header, using B1: {header}")
                    fidelity = BodyFidelity.B1
                
                # Extract metadata (e.g., line ranges for surgical operations)
                metadata = {}
                for part in parts:
                    if part.startswith('L='):  # Line range: L=5-7 or L=5
                        line_spec = part.split('=')[1]
                        if '-' in line_spec:
                            start, end = line_spec.split('-')
                            metadata['line_start'] = int(start)
                            metadata['line_end'] = int(end)
                        else:
                            metadata['line_start'] = int(line_spec)
                            metadata['line_end'] = int(line_spec)
                
                # Move to next line to check for META or body content
                i += 1
                
                # Check for META line after TGT line
                if i < len(lines) and lines[i].startswith('META:'):
                    # Parse metadata for surgical operations
                    meta_content = lines[i][5:].strip()
                    for meta_item in meta_content.split(','):
                        if '=' in meta_item:
                            key, value = meta_item.split('=', 1)
                            metadata[key.strip()] = value.strip()
                    i += 1
                
                # Extract body content
                if i < len(lines) and lines[i].startswith('B:'):
                    i += 1
                    body_lines = []
                    while i < len(lines) and lines[i] != 'E':  # Dense END marker
                        body_lines.append(lines[i])
                        i += 1
                    
                    body_content = '\n'.join(body_lines).strip()
                    
                    patches.append(cls(
                        target_cid=cid,
                        operation=operation,
                        body_fidelity=fidelity,
                        body_content=body_content,
                        metadata=metadata
                    ))
            i += 1
        
        return patches

class CAI3Cache:
    """Cache manager for CAI3 artifacts with robust path handling"""
    
    def __init__(self, cache_dir: Path = Path(".cai3_cache")):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(exist_ok=True)
        
        # Keep track of content hashes to file mappings for better cache hits
        self.content_hash_map = {}
        self._load_content_hash_index()
    
    def get_cache_key(self, source_path: Path) -> str:
        """Generate cache key from source path"""
        return hashlib.md5(str(source_path.absolute()).encode()).hexdigest()[:12]
    
    def get_content_hash(self, source_path: Path) -> Optional[str]:
        """Get content hash for a file, used for cache matching"""
        try:
            if source_path.exists():
                return hashlib.md5(source_path.read_bytes()).hexdigest()
            return None
        except Exception:
            return None
    
    def store_full(self, source_path: Path, cai3_full: CAI3Full):
        """Store CAI3Full to cache with content hash tracking"""
        cache_key = self.get_cache_key(source_path)
        cache_file = self.cache_dir / f"{cache_key}_full.json"
        
        # Update content hash before storing
        content_hash = self.get_content_hash(source_path)
        if content_hash:
            cai3_full.file_hash = content_hash
            self.content_hash_map[content_hash] = cache_key
            self._save_content_hash_index()
        
        cache_file.write_text(cai3_full.to_json())
    
    def store_map(self, source_path: Path, cai3_map: CAI3Map):
        """Store CAI3Map to cache"""
        cache_key = self.get_cache_key(source_path)
        cache_file = self.cache_dir / f"{cache_key}_map.json"
        cache_file.write_text(cai3_map.to_json())
    
    def load_full(self, source_path: Path) -> Optional[CAI3Full]:
        """Load CAI3Full from cache with fallback strategies"""
        # Strategy 1: Direct cache lookup
        cache_key = self.get_cache_key(source_path)
        cache_file = self.cache_dir / f"{cache_key}_full.json"
        if cache_file.exists():
            return CAI3Full.from_json(cache_file.read_text())
        
        # Strategy 2: Content hash lookup
        content_hash = self.get_content_hash(source_path)
        if content_hash and content_hash in self.content_hash_map:
            fallback_key = self.content_hash_map[content_hash]
            fallback_file = self.cache_dir / f"{fallback_key}_full.json"
            if fallback_file.exists():
                logging.getLogger(__name__).info(f"Found cache by content hash: {fallback_file}")
                return CAI3Full.from_json(fallback_file.read_text())
        
        # Strategy 3: Search all cache files for matching content hash
        if content_hash:
            for cache_file in self.cache_dir.glob("*_full.json"):
                try:
                    cache_data = json.loads(cache_file.read_text())
                    if cache_data.get('file_hash') == content_hash:
                        logging.getLogger(__name__).info(f"Found matching cache by content hash: {cache_file}")
                        return CAI3Full.from_json(cache_file.read_text())
                except (json.JSONDecodeError, KeyError):
                    continue
        
        return None
    
    def load_map(self, source_path: Path) -> Optional[CAI3Map]:
        """Load CAI3Map from cache with fallback strategies"""
        # Strategy 1: Direct cache lookup
        cache_key = self.get_cache_key(source_path)
        cache_file = self.cache_dir / f"{cache_key}_map.json"
        if cache_file.exists():
            return CAI3Map.from_json(cache_file.read_text())
        
        # Strategy 2: Content hash lookup
        content_hash = self.get_content_hash(source_path)
        if content_hash and content_hash in self.content_hash_map:
            fallback_key = self.content_hash_map[content_hash]
            fallback_file = self.cache_dir / f"{fallback_key}_map.json"
            if fallback_file.exists():
                return CAI3Map.from_json(fallback_file.read_text())
        
        # Strategy 3: Find corresponding map file for any matching full cache
        if content_hash:
            for cache_file in self.cache_dir.glob("*_full.json"):
                try:
                    cache_data = json.loads(cache_file.read_text())
                    if cache_data.get('file_hash') == content_hash:
                        # Found matching full cache, look for corresponding map
                        map_file = self.cache_dir / cache_file.name.replace('_full.json', '_map.json')
                        if map_file.exists():
                            return CAI3Map.from_json(map_file.read_text())
                except (json.JSONDecodeError, KeyError):
                    continue
        
        return None
    
    def invalidate(self, source_path: Path):
        """Invalidate cache for a source file"""
        cache_key = self.get_cache_key(source_path)
        
        # Remove from content hash map
        content_hash = self.get_content_hash(source_path)
        if content_hash and content_hash in self.content_hash_map:
            del self.content_hash_map[content_hash]
            self._save_content_hash_index()
        
        # Remove cache files
        for suffix in ['_full.json', '_map.json']:
            cache_file = self.cache_dir / f"{cache_key}{suffix}"
            if cache_file.exists():
                cache_file.unlink()
    
    def _load_content_hash_index(self):
        """Load the content hash to cache key mapping"""
        index_file = self.cache_dir / "content_hash_index.json"
        if index_file.exists():
            try:
                self.content_hash_map = json.loads(index_file.read_text())
            except (json.JSONDecodeError, FileNotFoundError):
                self.content_hash_map = {}
    
    def _save_content_hash_index(self):
        """Save the content hash to cache key mapping"""
        index_file = self.cache_dir / "content_hash_index.json"
        try:
            index_file.write_text(json.dumps(self.content_hash_map, indent=2))
        except Exception as e:
            logging.getLogger(__name__).warning(f"Failed to save content hash index: {e}")

# Utility functions
def generate_cid(node_type: str, node_name: str, parent_cid: Optional[str] = None) -> str:
    """Generate a unique cid for a node"""
    # Use a short hash of the full path for uniqueness
    full_path = f"{parent_cid or 'root'}.{node_type}.{node_name}"
    hash_val = hashlib.md5(full_path.encode()).hexdigest()[:4]
    
    # Create readable cid (e.g., "fn_1a2c" for function, "cl_3b4d" for class)
    prefix = {
        'F': 'fn',
        'M': 'mt',
        'C': 'cl'
    }.get(node_type, 'nd')
    
    return f"{prefix}_{hash_val}"

def compress_name(name: str, used_names: Set[str]) -> str:
    """Generate a compressed name that doesn't conflict"""
    # Strategy: use initials, then add numbers if needed
    if '_' in name:
        # snake_case: take first letter of each part
        parts = name.split('_')
        base = ''.join(p[0] for p in parts if p)[:2]  # Max 2 chars
    elif name[0].isupper():
        # CamelCase: take capital letters
        base = ''.join(c for c in name if c.isupper()).lower()[:2]
    else:
        # Simple name: take first 1-2 chars
        base = name[0] if len(name) > 5 else name[:2]
    
    # Ensure uniqueness
    if base not in used_names:
        used_names.add(base)
        return base
    
    # Add numbers if needed
    for i in range(10):
        candidate = f"{base[0]}{i}"
        if candidate not in used_names:
            used_names.add(candidate)
            return candidate
    
    # Fallback: use hash
    return hashlib.md5(name.encode()).hexdigest()[:3]