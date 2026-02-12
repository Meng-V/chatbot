#!/usr/bin/env python3
"""
LibCal Comprehensive Test Suite
================================
Tests LibCal functionality using questions from ../testquestion.json

Focuses on:
- Library hours (all locations)
- Study room reservations
- Contact information
- Location-specific queries

Usage:
    python scripts/libcal_comprehensive_test.py
    python scripts/libcal_comprehensive_test.py --category library_hours
    python scripts/libcal_comprehensive_test.py --quick  # Run subset only
"""

import asyncio
import httpx
import json
import sys
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Tuple
from collections import defaultdict
import statistics
import time

# Configuration
API_URL = "http://localhost:8000/ask"
ROUTE_URL = "http://localhost:8000/route"
TIMEOUT = 90
DELAY_BETWEEN_REQUESTS = 2.0  # Avoid rate limits
DELAY_BETWEEN_CATEGORIES = 5.0

# File paths
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
TEST_QUESTIONS_FILE = PROJECT_ROOT / "test" / "testquestion.json"
RESULTS_DIR = SCRIPT_DIR.parent / "test_results"
RESULTS_DIR.mkdir(exist_ok=True)


class Color:
    """ANSI color codes for terminal output"""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    END = '\033[0m'


class TestResult:
    """Container for test result data"""
    def __init__(self, category: str, subcategory: str, question: str):
        self.category = category
        self.subcategory = subcategory
        self.question = question
        self.response = None
        self.error = None
        self.response_time = 0
        self.routed_agent = None
        self.success = False
        self.validation_notes = []
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category,
            "subcategory": self.subcategory,
            "question": self.question,
            "response": self.response,
            "error": self.error,
            "response_time": self.response_time,
            "routed_agent": self.routed_agent,
            "success": self.success,
            "validation_notes": self.validation_notes
        }


