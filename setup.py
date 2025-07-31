# ===== setup.py =====
"""
Setup configuration for optimize-ai package.
"""

from setuptools import setup, find_packages
from pathlib import Path

# Read README for long description
readme_path = Path(__file__).parent / "README.md"
long_description = ""
try:
    if readme_path.exists():
        long_description = readme_path.read_text(encoding="utf-8")
except Exception as e:
    print(f"Warning: Could not read README.md: {e}")

# Read requirements
requirements_path = Path(__file__).parent / "requirements.txt"
requirements = []
try:
    if requirements_path.exists():
        requirements = [
            line.strip() 
            for line in requirements_path.read_text(encoding="utf-8").split('\n')
            if line.strip() and not line.startswith('#')
        ]
except Exception as e:
    print(f"Warning: Could not read requirements.txt: {e}")

setup(
    name="optimize-ai",
    version="0.1.0",  # Updated for MVP stage
    author="Optimize AI Team",
    author_email="team@optimize-ai.com",
    description="AI-powered code compression for 10x more efficient LLM interactions",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/optimize-ai/optimize-ai",
    license="MIT",
    packages=find_packages(exclude=["tests", "tests.*", "docs", "docs.*"]),
    classifiers=[
        "Development Status :: 3 - Alpha",  # Updated for MVP
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Software Development :: Code Generators",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.8",
    install_requires=requirements,
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-asyncio>=0.21.0",
            "pytest-cov>=4.0.0",
            "black>=23.0.0",
            "flake8>=6.0.0",
            "mypy>=1.0.0",
            "isort>=5.12.0",
        ],
        "docs": [
            "sphinx>=6.0.0",
            "sphinx-rtd-theme>=1.2.0",
            "sphinx-autodoc-typehints>=1.22.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "optimize-ai=cli.main:cli",
            "pycompress=cli.main:cli",  # Alternative name
        ],
    },
    include_package_data=True,
    package_data={
        "optimize_ai": [
            "integrations/vscode/package.json",
            "integrations/vscode/extension.json",
            "integrations/cursor/package.json",
            "integrations/cursor/extension.json",
            "integrations/claude/install.sh",
            "integrations/claude/claude-cai",
            "LICENSE",  # Include license file if present
        ],
    },
    keywords="ai code-compression llm-optimization python-optimizer",
    zip_safe=False,  # Safer for packages with data files
    project_urls={
        "Bug Reports": "https://github.com/optimize-ai/optimize-ai/issues",
        "Source": "https://github.com/optimize-ai/optimize-ai",
        "Documentation": "https://optimize-ai.readthedocs.io",
    },
)