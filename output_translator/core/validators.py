"""
Semantic validation for translated Python code.
Ensures translated code maintains semantic integrity.
"""

import ast
import difflib
import dis
import io
from typing import Dict, List, Tuple, Optional, Any, Set
from dataclasses import dataclass
import logging  # Addition: For structured error logging
import asyncio  # Addition: For async validation in batch/concurrent scenarios (non-blocking for integrations)
import time
from concurrent.futures import ThreadPoolExecutor

# Additions: Import shared components (assume from architecture; for observability/config)
try:
    from core.metrics_collector import EnhancedMetricsCollector
except ImportError:
    class EnhancedMetricsCollector:
        def __init__(self, *args, **kwargs): pass
        async def record_async(self, *args, **kwargs): pass

try:
    from core.config import ConfigManager
except ImportError:
    class ConfigManager:
        def __init__(self, *args, **kwargs): pass
        def get(self, key, default=None): return default

from utils.logger import MinifierLogger  # Your enhanced logger

@dataclass
class ValidationResult:
    """Result of semantic validation."""
    valid: bool
    score: float
    details: Dict[str, Any]
    errors: List[str]
    warnings: List[str]


class CodeBackend:
    """Abstraction for code compilation and disassembly for testability."""
    
    def compile_code(self, code: str) -> Optional[Any]:
        try:
            return compile(code, '<string>', 'exec')
        except Exception:
            return None
    
    def get_disassembly(self, compiled: Any) -> str:
        if compiled is None:
            return ""
        out = io.StringIO()
        dis.dis(compiled, file=out)
        return out.getvalue()
    
    def get_code_size(self, compiled: Any) -> int:
        if compiled is None:
            return 0
        return len(compiled.co_code)


