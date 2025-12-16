#!/usr/bin/env python3
"""
OptimizeAI Server Startup Script
"""

import os
import subprocess
import sys
from pathlib import Path

def start_server():
    """Start the OptimizeAI FastAPI server"""
    
    # Set up environment
    project_root = Path(__file__).parent
    os.chdir(project_root)
    
    # Set PYTHONPATH
    env = os.environ.copy()
    env['PYTHONPATH'] = str(project_root)
    
    print("🚀 Starting OptimizeAI Server...")
    print(f"📁 Project root: {project_root}")
    print(f"🐍 Python path: {env['PYTHONPATH']}")
    print("🌐 Server will be available at: http://localhost:8000")
    print("📚 API docs available at: http://localhost:8000/docs")
    print("\n" + "="*50)
    
    try:
        # Start the server
        subprocess.run([
            '.venv/bin/python', '-m', 'uvicorn', 
            'app:app', 
            '--host', '0.0.0.0', 
            '--port', '8000',
            '--reload'  # Auto-reload on code changes
        ], env=env, check=True)
        
    except KeyboardInterrupt:
        print("\n🛑 Server stopped by user")
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to start server: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        sys.exit(1)

print('🚀 Starting Optimize AI Server...')
print('📍 Server will be available at: http://localhost:8000')
print('📚 API Documentation: http://localhost:8000/docs')
print('🛑 Press Ctrl+C to stop the server')
print('=' * 50)

try:
    import uvicorn
    from app import app
    
    # Start the server
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=8000,
        reload=False,  # Set to True for development
        log_level="info"
    )
except KeyboardInterrupt:
    print('\n👋 Server stopped by user')
except Exception as e:
    print(f'❌ Failed to start server: {e}')
    sys.exit(1)
