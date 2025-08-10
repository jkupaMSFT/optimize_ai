# optimize_ai/input_optimizer/engine/cai3_structures.py
"""
CAI3 three-plane architecture data structures for maximum compression.
Only CAI3-LITE goes to the LLM, FULL and MAP stay local.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Set
from enum import Enum
import hashlib
import json
from pathlib import Path

class BodyFidelity(Enum):
    """Fidelity levels for method bodies"""
    B0 = "skeleton"  # No body, just signature
    B1 = "flow"      # FLOW language representation
    B2 = "ast"       # Full AST (rarely used)

class NodeType(Enum):
    """CAI3 node types"""
    CLASS = "C"
    METHOD = "M"
    FUNCTION = "F"
    IMPORT = "I"

@dataclass
class CAI3Node:
    """Single node in the CAI3 representation"""
    cid: str  # Unique identifier (e.g., "fn_1a2c")
    type: NodeType  # Node type
    name: str  # Original name
    short_name: str  # Compressed name (e.g., "vr" for "validate_record")
    signature: str  # Simplified signature (e.g., "record->bool")
    body_fidelity: BodyFidelity = BodyFidelity.B0
    body_content: Optional[str] = None  # FLOW or AST content
    span: Optional[Tuple[int, int]] = None  # Line numbers
    byte_span: Optional[Tuple[int, int]] = None  # Byte offsets
    context_hash: Optional[str] = None  # Hash of surrounding context
    parent_cid: Optional[str] = None  # Parent class/module
    metadata: Dict = field(default_factory=dict)

@dataclass
class CAI3Full:
    """Complete representation stored locally - never sent to LLM"""
    nodes: List[CAI3Node]
    imports: List[str]  # Full import statements
    pools: Dict[str, str]  # Constants pool (e.g., "processed_at" -> value)
    bound_hashes: Dict[str, str]  # cid -> content hash
    span_hashes: Dict[str, str]  # cid -> span hash (SH)
    source_path: str
    python_version: str = "3.11"
    file_hash: str = ""  # Hash of original file
    compression_stats: Dict = field(default_factory=dict)
    
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
            source_path=data['source_path'],
            python_version=data.get('python_version', '3.11'),
            file_hash=data.get('file_hash', ''),
            compression_stats=data.get('compression_stats', {})
        )

@dataclass
class CAI3Map:
    """Mapping layer for translator - stays local"""
    name_map: Dict[str, str]  # short -> original (e.g., "vr" -> "validate_record")
    reverse_name_map: Dict[str, str]  # original -> short
    span_map: Dict[str, Tuple[int, int]]  # cid -> (start_line, end_line)
    byte_map: Dict[str, Tuple[int, int]]  # cid -> (start_byte, end_byte)
    ast_paths: Dict[str, str]  # cid -> AST path (e.g., "Module.body[0].body[2]")
    context_hashes: Dict[str, str]  # cid -> context hash for validation
    parent_map: Dict[str, str]  # cid -> parent_cid
    children_map: Dict[str, List[str]]  # parent_cid -> [child_cids]
    
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
            'children_map': self.children_map
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
            children_map=data['children_map']
        )

@dataclass
class CAI3Lite:
    """Minimal representation for LLM - this is all the model sees"""
    header: str  # Version, file, macros (e.g., "#C3-L v1 py=3.11 file=processor.py MACROS=v1")
    imports: str  # Compressed imports (e.g., "I:json|csv|from datetime:datetime")
    table: List[str]  # T: entries (signatures only)
    bodies: List[str]  # B: entries (FLOW bodies for edited methods only)
    config_keys: Optional[str] = None  # Config keys if used (e.g., "CFG_KEYS:required_fields,type_validation")
    
    def serialize(self) -> str:
        """Convert to string format for LLM"""
        lines = [self.header]
        
        if self.imports:
            lines.append(self.imports)
            
        if self.config_keys:
            lines.append(self.config_keys)
            
        lines.append("")  # Blank line after header
        
        # Add table entries
        lines.extend(self.table)
        
        if self.bodies:
            lines.append("")  # Blank line before bodies
            lines.extend(self.bodies)
        
        return '\n'.join(lines)

@dataclass
class CAI3Patch:
    """Patch returned by LLM"""
    target_cid: str  # Target node cid
    operation: str  # RB (replace body), AM (add method), etc.
    body_fidelity: BodyFidelity
    body_content: str  # New FLOW/AST content
    metadata: Dict = field(default_factory=dict)
    
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
                
            # Parse patch header (e.g., "1:TGT:cid=fn_1a2c OP:RB F=B1")
            if ':TGT:' in lines[i]:
                header = lines[i]
                parts = header.split()
                
                # Extract cid
                cid_part = [p for p in parts if p.startswith('cid=')][0]
                cid = cid_part.split('=')[1]
                
                # Extract operation
                op_part = [p for p in parts if p.startswith('OP:')][0]
                operation = op_part.split(':')[1]
                
                # Extract fidelity
                f_part = [p for p in parts if p.startswith('F=')][0]
                fidelity = BodyFidelity[f_part.split('=')[1]]
                
                # Extract body content
                i += 1
                if i < len(lines) and lines[i].startswith('B:'):
                    i += 1
                    body_lines = []
                    while i < len(lines) and not lines[i].startswith('END'):
                        body_lines.append(lines[i])
                        i += 1
                    
                    body_content = '\n'.join(body_lines).strip()
                    
                    patches.append(cls(
                        target_cid=cid,
                        operation=operation,
                        body_fidelity=fidelity,
                        body_content=body_content
                    ))
            i += 1
        
        return patches

class CAI3Cache:
    """Cache manager for CAI3 artifacts"""
    
    def __init__(self, cache_dir: Path = Path(".cai3_cache")):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(exist_ok=True)
    
    def get_cache_key(self, source_path: Path) -> str:
        """Generate cache key from source path"""
        return hashlib.md5(str(source_path.absolute()).encode()).hexdigest()[:12]
    
    def store_full(self, source_path: Path, cai3_full: CAI3Full):
        """Store CAI3Full to cache"""
        cache_key = self.get_cache_key(source_path)
        cache_file = self.cache_dir / f"{cache_key}_full.json"
        cache_file.write_text(cai3_full.to_json())
    
    def store_map(self, source_path: Path, cai3_map: CAI3Map):
        """Store CAI3Map to cache"""
        cache_key = self.get_cache_key(source_path)
        cache_file = self.cache_dir / f"{cache_key}_map.json"
        cache_file.write_text(cai3_map.to_json())
    
    def load_full(self, source_path: Path) -> Optional[CAI3Full]:
        """Load CAI3Full from cache"""
        cache_key = self.get_cache_key(source_path)
        cache_file = self.cache_dir / f"{cache_key}_full.json"
        if cache_file.exists():
            return CAI3Full.from_json(cache_file.read_text())
        return None
    
    def load_map(self, source_path: Path) -> Optional[CAI3Map]:
        """Load CAI3Map from cache"""
        cache_key = self.get_cache_key(source_path)
        cache_file = self.cache_dir / f"{cache_key}_map.json"
        if cache_file.exists():
            return CAI3Map.from_json(cache_file.read_text())
        return None
    
    def invalidate(self, source_path: Path):
        """Invalidate cache for a source file"""
        cache_key = self.get_cache_key(source_path)
        for suffix in ['_full.json', '_map.json']:
            cache_file = self.cache_dir / f"{cache_key}{suffix}"
            if cache_file.exists():
                cache_file.unlink()

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
        base = ''.join(p[0] for p in parts if p)
    elif name[0].isupper():
        # CamelCase: take capital letters
        base = ''.join(c for c in name if c.isupper()).lower()
    else:
        # Simple name: take first 2-3 chars
        base = name[:3] if len(name) > 3 else name
    
    # Ensure uniqueness
    if base not in used_names:
        used_names.add(base)
        return base
    
    # Add numbers if needed
    for i in range(1, 100):
        candidate = f"{base}{i}"
        if candidate not in used_names:
            used_names.add(candidate)
            return candidate
    
    # Fallback: use hash
    return hashlib.md5(name.encode()).hexdigest()[:4]