"""
Test configuration and runner for adapter integration tests.

This module provides utilities for running different test suites
and configuring test environments.
"""

import os
import sys
import subprocess
import time
from typing import Dict, List, Optional

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

class TestRunner:
    """Test runner with different test suite configurations."""
    
    def __init__(self, verbose: bool = True):
        self.verbose = verbose
        self.test_results = {}
    
    def run_integration_tests(self) -> bool:
        """Run integration tests with real API endpoints."""
        print("🔧 Running Integration Tests...")
        print("=" * 50)
        
        cmd = [
            "python", "-m", "pytest", 
            "tests/test_adapter_integration.py::TestAdapterIntegration",
            "-v" if self.verbose else "-q",
            "--tb=short"
        ]
        
        return self._run_test_command(cmd, "integration")
    
    def run_mock_header_tests(self) -> bool:
        """Run mock header tests for rate limiting scenarios."""
        print("🎭 Running Mock Header Tests...")
        print("=" * 50)
        
        # Test specific scenario: Low pct (10%) + medium input → TRANSLATE
        print("Testing scenario: Low pct (10%) + medium input → TRANSLATE")
        
        cmd = [
            "python", "-m", "pytest",
            "tests/test_adapter_integration.py::TestMockHeaderScenarios",
            "-v" if self.verbose else "-q",
            "--tb=short",
            "-k", "low_remaining_pct or translation_flag"
        ]
        
        return self._run_test_command(cmd, "mock_headers")
    
    def run_validation_loop_tests(self) -> bool:
        """Run validation tests to prevent infinite loops and semantic regressions."""
        print("🔍 Running Validation Loop Tests...")
        print("=" * 50)
        print("AI Review: Ensuring no infinite loops or semantic regressions...")
        
        cmd = [
            "python", "-m", "pytest",
            "tests/test_adapter_integration.py::TestValidationLoops",
            "-v" if self.verbose else "-q",
            "--tb=short"
        ]
        
        return self._run_test_command(cmd, "validation_loops")
    
    def run_latency_tests(self) -> bool:
        """Run latency tests and warn if adaptation logic exceeds 200ms."""
        print("⚡ Running Latency Tests...")
        print("=" * 50)
        print("Checking if adaptation logic exceeds 200ms on large payloads...")
        
        cmd = [
            "python", "-m", "pytest",
            "tests/test_adapter_integration.py::TestLatencyChecks",
            "-v" if self.verbose else "-q",
            "--tb=short",
            "-s"  # Show print statements for latency warnings
        ]
        
        return self._run_test_command(cmd, "latency")
    
    def run_edge_case_tests(self) -> bool:
        """Run edge case and error condition tests."""
        print("🎯 Running Edge Case Tests...")
        print("=" * 50)
        
        cmd = [
            "python", "-m", "pytest",
            "tests/test_adapter_integration.py::TestEdgeCases",
            "-v" if self.verbose else "-q",
            "--tb=short"
        ]
        
        return self._run_test_command(cmd, "edge_cases")
    
    def run_all_tests(self) -> Dict[str, bool]:
        """Run all test suites."""
        print("🚀 Running All Adapter Tests...")
        print("=" * 80)
        
        test_suites = [
            ("Integration Tests", self.run_integration_tests),
            ("Mock Header Tests", self.run_mock_header_tests),
            ("Validation Loop Tests", self.run_validation_loop_tests),
            ("Latency Tests", self.run_latency_tests),
            ("Edge Case Tests", self.run_edge_case_tests)
        ]
        
        results = {}
        start_time = time.time()
        
        for suite_name, test_func in test_suites:
            print(f"\n📋 Starting {suite_name}...")
            suite_start = time.time()
            
            try:
                results[suite_name] = test_func()
                suite_time = time.time() - suite_start
                status = "✅ PASSED" if results[suite_name] else "❌ FAILED"
                print(f"   {status} in {suite_time:.2f}s")
            except Exception as e:
                results[suite_name] = False
                print(f"   ❌ ERROR: {str(e)}")
        
        total_time = time.time() - start_time
        self._print_summary(results, total_time)
        
        return results
    
    def _run_test_command(self, cmd: List[str], test_type: str) -> bool:
        """Run a test command and return success status."""
        try:
            # Change to project directory
            os.chdir(project_root)
            
            result = subprocess.run(
                cmd,
                capture_output=not self.verbose,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            success = result.returncode == 0
            self.test_results[test_type] = {
                "success": success,
                "returncode": result.returncode,
                "stdout": result.stdout if hasattr(result, 'stdout') else "",
                "stderr": result.stderr if hasattr(result, 'stderr') else ""
            }
            
            if not success and not self.verbose:
                print(f"❌ Test failed. stderr: {result.stderr}")
                print(f"   stdout: {result.stdout}")
            
            return success
            
        except subprocess.TimeoutExpired:
            print(f"❌ Test timed out after 5 minutes")
            return False
        except Exception as e:
            print(f"❌ Error running test: {str(e)}")
            return False
    
    def _print_summary(self, results: Dict[str, bool], total_time: float):
        """Print test summary."""
        print("\n" + "=" * 80)
        print("📊 TEST SUMMARY")
        print("=" * 80)
        
        passed = sum(1 for r in results.values() if r)
        total = len(results)
        
        print(f"Total Tests: {total}")
        print(f"Passed: {passed}")
        print(f"Failed: {total - passed}")
        print(f"Total Time: {total_time:.2f}s")
        print(f"Success Rate: {passed/total*100:.1f}%")
        
        print("\nDetailed Results:")
        for suite_name, success in results.items():
            status = "✅ PASSED" if success else "❌ FAILED"
            print(f"  {status} {suite_name}")
        
        if passed == total:
            print("\n🎉 All tests passed! Adapter is ready for production.")
        else:
            print(f"\n⚠️  {total - passed} test suite(s) failed. Review logs above.")


def run_specific_test_scenario():
    """Run the specific test scenario mentioned in requirements."""
    print("🎯 Running Specific Test Scenario:")
    print("   Low pct (10%) + medium input → TRANSLATE")
    print("=" * 60)
    
    # This will test the specific scenario
    from tests.test_adapter_integration import TestMockHeaderScenarios
    
    test_instance = TestMockHeaderScenarios()
    
    try:
        # Test the specific case mentioned
        test_instance.test_rate_limit_header_adaptation(10, "aggressive_or_higher")
        print("✅ Specific scenario test passed")
        return True
    except Exception as e:
        print(f"❌ Specific scenario test failed: {str(e)}")
        return False


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Run adapter integration tests")
    parser.add_argument(
        "--suite", 
        choices=["integration", "mock", "validation", "latency", "edge", "all", "specific"],
        default="all",
        help="Test suite to run"
    )
    parser.add_argument("--quiet", "-q", action="store_true", help="Quiet output")
    
    args = parser.parse_args()
    
    runner = TestRunner(verbose=not args.quiet)
    
    if args.suite == "integration":
        success = runner.run_integration_tests()
    elif args.suite == "mock":
        success = runner.run_mock_header_tests()
    elif args.suite == "validation":
        success = runner.run_validation_loop_tests()
    elif args.suite == "latency":
        success = runner.run_latency_tests()
    elif args.suite == "edge":
        success = runner.run_edge_case_tests()
    elif args.suite == "specific":
        success = run_specific_test_scenario()
    else:  # all
        results = runner.run_all_tests()
        success = all(results.values())
    
    sys.exit(0 if success else 1)