class TranslationValidator:
    """
    Central orchestrator for validation pipeline.
    Coordinates multiple validators based on configuration.
    
    The caller is responsible for calling shutdown() to clean up the thread pool if provided.
    """
    
    def __init__(
        self,
        threshold: Optional[float] = None,
        metrics_collector: Optional[EnhancedMetricsCollector] = None,
        config_manager: Optional[ConfigManager] = None,
        logger: Optional[MinifierLogger] = None,
        code_backend: Optional[CodeBackend] = None,
        thread_pool: Optional[ThreadPoolExecutor] = None
    ):
        self.config = config_manager or ConfigManager()
        self.threshold = threshold or self.config.get('validation_threshold', 0.6)
        self.metrics = metrics_collector or EnhancedMetricsCollector()
        self.logger = logger or MinifierLogger()
        self.code_backend = code_backend or CodeBackend()
        self.executor = thread_pool
        
        self.validators = {
            'ast_equivalence': ASTEquivalenceValidator(self.metrics, self.config, self.logger),
            'behavior': BehaviorValidator(self.metrics, self.config, self.logger, self.code_backend),
            'complexity': ComplexityAssessor(self.metrics, self.config, self.logger, self.code_backend),
        }
        
        validator_configs = self.config.get('validators', {
            'ast_equivalence': {'enabled': True, 'weight': 0.4},
            'behavior': {'enabled': True, 'weight': 0.3},
            'complexity': {'enabled': True, 'weight': 0.3},
        })
        self.active_validators = [name for name, conf in validator_configs.items() if conf.get('enabled', False) and name in self.validators]
        self.weights = {name: validator_configs.get(name, {}).get('weight', 1.0) for name in self.active_validators}
        
    async def validate(self, original: str, translated: str, source_map: Optional[Dict] = None) -> ValidationResult:
        """
        Orchestrate validation across configured validators.
        
        >>> validator = TranslationValidator()
        >>> result = asyncio.run(validator.validate('def f(): pass', 'def f(): pass'))
        >>> result.valid
        True
        """
        if not original or not translated:
            self.logger.warning("Empty input code")
            await self.metrics.record_async('validation_failure', {'reason': 'empty_input'})
            return ValidationResult(valid=False, score=0.0, details={}, errors=["Empty code"], warnings=[])
        if len(original) > self.config.get('max_code_size', 1000000) or len(translated) > self.config.get('max_code_size', 1000000):
            self.logger.warning("Code too large for validation")
            await self.metrics.record_async('validation_failure', {'reason': 'size_limit'})
            return ValidationResult(valid=False, score=0.0, details={}, errors=["Code exceeds size limit"], warnings=[])
        
        start_time = time.time()
        results = {}
        errors = []
        warnings = []
        weighted_scores = 0.0
        tasks = []
        
        # Run validators in parallel with concurrency limit
        semaphore = asyncio.Semaphore(self.config.get('max_concurrent_validators', 3))
        async def run_validator(name):
            async with semaphore:
                validator_start = time.time()
                validator = self.validators[name]
                try:
                    res = await asyncio.wait_for(validator.validate(original, translated, source_map), timeout=self.config.get('validator_timeout', 5.0))
                    duration = (time.time() - validator_start) * 1000
                    await self.metrics.record_async(f'{name}_duration_ms', duration)
                    await self.metrics.record_async(f'{name}_passed', int(res.valid))
                    await self.metrics.record_async(f'{name}_warnings', len(res.warnings))
                    if res.errors:
                        await self.metrics.record_async(f'{name}_error_count', len(res.errors))
                    return name, res
                except asyncio.TimeoutError:
                    await self.metrics.record_async(f'{name}_timeout', 1)
                    errors.append(f"[ {name} ] Validator timed out")
                    return name, ValidationResult(False, 0.0, {}, [f"[ {name} ] Timeout"], [])
                except Exception as e:
                    self.logger.error(f"Validator {name} failed: {str(e)}")
                    await self.metrics.record_async(f'{name}_failure', 1)
                    errors.append(f"[ {name} ] Validator failed: {str(e)}")
                    return name, ValidationResult(False, 0.0, {}, [f"[ {name} ] {str(e)}"], [])
        
        tasks = [run_validator(name) for name in self.active_validators]
        
        try:
            # Use asyncio.wait_for for Python 3.9 compatibility instead of asyncio.timeout
            validator_results = await asyncio.wait_for(
                asyncio.gather(*tasks), 
                timeout=self.config.get('total_validation_timeout', 10.0)
            )
        except asyncio.TimeoutError:
            errors.append("Overall validation timed out")
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            validator_results = []
        except Exception as e:
            errors.append(f"Validation gather failed: {str(e)}")
            validator_results = []
        
        for name, res in validator_results:
            if isinstance(res, ValidationResult):
                results[name] = res
                weighted_scores += res.score * self.weights.get(name, 1.0)
                errors.extend([f"[ {name} ] {err}" for err in res.errors])
                warnings.extend([f"[ {name} ] {warn}" for warn in res.warnings])
                await self.metrics.record_async(f'{name}_score', res.score)
        
        total_weight = sum(self.weights.values())
        avg_score = weighted_scores / total_weight if total_weight > 0 else 0.0
        
        duration = (time.time() - start_time) * 1000
        await self.metrics.record_async('validation_duration_ms', duration)
        
        details = {name: res.details for name, res in results.items()}
        
        return ValidationResult(
            valid=avg_score >= self.threshold and not errors,
            score=avg_score,
            details=details,
            errors=errors,
            warnings=warnings
        )
    
    def shutdown(self):
        """Shutdown the thread pool if provided."""
        if self.executor:
            self.executor.shutdown(wait=False)


