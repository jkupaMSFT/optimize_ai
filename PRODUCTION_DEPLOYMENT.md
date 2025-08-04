# OptimizeAI Production Deployment Guide

This guide explains how to deploy OptimizeAI in a production environment using Docker and Docker Compose.

## Prerequisites

- Docker (version 20.10 or higher)
- Docker Compose (version 1.29 or higher)
- curl (for health checks)

## Quick Start

1. **Deploy the application:**

   ```bash
   ./deploy-production.sh
   ```

2. **Verify deployment:**
   ```bash
   python test_production_deployment.py
   ```

## Services

The production deployment includes:

### OptimizeAI API (Port 8000)

- Main application service
- Provides code minification and translation APIs
- Health check endpoint: `/health`
- API documentation: `/docs`

### Prometheus (Port 9090)

- Metrics collection and monitoring
- Scrapes metrics from OptimizeAI API
- Web interface: `http://localhost:9090`

### Grafana (Port 3000)

- Visualization and dashboards
- Pre-configured OptimizeAI dashboard
- Default login: admin/admin
- Web interface: `http://localhost:3000`

## Configuration

### Environment Variables

The following environment variables can be configured in `.env.production`:

- `ENVIRONMENT`: deployment environment (production/development)
- `LOG_LEVEL`: logging level (DEBUG/INFO/WARNING/ERROR)
- `HOST`: server host (default: 0.0.0.0)
- `PORT`: server port (default: 8000)
- `METRICS_ENABLED`: enable metrics collection (true/false)

### Docker Compose Override

For custom configuration, create a `docker-compose.override.yml` file:

```yaml
version: "3.8"

services:
  optimizeai:
    environment:
      - CUSTOM_ENV_VAR=value
    volumes:
      - ./custom-config:/app/config
```

## Monitoring

### Health Checks

All services include health checks:

- **OptimizeAI**: `curl http://localhost:8000/health`
- **Prometheus**: `curl http://localhost:9090/-/ready`
- **Grafana**: `curl http://localhost:3000/api/health`

### Logs

View service logs:

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f optimizeai
docker-compose logs -f prometheus
docker-compose logs -f grafana
```

### Metrics

Access metrics at:

- Prometheus metrics: `http://localhost:9090`
- Application metrics: `http://localhost:8000/metrics`
- Grafana dashboards: `http://localhost:3000`

## Maintenance

### Starting Services

```bash
docker-compose up -d
```

### Stopping Services

```bash
docker-compose down
```

### Restarting Services

```bash
docker-compose restart
```

### Updating the Application

1. Pull latest changes
2. Rebuild and restart:
   ```bash
   docker-compose down
   docker-compose build --no-cache
   docker-compose up -d
   ```

### Backup

Important data to backup:

- Application logs: `./logs/`
- Grafana dashboards: `grafana_data` volume
- Prometheus data: `prometheus_data` volume

## Security Considerations

### Production Checklist

- [ ] Change default Grafana password
- [ ] Configure SSL/TLS certificates
- [ ] Set up firewall rules
- [ ] Configure log rotation
- [ ] Set up backup procedures
- [ ] Configure monitoring alerts
- [ ] Review CORS settings
- [ ] Set proper file permissions

### SSL/TLS Setup

For production, configure a reverse proxy (nginx/traefik) with SSL:

```nginx
server {
    listen 443 ssl;
    server_name your-domain.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## Troubleshooting

### Common Issues

1. **Port conflicts**: Ensure ports 8000, 9090, and 3000 are available
2. **Permission errors**: Check file permissions in logs and data directories
3. **Memory issues**: Ensure sufficient memory for all services

### Debug Commands

```bash
# Check service status
docker-compose ps

# View resource usage
docker stats

# Check container logs
docker-compose logs [service-name]

# Execute command in container
docker-compose exec optimizeai bash
```

### Performance Tuning

For high-load environments:

1. Increase worker processes in Dockerfile
2. Configure resource limits in docker-compose.yml
3. Set up load balancing
4. Optimize database connections
5. Configure caching

## Support

For issues and support:

1. Check the application logs
2. Verify service health checks
3. Review configuration files
4. Test with the provided test script
