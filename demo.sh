#!/bin/bash
# demo.sh - Automated demo script

echo "🚀 OptimizeAI Production Demo"
echo "=============================="

# Check if we're in the right directory
if [ ! -f "start_server.py" ]; then
    echo "Error: Please run this script from the optimize_ai root directory"
    exit 1
fi

# Start server
echo "Starting OptimizeAI server..."
python start_server.py &
SERVER_PID=$!
sleep 3

# Demo 1: CLI Compression
echo -e "\n📝 Demo 1: CLI Compression"
python -m cli.main compress examples/large_module.py --verbose --output examples/large_module.cai

# Demo 2: Real-time VSCode Integration
echo -e "\n🔧 Demo 2: VSCode Integration"
if command -v code &> /dev/null; then
    code examples/demo_project
    echo "Watch the status bar for real-time compression stats!"
else
    echo "VSCode not found - skipping VSCode integration demo"
    echo "You can manually open examples/demo_project in your editor"
fi

# Demo 3: Web Dashboard
echo -e "\n🌐 Demo 3: Web Dashboard"
if command -v open &> /dev/null; then
    open http://localhost:8000/dashboard
    echo "Opening web dashboard in your browser!"
elif command -v xdg-open &> /dev/null; then
    xdg-open http://localhost:8000/dashboard
    echo "Opening web dashboard in your browser!"
else
    echo "Please open http://localhost:8000/dashboard in your browser"
fi

# Demo 4: API Integration
echo -e "\n🔌 Demo 4: API Integration"
if command -v curl &> /dev/null; then
    echo "Testing API compression..."
    if command -v jq &> /dev/null; then
        curl -X POST http://localhost:8000/minify \
          -H "Content-Type: application/json" \
          -d '{"code": "def calculate(x, y): return x * y + 10"}' | jq
    else
        curl -X POST http://localhost:8000/minify \
          -H "Content-Type: application/json" \
          -d '{"code": "def calculate(x, y): return x * y + 10"}'
    fi
else
    echo "curl not available - skipping API demo"
fi

# Wait for user input before cleanup
echo -e "\n⏸️  Press Enter to stop the demo and cleanup..."
read -r

# Cleanup
echo -e "\n🧹 Cleaning up..."
if [ ! -z "$SERVER_PID" ]; then
    kill $SERVER_PID 2>/dev/null
    echo "Server stopped"
fi

echo -e "\n✅ Demo Complete!"
echo "Thank you for trying OptimizeAI!"