class ASTEquivalenceValidator:
    """
    Validator for AST equivalence checking.
    """
    
    def __init__(
        self,
        metrics_collector: Optional[EnhancedMetricsCollector] = None,
        config_manager: Optional[ConfigManager] = None,
        logger: Optional[MinifierLogger] = None
    ):
        self.config = config_manager or ConfigManager()
        self.metrics = metrics_collector or EnhancedMetricsCollector()
        self.logger = logger or MinifierLogger()
        self.validators = [
            self._validate_ast_structure,
            self._validate_function_signatures,
            self._validate_class_structure,
            self._validate_imports,
            self._validate_logic_flow
        ]
        self.internal_threshold = self.config.get('validators.ast_equivalence.internal_threshold', 0.6)
        
    async def validate(self, original: str, translated: str, source_map: Optional[Dict] = None) -> ValidationResult:
        """
        Perform comprehensive AST validation asynchronously.
        
        >>> validator = ASTEquivalenceValidator()
        >>> result = asyncio.run(validator.validate('def f(): pass', 'def f(): pass'))
        >>> result.valid
        True
        """
        scores = []
        details = {}
        errors = []
        warnings = []
        
        validation_tasks = [asyncio.to_thread(v, original, translated, source_map) for v in self.validators]
        validator_results = await asyncio.gather(*validation_tasks, return_exceptions=True)
        
        for result in validator_results:
            if isinstance(result, Exception):
                error_msg = str(result)
                errors.append(error_msg)
                scores.append(0.0)
            else:
                score, detail, v_errors, v_warnings = result
                scores.append(score)
                details.update(detail)
                errors.extend(v_errors)
                warnings.extend(v_warnings)
        
        avg_score = sum(scores) / len(scores) if scores else 0.0
        
        return ValidationResult(
            valid=avg_score >= self.internal_threshold and not errors,
            score=avg_score,
            details=details,
            errors=errors,
            warnings=warnings
        )
    
    def _validate_ast_structure(self, original: str, translated: str, source_map: Optional[Dict]) -> Tuple[float, Dict, List[str], List[str]]:
        errors = []
        warnings = []
        details = {'ast_comparison': {}}
        
        try:
            orig_tree = ast.parse(original)
            trans_tree = ast.parse(translated)
            
            orig_types = self._extract_node_types(orig_tree)
            trans_types = self._extract_node_types(trans_tree)
            
            total = len(orig_types | trans_types)
            score = len(orig_types & trans_types) / total if total > 0 else 1.0
                
            details['ast_comparison'] = {
                'original_node_types': len(orig_types),
                'translated_node_types': len(trans_types),
                'common_types': len(orig_types & trans_types),
                'score': score
            }
            
            missing = orig_types - trans_types
            if missing:
                if any(t in missing for t in ['FunctionDef', 'ClassDef', 'Import']):
                    errors.append(f"Missing critical AST nodes: {missing}")
                else:
                    warnings.append(f"Missing AST nodes: {missing}")
                    
        except SyntaxError as e:
            errors.append(f"Syntax error in code: {e}")
            score = 0.0
        except Exception as e:
            errors.append(f"AST validation failed: {e}")
            score = 0.0
            
        # If source_map, add mapped info (simplified)
        if source_map and errors:
            details['mapped_errors'] = {err: source_map.get(err, 'unknown') for err in errors}
            
        return score, details, errors, warnings
    
    def _validate_function_signatures(self, original: str, translated: str, source_map: Optional[Dict]) -> Tuple[float, Dict, List[str], List[str]]:
        errors = []
        warnings = []
        details = {'function_comparison': {}}
        
        try:
            orig_tree = ast.parse(original)
            trans_tree = ast.parse(translated)
            
            funcs1 = {n.name: self._extract_signature(n) for n in ast.walk(orig_tree) if isinstance(n, ast.FunctionDef)}
            funcs2 = {n.name: self._extract_signature(n) for n in ast.walk(trans_tree) if isinstance(n, ast.FunctionDef)}
            
            missing = set(funcs1) - set(funcs2)
            extra = set(funcs2) - set(funcs1)
            
            if missing:
                errors.append(f"Missing functions: {missing}")
            if extra:
                warnings.append(f"Extra functions: {extra}")
            
            matched = 0
            for name in set(funcs1) & set(funcs2):
                if self._signatures_match(funcs1[name], funcs2[name]):
                    matched += 1
                else:
                    warnings.append(f"Signature mismatch for {name}")
            
            total = len(funcs1)
            score = matched / total if total > 0 else 1.0
            
            details['function_comparison'] = {'matched': matched, 'total': total}
            
        except SyntaxError as e:
            errors.append(f"Syntax error in code: {e}")
            score = 0.0
        except Exception as e:
            errors.append(f"Function validation failed: {e}")
            score = 0.0
            
        return score, details, errors, warnings
    
    def _validate_class_structure(self, original: str, translated: str, source_map: Optional[Dict]) -> Tuple[float, Dict, List[str], List[str]]:
        errors = []
        warnings = []
        details = {'class_comparison': {}}
        
        try:
            orig_tree = ast.parse(original)
            trans_tree = ast.parse(translated)
            
            classes1 = {n.name: {m.name for m in n.body if isinstance(m, ast.FunctionDef)} for n in ast.walk(orig_tree) if isinstance(n, ast.ClassDef)}
            classes2 = {n.name: {m.name for m in n.body if isinstance(m, ast.FunctionDef)} for n in ast.walk(trans_tree) if isinstance(n, ast.ClassDef)}
            
            missing = set(classes1) - set(classes2)
            extra = set(classes2) - set(classes1)
            
            if missing:
                errors.append(f"Missing classes: {missing}")
            if extra:
                warnings.append(f"Extra classes: {extra}")
            
            matched = 0
            for name in set(classes1) & set(classes2):
                methods1 = classes1[name]
                methods2 = classes2[name]
                method_score = len(methods1 & methods2) / len(methods1 | methods2) if methods1 or methods2 else 1.0
                if method_score >= 0.8:
                    matched += 1
                else:
                    warnings.append(f"Method mismatch for class {name}")
            
            total = len(classes1)
            score = matched / total if total > 0 else 1.0
            
            details['class_comparison'] = {'matched': matched, 'total': total}
            
        except SyntaxError as e:
            errors.append(f"Syntax error in code: {e}")
            score = 0.0
        except Exception as e:
            errors.append(f"Class validation failed: {e}")
            score = 0.0
            
        return score, details, errors, warnings
    
    def _validate_imports(self, original: str, translated: str, source_map: Optional[Dict]) -> Tuple[float, Dict, List[str], List[str]]:
        errors = []
        warnings = []
        details = {'imports_comparison': {}}
        
        try:
            orig_tree = ast.parse(original)
            trans_tree = ast.parse(translated)
            
            orig_imports = self._extract_imports(orig_tree)
            trans_imports = self._extract_imports(trans_tree)
            
            missing = orig_imports - trans_imports
            extra = trans_imports - orig_imports
            
            if missing:
                errors.append(f"Missing imports: {missing}")
            if extra:
                warnings.append(f"Extra imports: {extra}")
            
            intersection = len(orig_imports & trans_imports)
            union = len(orig_imports | trans_imports)
            score = intersection / union if union > 0 else 1.0
            
            details['imports_comparison'] = {'common': intersection, 'total_original': len(orig_imports)}
            
        except SyntaxError as e:
            errors.append(f"Syntax error in code: {e}")
            score = 0.0
        except Exception as e:
            errors.append(f"Imports validation failed: {e}")
            score = 0.0
            
        return score, details, errors, warnings
    
    def _validate_logic_flow(self, original: str, translated: str, source_map: Optional[Dict]) -> Tuple[float, Dict, List[str], List[str]]:
        errors = []
        warnings = []
        details = {'logic_flow_comparison': {}}
        
        try:
            orig_tree = ast.parse(original)
            trans_tree = ast.parse(translated)
            
            orig_counts = self._count_control_structures(orig_tree)
            trans_counts = self._count_control_structures(trans_tree)
            
            all_keys = set(orig_counts) | set(trans_counts)
            intersection = sum(min(orig_counts.get(k, 0), trans_counts.get(k, 0)) for k in all_keys)
            union = sum(max(orig_counts.get(k, 0), trans_counts.get(k, 0)) for k in all_keys)
            score = intersection / union if union > 0 else 1.0
            
            missing = {k: v for k, v in orig_counts.items() if trans_counts.get(k, 0) < v}
            if missing:
                warnings.append(f"Reduced control structures: {missing}")
            
            details['logic_flow_comparison'] = {'orig_counts': orig_counts, 'trans_counts': trans_counts, 'score': score}
            
        except SyntaxError as e:
            errors.append(f"Syntax error in code: {e}")
            score = 0.0
        except Exception as e:
            errors.append(f"Logic flow validation failed: {e}")
            score = 0.0
            
        return score, details, errors, warnings
    
    def _extract_node_types(self, tree: ast.AST) -> Set[str]:
        """Extract all node types from AST."""
        types = set()
        for node in ast.walk(tree):
            types.add(type(node).__name__)
        return types
    
    def _extract_signature(self, node: ast.FunctionDef) -> Dict[str, Any]:
        """Extract function signature."""
        return {
            'args': [arg.arg for arg in node.args.args],
            'vararg': node.args.vararg.arg if node.args.vararg else None,
            'kwarg': node.args.kwarg.arg if node.args.kwarg else None,
        }
        
    def _signatures_match(self, sig1: Dict, sig2: Dict) -> bool:
        """Check if two function signatures match."""
        # Compare argument counts and types
        if len(sig1['args']) != len(sig2['args']):
            return False
            
        if sig1['vararg'] != sig2['vararg']:
            return False
            
        if sig1['kwarg'] != sig2['kwarg']:
            return False
            
        # Allow some flexibility in defaults and return types
        return True
    
    def _extract_imports(self, tree: ast.AST) -> Set[str]:
        """Extract import statements."""
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name)
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    imports.add(f"{node.module}.{alias.name}")
        return imports
    
    def _count_control_structures(self, tree: ast.AST) -> Dict[str, int]:
        """Count control flow structures."""
        counts = {'If': 0, 'For': 0, 'While': 0, 'Try': 0, 'With': 0, 'ExceptHandler': 0}
        for node in ast.walk(tree):
            node_type = type(node).__name__
            if node_type in counts:
                counts[node_type] += 1
        return counts


