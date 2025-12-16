#!/usr/bin/env python3
"""
Production Deployment Configuration Validator
Validates all configuration files for the production deployment.
"""

import os
import yaml
import json
from pathlib import Path
from typing import Dict, Any, List

class ProductionConfigValidator:
    def __init__(self):
        self.base_path = Path.cwd()
        self.errors: List[str] = []
        self.warnings: List[str] = []
        
    def validate_docker_compose(self) -> bool:
        """Validate docker-compose.yml structure."""
        compose_file = self.base_path / "docker-compose.yml"
        
        if not compose_file.exists():
            self.errors.append("docker-compose.yml not found")
            return False
            
        try:
            with open(compose_file, 'r') as f:
                compose_config = yaml.safe_load(f)
                
            # Check required services
            required_services = ['optimizeai', 'prometheus', 'grafana']
            services = compose_config.get('services', {})
            
            for service in required_services:
                if service not in services:
                    self.errors.append(f"Missing required service: {service}")
                    
            # Check OptimizeAI service configuration
            optimizeai = services.get('optimizeai', {})
            if 'build' not in optimizeai:
                self.errors.append("OptimizeAI service missing build configuration")
            if 'ports' not in optimizeai or '8000:8000' not in optimizeai['ports']:
                self.errors.append("OptimizeAI service missing correct port mapping")
                
            # Check environment variables
            env_vars = optimizeai.get('environment', [])
            required_env = ['ENVIRONMENT=production', 'LOG_LEVEL=INFO', 'METRICS_ENABLED=true']
            for required in required_env:
                if required not in env_vars:
                    self.warnings.append(f"OptimizeAI missing recommended environment variable: {required}")
                    
            print("✅ Docker Compose configuration is valid")
            return True
            
        except yaml.YAMLError as e:
            self.errors.append(f"Invalid YAML in docker-compose.yml: {e}")
            return False
        except Exception as e:
            self.errors.append(f"Error validating docker-compose.yml: {e}")
            return False
    
    def validate_dockerfile(self) -> bool:
        """Validate Dockerfile."""
        dockerfile = self.base_path / "Dockerfile"
        
        if not dockerfile.exists():
            self.errors.append("Dockerfile not found")
            return False
            
        try:
            with open(dockerfile, 'r') as f:
                content = f.read()
                
            required_instructions = ['FROM', 'WORKDIR', 'COPY', 'EXPOSE', 'CMD', 'HEALTHCHECK']
            for instruction in required_instructions:
                if instruction not in content:
                    self.warnings.append(f"Dockerfile missing recommended instruction: {instruction}")
                    
            if 'EXPOSE 8000' not in content:
                self.errors.append("Dockerfile not exposing port 8000")
                
            if 'HEALTHCHECK' not in content:
                self.warnings.append("Dockerfile missing health check")
                
            print("✅ Dockerfile configuration is valid")
            return True
            
        except Exception as e:
            self.errors.append(f"Error validating Dockerfile: {e}")
            return False
    
    def validate_prometheus_config(self) -> bool:
        """Validate Prometheus configuration."""
        prometheus_file = self.base_path / "monitoring" / "prometheus.yml"
        
        if not prometheus_file.exists():
            self.errors.append("monitoring/prometheus.yml not found")
            return False
            
        try:
            with open(prometheus_file, 'r') as f:
                prometheus_config = yaml.safe_load(f)
                
            # Check scrape configs
            scrape_configs = prometheus_config.get('scrape_configs', [])
            optimize_ai_job = None
            
            for job in scrape_configs:
                if job.get('job_name') == 'optimize-ai':
                    optimize_ai_job = job
                    break
                    
            if not optimize_ai_job:
                self.errors.append("Prometheus config missing optimize-ai scrape job")
                return False
                
            # Check targets
            targets = optimize_ai_job.get('static_configs', [{}])[0].get('targets', [])
            if 'optimizeai:8000' not in targets:
                self.errors.append("Prometheus config missing correct OptimizeAI target")
                
            print("✅ Prometheus configuration is valid")
            return True
            
        except yaml.YAMLError as e:
            self.errors.append(f"Invalid YAML in prometheus.yml: {e}")
            return False
        except Exception as e:
            self.errors.append(f"Error validating prometheus.yml: {e}")
            return False
    
    def validate_grafana_config(self) -> bool:
        """Validate Grafana configuration."""
        # Check datasource config
        datasource_file = self.base_path / "monitoring" / "grafana" / "provisioning" / "datasources" / "prometheus.yml"
        
        if not datasource_file.exists():
            self.errors.append("Grafana datasource configuration not found")
            return False
            
        try:
            with open(datasource_file, 'r') as f:
                datasource_config = yaml.safe_load(f)
                
            datasources = datasource_config.get('datasources', [])
            if not datasources:
                self.errors.append("No Grafana datasources configured")
                return False
                
            prometheus_ds = datasources[0]
            if prometheus_ds.get('url') != 'http://prometheus:9090':
                self.errors.append("Grafana datasource URL incorrect")
                
            print("✅ Grafana datasource configuration is valid")
            
        except Exception as e:
            self.errors.append(f"Error validating Grafana datasource config: {e}")
            return False
        
        # Check dashboard config
        dashboard_file = self.base_path / "monitoring" / "grafana" / "dashboards" / "optimize-ai-dashboard.json"
        
        if not dashboard_file.exists():
            self.warnings.append("OptimizeAI dashboard not found")
            return True
            
        try:
            with open(dashboard_file, 'r') as f:
                dashboard_config = json.load(f)
                
            if 'title' not in dashboard_config:
                self.warnings.append("Dashboard missing title")
                
            if 'panels' not in dashboard_config or not dashboard_config['panels']:
                self.warnings.append("Dashboard has no panels")
                
            print("✅ Grafana dashboard configuration is valid")
            return True
            
        except json.JSONDecodeError as e:
            self.errors.append(f"Invalid JSON in dashboard config: {e}")
            return False
        except Exception as e:
            self.errors.append(f"Error validating dashboard config: {e}")
            return False
    
    def validate_environment_config(self) -> bool:
        """Validate environment configuration."""
        env_file = self.base_path / ".env.production"
        
        if not env_file.exists():
            self.warnings.append(".env.production not found")
            return True
            
        try:
            with open(env_file, 'r') as f:
                content = f.read()
                
            required_vars = ['ENVIRONMENT', 'LOG_LEVEL', 'HOST', 'PORT', 'METRICS_ENABLED']
            for var in required_vars:
                if f"{var}=" not in content:
                    self.warnings.append(f"Environment file missing variable: {var}")
                    
            print("✅ Environment configuration is valid")
            return True
            
        except Exception as e:
            self.errors.append(f"Error validating environment config: {e}")
            return False
    
    def validate_deployment_script(self) -> bool:
        """Validate deployment script."""
        script_file = self.base_path / "deploy-production.sh"
        
        if not script_file.exists():
            self.errors.append("deploy-production.sh not found")
            return False
            
        if not os.access(script_file, os.X_OK):
            self.warnings.append("deploy-production.sh is not executable")
            
        print("✅ Deployment script exists")
        return True
    
    def run_validation(self) -> bool:
        """Run all validation checks."""
        print("🔍 Validating Production Deployment Configuration...")
        print("=" * 60)
        
        validators = [
            ("Docker Compose", self.validate_docker_compose),
            ("Dockerfile", self.validate_dockerfile),
            ("Prometheus Config", self.validate_prometheus_config),
            ("Grafana Config", self.validate_grafana_config),
            ("Environment Config", self.validate_environment_config),
            ("Deployment Script", self.validate_deployment_script),
        ]
        
        success_count = 0
        
        for name, validator in validators:
            print(f"\n🔍 Validating {name}...")
            try:
                if validator():
                    success_count += 1
            except Exception as e:
                self.errors.append(f"Validator {name} failed with exception: {e}")
        
        print("\n" + "=" * 60)
        print(f"📊 Validation Results: {success_count}/{len(validators)} validators passed")
        
        if self.warnings:
            print(f"\n⚠️  Warnings ({len(self.warnings)}):")
            for warning in self.warnings:
                print(f"   - {warning}")
        
        if self.errors:
            print(f"\n❌ Errors ({len(self.errors)}):")
            for error in self.errors:
                print(f"   - {error}")
            return False
        else:
            print("\n🎉 All validations passed! Production deployment configuration is ready.")
            return True

def main():
    """Main validation function."""
    validator = ProductionConfigValidator()
    success = validator.run_validation()
    
    if success:
        print("\n✅ Production deployment configuration validated successfully!")
        print("\nNext steps:")
        print("1. Install Docker and Docker Compose")
        print("2. Run: ./deploy-production.sh")
        print("3. Test with: python test_production_deployment.py")
        return 0
    else:
        print("\n❌ Configuration validation failed. Please fix the errors above.")
        return 1

if __name__ == "__main__":
    import sys
    sys.exit(main())
