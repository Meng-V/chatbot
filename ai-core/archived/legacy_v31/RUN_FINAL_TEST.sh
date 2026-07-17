#!/bin/bash

# Final Comprehensive Test Execution Script
# This script runs the complete test suite and generates all reports

echo "=============================================="
echo "FINAL COMPREHENSIVE TEST SUITE"
echo "=============================================="
echo ""

# Check if we're in the right directory
if [ ! -f "scripts/final_comprehensive_test.py" ]; then
    echo "❌ Error: Must run from ai-core directory"
    echo "   cd ai-core && ./RUN_FINAL_TEST.sh"
    exit 1
fi

# Check if server is running
echo "🔍 Checking if server is running..."
if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo "✅ Server is running"
else
    echo "❌ Server is not running!"
    echo ""
    echo "Please start the server first:"
    echo "  .venv/bin/uvicorn src.main:app_sio --host 0.0.0.0 --port 8000"
    echo ""
    exit 1
fi

echo ""
echo "🚀 Starting comprehensive test suite..."
echo "   This will take approximately 15-20 minutes"
echo "   Rate limit protection is enabled"
echo ""

# Run the test
python scripts/final_comprehensive_test.py

# Check exit code
if [ $? -eq 0 ]; then
    echo ""
    echo "=============================================="
    echo "✅ TEST COMPLETE"
    echo "=============================================="
    echo ""
    echo "📁 Results saved in: test_results/"
    echo ""
    echo "Next steps:"
    echo "1. Review the test report in test_results/"
    echo "2. Check for any failures or issues"
    echo "3. If tests pass (95%+), proceed with subject librarian testing"
    echo "4. Share LIBRARIAN_TESTING_INVITATION.md with the team"
    echo ""
else
    echo ""
    echo "=============================================="
    echo "❌ TEST FAILED"
    echo "=============================================="
    echo ""
    echo "Please check the error messages above"
    echo ""
    exit 1
fi
