#!/bin/bash

# Simple VSCode Extension Packager for Node.js 14
# This creates a basic .vsix package without using vsce

echo "Creating VSCode extension package..."

# Ensure compilation is up to date
npm run compile

# Create temporary directory structure
mkdir -p .temp-package

# Copy essential files
cp package.json .temp-package/
cp -r out .temp-package/
cp README.md .temp-package/ 2>/dev/null || echo "README.md not found, skipping"
cp LICENSE.txt .temp-package/ 2>/dev/null || echo "LICENSE.txt not found, skipping"

# Create a simple manifest
cat > .temp-package/extension.vsixmanifest << 'EOF'
<?xml version="1.0" encoding="utf-8"?>
<PackageManifest Version="2.0.0" xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011" xmlns:d="http://schemas.microsoft.com/developer/vsx-schema-design/2011">
  <Metadata>
    <Identity Language="en-US" Id="optimize-ai-vscode" Version="0.1.0" Publisher="optimize-ai"/>
    <DisplayName>Optimize AI - Code Compression</DisplayName>
    <Description>Intelligent code compression for AI-powered development</Description>
  </Metadata>
  <Installation>
    <InstallationTarget Id="Microsoft.VisualStudio.Code"/>
  </Installation>
  <Dependencies/>
  <Assets>
    <Asset Type="Microsoft.VisualStudio.Code.Manifest" Path="package.json"/>
  </Assets>
</PackageManifest>
EOF

# Create the package
cd .temp-package
zip -r ../optimize-ai-vscode-0.1.0.vsix * > /dev/null 2>&1
cd ..

# Cleanup
rm -rf .temp-package

if [ -f "optimize-ai-vscode-0.1.0.vsix" ]; then
    echo "✅ Package created successfully: optimize-ai-vscode-0.1.0.vsix"
    ls -la optimize-ai-vscode-0.1.0.vsix
else
    echo "❌ Package creation failed"
    exit 1
fi