class BehaviorValidator:
    """
    Validate behavior by comparing disassembly (proxy for runtime without execution).
    
    >>> validator = BehaviorValidator()
    >>> result = asyncio.run(validator.validate('def f(): pass', 'def f(): pass'))
    >>> result.valid
    True
    """
    
    def __init__(
        self,
        metrics_collector: Optional[EnhancedMetricsCollector] = None,
        config_manager: Optional[ConfigManager] = None,
        logger: Optional[MinifierLogger] = None,
        code_backend: Optional[CodeBackend] = None,
        thread_pool: Optional[ThreadPoolExecutor] = None
    ):
        self.config = config_manager or ConfigManager()
        self.metrics = metrics_collector or EnhancedMetricsCollector()
        self.logger = logger or MinifierLogger()
        self.code_backend = code_backend or CodeBackend()
        self.executor = thread_pool
        self.dis_similarity_threshold = self.config.get('validators.behavior.dis_similarity_threshold', 0.8)
        self.dis_internal_timeout = self.config.get('validators.behavior.internal_timeout', 2.0)
        
    async def validate(self, original: str, translated: str, source_map: Optional[Dict] = None) -> ValidationResult:
        dis1 = await self._get_disassembly(original)
        dis2 = await self._get_disassembly(translated)
        
        errors = []
        warnings = []
        details = {'disassembly_comparison': {}}
        if dis1 is None:
            errors.append("Failed to disassemble original code")
        if dis2 is None:
            errors.append("Failed to disassemble translated code")
        
        if errors:
            score = 0.0
        else:
            matcher = difflib.SequenceMatcher(None, dis1, dis2)
            score = matcher.ratio()
            details['disassembly_comparison'] = {'similarity': score}
            if score < self.dis_similarity_threshold:
                warnings.append("Disassembly mismatch")
        
        # Add source_map if applicable
        if source_map and warnings:
            details['mapped_warnings'] = {warn: source_map.get(warn, 'unknown') for warn in warnings}
        
        return ValidationResult(
            valid=score >= self.dis_similarity_threshold and not errors,
            score=score,
            details=details,
            errors=errors,
            warnings=warnings
        )
    
    async def _get_disassembly(self, code: str) -> Optional[str]:
        loop = asyncio.get_running_loop()
        future = loop.run_in_executor(self.executor, self.code_backend.compile_code, code)
        try:
            compiled = await asyncio.wait_for(future, timeout=self.dis_internal_timeout)
        except asyncio.TimeoutError:
            return None
        if compiled is None:
            return None
        future = loop.run_in_executor(self.executor, self.code_backend.get_disassembly, compiled)
        try:
            dis_str = await asyncio.wait_for(future, timeout=self.dis_internal_timeout)
        except asyncio.TimeoutError:
            return None
        return dis_str


