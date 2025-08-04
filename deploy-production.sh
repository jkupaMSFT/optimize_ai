#!/bin/bash

# Production deployment script for OptimizeAI

set -e

echo "🚀 Starting OptimizeAI Production Deployment..."

# Check if Docker and Docker Compose are installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    exit 1
fi

if ! command -v docker-compose &> /dev/null && ! command -v docker &> /dev/null; then
    echo "❌ Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

# Create necessary directories
echo "📁 Creating necessary directories..."
mkdir -p ./logs ./data
mkdir -p ./monitoring/grafana/provisioning/datasources
mkdir -p ./monitoring/grafana/provisioning/dashboards
mkdir -p ./monitoring/grafana/dashboards

# Set proper permissions
echo "🔒 Setting proper permissions..."
chmod +x ./deploy-production.sh
chmod 755 ./logs ./data

# Build and start services
echo "🏗️  Building and starting services..."
docker-compose down --remove-orphans
docker-compose build --no-cache
docker-compose up -d

# Wait for services to be ready
echo "⏳ Waiting for services to be ready..."
sleep 30

# Health check
echo "🔍 Performing health checks..."
if curl -f http://localhost:8000/health > /dev/null 2>&1; then
    echo "✅ OptimizeAI service is healthy"
else
    echo "❌ OptimizeAI service health check failed"
    docker-compose logs optimizeai
    exit 1
fi

if curl -f http://localhost:9090/-/ready > /dev/null 2>&1; then
    echo "✅ Prometheus is ready"
else
    echo "⚠️  Prometheus may not be ready yet"
fi

if curl -f http://localhost:3000/api/health > /dev/null 2>&1; then
    echo "✅ Grafana is ready"
else
    echo "⚠️  Grafana may not be ready yet"
fi

echo ""
echo "🎉 Production deployment completed!"
echo ""
echo "📊 Services are available at:"
echo "   - OptimizeAI API: http://localhost:8000"
echo "   - API Documentation: http://localhost:8000/docs"
echo "   - Prometheus: http://localhost:9090"
echo "   - Grafana: http://localhost:3000 (admin/admin)"
echo ""
echo "📝 To view logs: docker-compose logs -f [service-name]"
echo "🛑 To stop services: docker-compose down"
echo "🔄 To restart services: docker-compose restart"
echo ""
echo "🔧 For production use, please:"
echo "   1. Change default Grafana password"
echo "   2. Configure proper SSL/TLS certificates"
echo "   3. Set up proper backup procedures"
echo "   4. Configure log rotation"
echo "   5. Set up monitoring alerts"