class LibCalTester:
    """Main test runner for LibCal functionality"""
    
    def __init__(self):
        self.test_questions = {}
        self.results: List[TestResult] = []
        self.start_time = None
        
    def load_test_questions(self) -> bool:
        """Load test questions from JSON file"""
        if not TEST_QUESTIONS_FILE.exists():
            print(f"{Color.RED}❌ Test questions file not found: {TEST_QUESTIONS_FILE}{Color.END}")
            return False
        
        try:
            with open(TEST_QUESTIONS_FILE, 'r') as f:
                self.test_questions = json.load(f)
            print(f"{Color.GREEN}✓ Loaded test questions from {TEST_QUESTIONS_FILE}{Color.END}")
            return True
        except Exception as e:
            print(f"{Color.RED}❌ Error loading test questions: {e}{Color.END}")
            return False
    
    def get_libcal_questions(self, category_filter: str = None) -> List[Tuple[str, str, str]]:
        """
        Extract LibCal-related questions from test data
        Returns list of (category, subcategory, question) tuples
        """
        libcal_questions = []
        
        # LibCal-related categories
        libcal_categories = {
            "library_hours": ["king_library", "art_and_architecture", "makerspace", 
                             "special_collections", "regional_libraries"],
            "library_contact_info": ["king_library", "art_and_architecture", "makerspace",
                                    "special_collections", "middletown", "hamilton"],
            "study_rooms": ["reservation_info", "action_requests"],
            "technology_and_help": ["live_chat"]  # Ask Us hours
        }
        
        # Apply category filter if specified
        if category_filter:
            if category_filter in libcal_categories:
                categories_to_test = {category_filter: libcal_categories[category_filter]}
            else:
                print(f"{Color.YELLOW}⚠ Unknown category: {category_filter}{Color.END}")
                return []
        else:
            categories_to_test = libcal_categories
        
        # Extract questions
        for category, subcategories in categories_to_test.items():
            if category not in self.test_questions:
                continue
            
            category_data = self.test_questions[category]
            
            if isinstance(category_data, dict):
                # Nested structure (has subcategories)
                for subcat in subcategories:
                    if subcat in category_data:
                        questions = category_data[subcat]
                        for q in questions:
                            libcal_questions.append((category, subcat, q))
            elif isinstance(category_data, list):
                # Flat list of questions
                for q in category_data:
                    libcal_questions.append((category, "", q))
        
        return libcal_questions
    
    async def test_single_question(self, category: str, subcategory: str, 
                                   question: str, client: httpx.AsyncClient) -> TestResult:
        """Test a single question against the API"""
        result = TestResult(category, subcategory, question)
        
        try:
            print(f"\n{Color.CYAN}Testing: {question[:80]}...{Color.END}")
            
            start_time = time.time()
            
            # First, test routing
            try:
                route_response = await client.post(
                    ROUTE_URL,
                    json={"query": question},
                    timeout=30
                )
                if route_response.status_code == 200:
                    route_data = route_response.json()
                    result.routed_agent = route_data.get("agent_id") or route_data.get("mode")
                    print(f"  {Color.MAGENTA}→ Routed to: {result.routed_agent}{Color.END}")
            except Exception as e:
                print(f"  {Color.YELLOW}⚠ Routing check failed: {e}{Color.END}")
            
            # Then test the full ask endpoint (without conversationId to let API create it)
            response = await client.post(
                API_URL,
                json={
                    "message": question
                },
                timeout=TIMEOUT
            )
            
            result.response_time = time.time() - start_time
            
            if response.status_code == 200:
                data = response.json()
                result.response = data.get("response", "")
                
                # Check if response is empty or too short
                if not result.response or len(result.response.strip()) < 10:
                    result.success = False
                    result.validation_notes.append("Response is empty or too short")
                else:
                    result.success = True
                
                # Validate response content and routing
                self._validate_libcal_response(result, category, subcategory)
                
                # Print result
                status_icon = f"{Color.GREEN}✓{Color.END}" if result.success else f"{Color.RED}✗{Color.END}"
                print(f"  {status_icon} Response time: {result.response_time:.2f}s")
                if result.response:
                    print(f"  {Color.BLUE}Response preview: {result.response[:150]}...{Color.END}")
                else:
                    print(f"  {Color.RED}Response is EMPTY{Color.END}")
                
                if result.validation_notes:
                    for note in result.validation_notes:
                        print(f"  {Color.YELLOW}⚠ {note}{Color.END}")
            else:
                result.error = f"HTTP {response.status_code}: {response.text}"
                result.success = False
                print(f"  {Color.RED}✗ Error: {result.error}{Color.END}")
        
        except asyncio.TimeoutError:
            result.error = f"Request timeout after {TIMEOUT}s"
            result.success = False
            print(f"  {Color.RED}✗ Timeout after {TIMEOUT}s{Color.END}")
        except Exception as e:
            result.error = str(e)
            result.success = False
            print(f"  {Color.RED}✗ Exception: {e}{Color.END}")
        
        return result
    
    def _validate_libcal_response(self, result: TestResult, category: str, subcategory: str):
        """Validate if response contains expected LibCal data"""
        response_lower = result.response.lower()
        
        # Check for misrouting to google_site when it should be libcal_hours
        if category == "library_hours" and result.routed_agent == "google_site":
            result.success = False
            result.validation_notes.append("MISROUTED: Should be libcal_hours, not google_site")
        
        # Check for misrouting to google_site for study room questions
        if category == "study_rooms" and result.routed_agent == "google_site":
            result.success = False
            result.validation_notes.append("MISROUTED: Should be libcal_spaces, not google_site")
        
        # Validation rules for library hours
        if category == "library_hours":
            expected_keywords = []
            
            if "king" in subcategory or "king" in result.question.lower():
                expected_keywords = ["king", "library", "hour", "open", "close"]
            elif "art" in subcategory or "wertz" in result.question.lower():
                expected_keywords = ["art", "architecture", "wertz"]
            elif "makerspace" in subcategory:
                expected_keywords = ["makerspace"]
            elif "special" in subcategory:
                expected_keywords = ["special", "collection"]
            elif "hamilton" in subcategory or "hamilton" in result.question.lower():
                expected_keywords = ["hamilton"]
            elif "middletown" in subcategory or "middletown" in result.question.lower():
                expected_keywords = ["middletown"]
            
            # Check if response contains time information
            has_time_info = any(word in response_lower for word in 
                              ["am", "pm", "hour", "open", "close", "monday", "tuesday", 
                               "wednesday", "thursday", "friday", "saturday", "sunday"])
            
            if not has_time_info:
                result.validation_notes.append("Response may not contain hour information")
            
            # Check for expected keywords
            missing_keywords = [kw for kw in expected_keywords if kw.lower() not in response_lower]
            if missing_keywords:
                result.validation_notes.append(f"Missing keywords: {', '.join(missing_keywords)}")
        
        # Validation rules for study rooms
        elif category == "study_rooms":
            if "reservation" in subcategory:
                expected = ["reserve", "room", "book", "libcal"]
                missing = [kw for kw in expected if kw not in response_lower]
                if missing:
                    result.validation_notes.append(f"May be missing reservation info: {', '.join(missing)}")
            elif "action" in subcategory:
                # These are actual booking requests
                expected = ["room", "study"]
                missing = [kw for kw in expected if kw not in response_lower]
                if missing:
                    result.validation_notes.append(f"May not be handling booking request properly")
        
        # Validation for contact info
        elif category == "library_contact_info":
            expected = ["phone", "address", "contact", "email"]
            has_contact = any(kw in response_lower for kw in expected)
            if not has_contact:
                result.validation_notes.append("Response may not contain contact information")
        
        # Validation for live chat hours
        elif category == "technology_and_help" and "chat" in result.question.lower():
            expected = ["chat", "hour", "available", "open"]
            missing = [kw for kw in expected if kw not in response_lower]
            if missing:
                result.validation_notes.append(f"May be missing chat availability info")
    
    async def run_tests(self, category_filter: str = None, quick_mode: bool = False):
        """Run all LibCal tests"""
        print(f"\n{Color.BOLD}{'='*80}{Color.END}")
        print(f"{Color.BOLD}{Color.CYAN}LibCal Comprehensive Test Suite{Color.END}")
        print(f"{Color.BOLD}{'='*80}{Color.END}\n")
        
        if not self.load_test_questions():
            return
        
        # Get questions to test
        questions_to_test = self.get_libcal_questions(category_filter)
        
        if not questions_to_test:
            print(f"{Color.RED}❌ No LibCal questions found to test{Color.END}")
            return
        
        if quick_mode:
            # Take first 3 from each category
            quick_questions = []
            by_category = defaultdict(list)
            for cat, subcat, q in questions_to_test:
                by_category[cat].append((cat, subcat, q))
            for cat, items in by_category.items():
                quick_questions.extend(items[:3])
            questions_to_test = quick_questions
        
        total_questions = len(questions_to_test)
        print(f"{Color.BOLD}Total questions to test: {total_questions}{Color.END}")
        if category_filter:
            print(f"{Color.BOLD}Category filter: {category_filter}{Color.END}")
        if quick_mode:
            print(f"{Color.YELLOW}Running in QUICK MODE (subset of questions){Color.END}")
        print()
        
        self.start_time = datetime.now()
        
        async with httpx.AsyncClient() as client:
            # Group by category for better output
            by_category = defaultdict(list)
            for cat, subcat, q in questions_to_test:
                by_category[cat].append((cat, subcat, q))
            
            for category_idx, (category, items) in enumerate(by_category.items()):
                print(f"\n{Color.BOLD}{Color.GREEN}{'='*80}{Color.END}")
                print(f"{Color.BOLD}{Color.GREEN}Category: {category.upper().replace('_', ' ')}{Color.END}")
                print(f"{Color.BOLD}{Color.GREEN}{'='*80}{Color.END}")
                
                for idx, (cat, subcat, question) in enumerate(items):
                    result = await self.test_single_question(cat, subcat, question, client)
                    self.results.append(result)
                    
                    # Progress
                    overall_progress = len(self.results)
                    print(f"  {Color.CYAN}Progress: {overall_progress}/{total_questions} "
                          f"({overall_progress*100//total_questions}%){Color.END}")
                    
                    # Delay between requests
                    if idx < len(items) - 1:
                        await asyncio.sleep(DELAY_BETWEEN_REQUESTS)
                
                # Longer delay between categories
                if category_idx < len(by_category) - 1:
                    await asyncio.sleep(DELAY_BETWEEN_CATEGORIES)
        
        # Generate reports
        self.generate_reports()
    
    def generate_reports(self):
        """Generate comprehensive test reports"""
        end_time = datetime.now()
        duration = (end_time - self.start_time).total_seconds()
        
        print(f"\n{Color.BOLD}{'='*80}{Color.END}")
        print(f"{Color.BOLD}{Color.CYAN}TEST RESULTS SUMMARY{Color.END}")
        print(f"{Color.BOLD}{'='*80}{Color.END}\n")
        
        # Overall statistics
        total = len(self.results)
        successful = sum(1 for r in self.results if r.success)
        failed = total - successful
        success_rate = (successful / total * 100) if total > 0 else 0
        
        print(f"{Color.BOLD}Overall Performance:{Color.END}")
        print(f"  Total tests: {total}")
        print(f"  {Color.GREEN}✓ Successful: {successful}{Color.END}")
        print(f"  {Color.RED}✗ Failed: {failed}{Color.END}")
        print(f"  Success rate: {Color.GREEN if success_rate >= 90 else Color.YELLOW}{success_rate:.1f}%{Color.END}")
        print(f"  Total duration: {duration:.1f}s")
        
        # Response time statistics
        if self.results:
            response_times = [r.response_time for r in self.results if r.response_time > 0]
            if response_times:
                avg_time = statistics.mean(response_times)
                median_time = statistics.median(response_times)
                max_time = max(response_times)
                min_time = min(response_times)
                
                print(f"\n{Color.BOLD}Response Time Statistics:{Color.END}")
                print(f"  Average: {avg_time:.2f}s")
                print(f"  Median: {median_time:.2f}s")
                print(f"  Min: {min_time:.2f}s")
                print(f"  Max: {max_time:.2f}s")
        
        # Category breakdown
        print(f"\n{Color.BOLD}Results by Category:{Color.END}")
        by_category = defaultdict(lambda: {"total": 0, "success": 0, "failed": 0})
        for result in self.results:
            by_category[result.category]["total"] += 1
            if result.success:
                by_category[result.category]["success"] += 1
            else:
                by_category[result.category]["failed"] += 1
        
        for category, stats in sorted(by_category.items()):
            rate = stats["success"] / stats["total"] * 100 if stats["total"] > 0 else 0
            color = Color.GREEN if rate >= 90 else Color.YELLOW if rate >= 70 else Color.RED
            print(f"  {category:30s} {color}{stats['success']:3d}/{stats['total']:3d} ({rate:5.1f}%){Color.END}")
        
        # Routing analysis
        print(f"\n{Color.BOLD}Routing Analysis:{Color.END}")
        routing_counts = defaultdict(int)
        for result in self.results:
            if result.routed_agent:
                routing_counts[result.routed_agent] += 1
        for agent, count in sorted(routing_counts.items(), key=lambda x: -x[1]):
            print(f"  {agent:30s} {count:3d} questions")
        
        # Failed tests details
        failed_results = [r for r in self.results if not r.success]
        if failed_results:
            print(f"\n{Color.BOLD}{Color.RED}Failed Tests Details:{Color.END}")
            for idx, result in enumerate(failed_results[:10], 1):  # Show first 10
                print(f"\n  {idx}. {Color.YELLOW}{result.question[:70]}...{Color.END}")
                print(f"     Category: {result.category} / {result.subcategory}")
                print(f"     Error: {Color.RED}{result.error}{Color.END}")
        
        # Validation warnings
        warnings = [r for r in self.results if r.validation_notes]
        if warnings:
            print(f"\n{Color.BOLD}{Color.YELLOW}Validation Warnings ({len(warnings)} tests):{Color.END}")
            warning_summary = defaultdict(int)
            for result in warnings:
                for note in result.validation_notes:
                    warning_summary[note] += 1
            for warning, count in sorted(warning_summary.items(), key=lambda x: -x[1])[:10]:
                print(f"  {count:3d}x {warning}")
        
        # Save detailed JSON report
        self._save_json_report(duration)
        
        print(f"\n{Color.BOLD}{'='*80}{Color.END}")
        print(f"{Color.GREEN}✓ Test suite completed!{Color.END}")
        print(f"{Color.BOLD}{'='*80}{Color.END}\n")
    
    def _save_json_report(self, duration: float):
        """Save detailed JSON report"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = RESULTS_DIR / f"libcal_test_report_{timestamp}.json"
        
        report = {
            "test_suite": "LibCal Comprehensive Test",
            "timestamp": datetime.now().isoformat(),
            "duration_seconds": duration,
            "summary": {
                "total_tests": len(self.results),
                "successful": sum(1 for r in self.results if r.success),
                "failed": sum(1 for r in self.results if not r.success),
                "success_rate": sum(1 for r in self.results if r.success) / len(self.results) * 100 if self.results else 0
            },
            "results": [r.to_dict() for r in self.results]
        }
        
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        print(f"\n{Color.CYAN}📄 Detailed report saved: {report_file}{Color.END}")


async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="LibCal Comprehensive Test Suite")
    parser.add_argument("--category", help="Test specific category only (e.g., library_hours)")
    parser.add_argument("--quick", action="store_true", help="Run quick mode (subset of tests)")
    args = parser.parse_args()
    
    tester = LibCalTester()
    await tester.run_tests(category_filter=args.category, quick_mode=args.quick)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\n{Color.YELLOW}Test interrupted by user{Color.END}")
        sys.exit(1)