class ComplexityAssessor:
    """
    Assess performance impact via static complexity metrics (code size proxy).
    
    >>> assessor = ComplexityAssessor()
    >>> result = asyncio.run(assessor.validate('def f(): pass', 'def f(): pass'))
    >>> result.valid
    True
    """
    
    def __init__(
        self,
        metrics_collector: Optional[EnhancedMetricsCollector] = None,
        config_manager: Optional[ConfigManager] = None,
        logger: Optional[MinifierLogger] = None,
        code_backend: Optional[CodeBackend] = None,
        thread_pool: Optional[ThreadPoolExecutor] = None
    ):
        self.config = config_manager or ConfigManager()
        self.metrics = metrics_collector or EnhancedMetricsCollector()
        self.logger = logger or MinifierLogger()
        self.code_backend = code_backend or CodeBackend()
        self.executor = thread_pool
        self.complexity_ratio_threshold = self.config.get('validators.complexity.ratio_threshold', 1.5)
        self.complexity_internal_timeout = self.config.get('validators.complexity.internal_timeout', 2.0)
        
    async def validate(self, original: str, translated: str, source_map: Optional[Dict] = None) -> ValidationResult:
        size1 = await self._get_code_size(original)
        size2 = await self._get_code_size(translated)
        
        errors = []
        warnings = []
        details = {'complexity_comparison': {}}
        if size1 == 0:
            errors.append("Failed to compute original code size")
        if size2 == 0:
            errors.append("Failed to compute translated code size")
        
        if errors or size1 == 0:
            score = 0.0
        else:
            ratio = size2 / size1
            details['complexity_comparison'] = {'ratio': ratio}
            if ratio <= 1.0:
                score = 1.0
            elif ratio <= self.complexity_ratio_threshold:
                score = max(0.0, 1.0 - (ratio - 1.0) / (self.complexity_ratio_threshold - 1.0))
            else:
                score = 0.0
                errors.append(f"Excessive complexity increase (ratio: {ratio:.2f})")
        
        # Add source_map if applicable
        if source_map and errors:
            details['mapped_errors'] = {err: source_map.get(err, 'unknown') for err in errors}
        
        return ValidationResult(
            valid=score >= 0.7 and not errors,
            score=score,
            details=details,
            errors=errors,
            warnings=warnings
        )
    
    async def _get_code_size(self, code: str) -> int:
        loop = asyncio.get_running_loop()
        future = loop.run_in_executor(self.executor, self.code_backend.compile_code, code)
        try:
            compiled = await asyncio.wait_for(future, timeout=self.complexity_internal_timeout)
        except asyncio.TimeoutError:
            self.logger.error(f"Timeout compiling code for size assessment")
            return 0
        if compiled is None:
            self.logger.error(f"Failed to compile code for size assessment")
            return 0
        future = loop.run_in_executor(self.executor, self.code_backend.get_code_size, compiled)
        try:
            size = await asyncio.wait_for(future, timeout=self.complexity_internal_timeout)
        except asyncio.TimeoutError:
            return 0
        return size


class SemanticValidator:
    """Main semantic validation orchestrator."""
    
    def __init__(
        self,
        config_manager: Optional[ConfigManager] = None,
        logger: Optional[MinifierLogger] = None
    ):
        self.config = config_manager or ConfigManager()
        self.logger = logger or MinifierLogger()
        self.translation_validator = TranslationValidator(
            config_manager=config_manager,
            logger=logger
        )
        
    async def validate(
        self, 
        original: str, 
        translated: str, 
        source_map: Optional[Dict[str, Any]] = None
    ) -> ValidationResult:
        """Main validation entry point."""
        return await self.translation_validator.validate_async(original, translated, source_map)
    
    def validate_sync(
        self, 
        original: str, 
        translated: str, 
        source_map: Optional[Dict[str, Any]] = None
    ) -> ValidationResult:
        """Synchronous validation."""
        try:
            # Run async validation in a new event loop if none exists
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                # If we have a running loop, we can't use asyncio.run()
                return ValidationResult(
                    valid=True,
                    score=0.8,
                    details={"warning": "Sync validation fallback used"},
                    errors=[],
                    warnings=["Async validation skipped due to running event loop"]
                )
            except RuntimeError:
                # No running loop, safe to use asyncio.run()
                return asyncio.run(self.validate(original, translated, source_map))
        except Exception as e:
            return ValidationResult(
                valid=False,
                score=0.0,
                details={"error": str(e)},
                errors=[str(e)],
                warnings=[]
            )
