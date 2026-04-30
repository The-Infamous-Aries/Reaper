import socket
import threading
import logging
from typing import Optional, Dict, List, Tuple
from contextlib import contextmanager
import psutil
import subprocess
import os
import asyncio
import re

logger = logging.getLogger("Reaper.PortManager")

class PortManager:
    """
    Centralized port management system for handling multiple web servers
    across different cogs without port conflicts.
    """
    
    def __init__(self, start_port: int = 8000, max_port: int = 9000):
        self.start_port = start_port
        self.max_port = max_port
        self.allocated_ports: Dict[str, int] = {}
        self.port_locks: Dict[int, threading.Lock] = {}
        self._lock = threading.Lock()
        self._port_test_cache: Dict[int, bool] = {}
        
    def is_port_available(self, port: int, host: str = "0.0.0.0") -> bool:
        """Test if a port is available for binding."""
        if port in self._port_test_cache:
            return self._port_test_cache[port]
            
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                result = s.connect_ex((host, port))
                is_available = result != 0  # Port is available if connection fails
                self._port_test_cache[port] = is_available
                return is_available
        except Exception as e:
            logger.warning(f"Error testing port {port}: {e}")
            return False
    
    def find_available_port(self, start_port: Optional[int] = None, host: str = "0.0.0.0") -> Optional[int]:
        """Find the next available port starting from start_port."""
        if start_port is None:
            start_port = self.start_port
            
        for port in range(start_port, self.max_port + 1):
            if self.is_port_available(port, host):
                return port
                
        logger.error(f"No available ports found in range {start_port}-{self.max_port}")
        return None
    
    def allocate_port(self, service_name: str, preferred_port: Optional[int] = None) -> int:
        """
        Allocate a port for a specific service.
        
        Args:
            service_name: Unique name for the service
            preferred_port: Preferred port number (optional)
            
        Returns:
            Allocated port number
            
        Raises:
            RuntimeError: If no ports are available
        """
        with self._lock:
            # Check if service already has an allocated port
            if service_name in self.allocated_ports:
                existing_port = self.allocated_ports[service_name]
                logger.info(f"Service '{service_name}' already allocated port {existing_port}")
                return existing_port
            
            # Try preferred port first
            if preferred_port and self.is_port_available(preferred_port):
                self.allocated_ports[service_name] = preferred_port
                self.port_locks[preferred_port] = threading.Lock()
                logger.info(f"Allocated preferred port {preferred_port} to service '{service_name}'")
                return preferred_port
            
            # Find next available port
            available_port = self.find_available_port()
            if available_port is None:
                raise RuntimeError(f"No available ports for service '{service_name}'")
            
            self.allocated_ports[service_name] = available_port
            self.port_locks[available_port] = threading.Lock()
            logger.info(f"Allocated port {available_port} to service '{service_name}'")
            return available_port
    
    def release_port(self, service_name: str) -> bool:
        """Release an allocated port."""
        with self._lock:
            if service_name not in self.allocated_ports:
                logger.warning(f"Service '{service_name}' has no allocated port to release")
                return False
            
            port = self.allocated_ports.pop(service_name)
            self.port_locks.pop(port, None)
            self._port_test_cache.pop(port, None)  # Clear cache for this port
            logger.info(f"Released port {port} from service '{service_name}'")
            return True
    
    def get_allocated_port(self, service_name: str) -> Optional[int]:
        """Get the allocated port for a service."""
        with self._lock:
            return self.allocated_ports.get(service_name)
    
    def get_all_allocated_ports(self) -> Dict[str, int]:
        """Get all allocated ports."""
        with self._lock:
            return self.allocated_ports.copy()
    
    def is_port_allocated(self, port: int) -> bool:
        """Check if a port is currently allocated."""
        with self._lock:
            return port in self.allocated_ports.values()
    
    def get_service_by_port(self, port: int) -> Optional[str]:
        """Get the service name for a given port."""
        with self._lock:
            for service_name, allocated_port in self.allocated_ports.items():
                if allocated_port == port:
                    return service_name
            return None
    
    @contextmanager
    def port_context(self, service_name: str, preferred_port: Optional[int] = None):
        """
        Context manager for port allocation.
        
        Usage:
            with port_manager.port_context("my_service") as port:
                # Use the allocated port
                start_server(port)
        """
        port = self.allocate_port(service_name, preferred_port)
        try:
            yield port
        finally:
            self.release_port(service_name)
    
    def clear_cache(self):
        """Clear the port test cache."""
        with self._lock:
            self._port_test_cache.clear()
            logger.info("Port test cache cleared")


# Global port manager instance
_global_port_manager: Optional[PortManager] = None

def get_port_manager() -> PortManager:
    """Get the global port manager instance."""
    global _global_port_manager
    if _global_port_manager is None:
        _global_port_manager = PortManager()
    return _global_port_manager

def get_local_ip():
    """Get the local IP address of the machine."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Connect to a remote address to determine local IP
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

def find_available_port(start_port: int = 8000, max_port: int = 9000) -> Optional[int]:
    """Find an available port in the given range."""
    manager = get_port_manager()
    manager.start_port = start_port
    manager.max_port = max_port
    return manager.find_available_port()

def allocate_port(service_name: str, preferred_port: Optional[int] = None) -> int:
    """Allocate a port for a service."""
    return get_port_manager().allocate_port(service_name, preferred_port)

def release_port(service_name: str) -> bool:
    """Release an allocated port."""
    return get_port_manager().release_port(service_name)

SERVICE_WEB_SERVER = "fastapi_web_server"
SERVICE_CLOUDFLARE = "cloudflare_tunnel"

def initialize_service_ports():
    """Initialize and clear ports for all required services."""
    manager = get_port_manager()
    
    # Kill existing processes on preferred ports
    kill_process_on_port(8080) # For FastAPI
    kill_process_on_port(8005) # For Cloudflare
    
    # Allocate ports
    manager.allocate_port(SERVICE_WEB_SERVER, preferred_port=8080)
    manager.allocate_port(SERVICE_CLOUDFLARE, preferred_port=8005)

def get_allocated_port(service_name: str) -> Optional[int]:
    """Get the allocated port for a service."""
    return get_port_manager().get_allocated_port(service_name)

def is_port_available(port: int, host: str = "0.0.0.0") -> bool:
    """Check if a port is available."""
    return get_port_manager().is_port_available(port, host)

def get_service_by_port(port: int) -> Optional[str]:
    """Get the service name for a given port."""
    return get_port_manager().get_service_by_port(port)

# Service name constants for consistent naming
SERVICE_WARS_BD = "war_costs_bd"
SERVICE_WARS_NET_BD = "wars_net_bd"
SERVICE_COMPARE = "compare"
SERVICE_UNIVERSE = "universe"
SERVICE_BASEBALL = "baseball"
SERVICE_RESOURCE_STOCKS = "resource_stocks"
SERVICE_WEB_SERVER = "fastapi_web_server"
SERVICE_CLOUDFLARE = "cloudflare_tunnel"

# Default port ranges for different services
DEFAULT_PORTS = {
    SERVICE_WARS_BD: 8000,
    SERVICE_WARS_NET_BD: 8005,
    SERVICE_COMPARE: 8001,
    SERVICE_UNIVERSE: 8002,
    SERVICE_BASEBALL: 8003,
    SERVICE_RESOURCE_STOCKS: 8004,
    SERVICE_WEB_SERVER: 8080,
    SERVICE_CLOUDFLARE: 8005,
}

def get_service_port(service_name: str) -> int:
    """Get the default port for a service, allocating if necessary."""
    manager = get_port_manager()
    
    # Check if already allocated
    allocated_port = manager.get_allocated_port(service_name)
    if allocated_port:
        return allocated_port
    
    # Try to allocate the default port
    preferred_port = DEFAULT_PORTS.get(service_name)
    return manager.allocate_port(service_name, preferred_port)

def cleanup_service_ports():
    """Clean up all allocated service ports. Call this during bot shutdown."""
    manager = get_port_manager()
    
    logger.info("Cleaning up service ports...")
    allocated_ports = manager.get_all_allocated_ports()
    
    for service_name in list(allocated_ports.keys()):
        try:
            manager.release_port(service_name)
            logger.info(f"Released port for service '{service_name}'")
        except Exception as e:
            logger.error(f"Error releasing port for service '{service_name}': {e}")

def kill_process_on_port(port: int):
    """Find and kill the process that is using the given port, ignoring system processes."""
    # On Windows, PID 0 is System Idle, and PID 4 is System. These cannot and should not be killed.
    protected_pids = [0, 4]
    
    for conn in psutil.net_connections():
        if conn.laddr and conn.laddr.port == port:
            if conn.pid is None or conn.pid in protected_pids:
                continue  # Skip if PID is None or a protected system process
            
            try:
                process = psutil.Process(conn.pid)
                logger.info(f"Attempting to kill process '{process.name()}' (PID: {conn.pid}) using port {port}")
                process.kill()
                process.wait(timeout=3) # Wait for the process to terminate
                logger.info(f"Successfully killed process '{process.name()}' (PID: {conn.pid})")
            except psutil.NoSuchProcess:
                # This can happen in a race condition where the process ends before we kill it.
                logger.warning(f"Process with PID {conn.pid} on port {port} no longer exists.")
            except (psutil.AccessDenied, PermissionError) as e:
                logger.error(f"Access denied to kill process '{process.name()}' (PID: {conn.pid}) on port {port}: {e}")
            except Exception as e:
                logger.error(f"An unexpected error occurred while trying to kill process on port {port}: {e}")

# Cloudflare Tunnel Management
_tunnel_process = None

def is_cloudflared_installed() -> bool:
    """Check if cloudflared is installed and accessible."""
    try:
        result = subprocess.run(['cloudflared.exe', 'version'], 
                              capture_output=True, text=True, timeout=10)
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False

def get_cloudflared_path() -> Optional[str]:
    """Get the path to cloudflared executable."""
    # Check current directory first
    local_path = os.path.join(os.getcwd(), 'cloudflared.exe')
    if os.path.exists(local_path):
        return local_path
    
    # Check if it's in PATH
    try:
        result = subprocess.run(['where', 'cloudflared.exe'], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return result.stdout.strip().split('\n')[0]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    
    return None

def ensure_cloudflared_config() -> bool:
    """Ensure cloudflared configuration files exist."""
    config_dir = os.path.join(os.getcwd(), 'cloudflared-config')
    config_file = os.path.join(config_dir, 'config.yml')
    creds_file = os.path.join(config_dir, 'creds.json')
    
    # Check if config directory exists
    if not os.path.exists(config_dir):
        try:
            os.makedirs(config_dir)
            logger.info(f"Created cloudflared config directory: {config_dir}")
        except Exception as e:
            logger.error(f"Failed to create config directory: {e}")
            return False
    
    # Check if config file exists
    if not os.path.exists(config_file):
        logger.error(f"Cloudflare tunnel config file not found: {config_file}")
        logger.error("Please run the tunnel setup process first.")
        return False
    
    # Check if credentials file exists
    if not os.path.exists(creds_file):
        logger.error(f"Cloudflare tunnel credentials file not found: {creds_file}")
        logger.error("Please run the tunnel setup process first.")
        return False
    
    return True

def start_cloudflare_tunnel_process() -> Optional[subprocess.Popen]:
    """Start the Cloudflare tunnel process."""
    global _tunnel_process
    
    # Check if already running
    if _tunnel_process and _tunnel_process.poll() is None:
        logger.info("Cloudflare tunnel is already running")
        return _tunnel_process
    
    # Ensure cloudflared is installed
    if not is_cloudflared_installed():
        logger.error("cloudflared.exe is not installed or not accessible")
        return None
    
    # Ensure config files exist
    if not ensure_cloudflared_config():
        return None
    
    # Kill any existing cloudflared processes
    try:
        for proc in psutil.process_iter(['pid', 'name']):
            if proc.info['name'] and 'cloudflared' in proc.info['name'].lower():
                logger.info(f"Killing existing cloudflared process: PID {proc.info['pid']}")
                proc.kill()
                proc.wait(timeout=5)
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired):
        pass
    
    try:
        # Start Cloudflare tunnel
        config_path = os.path.join(os.getcwd(), 'cloudflared-config', 'config.yml')
        cmd = [
            'cloudflared.exe',
            'tunnel', 
            '--config', config_path,
            'run', 'discord-bot'
        ]
        
        logger.info("Starting Cloudflare tunnel...")
        _tunnel_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=os.getcwd()
        )
        
        logger.info("Cloudflare tunnel process started")
        return _tunnel_process
        
    except Exception as e:
        logger.error(f"Error starting Cloudflare tunnel: {e}")
        return None

def stop_cloudflare_tunnel_process() -> bool:
    """Stop the Cloudflare tunnel process."""
    global _tunnel_process
    
    if not _tunnel_process:
        logger.info("No Cloudflare tunnel process to stop")
        return True
    
    try:
        logger.info("Stopping Cloudflare tunnel...")
        _tunnel_process.terminate()
        
        # Wait for graceful termination
        try:
            _tunnel_process.wait(timeout=10)
            logger.info("Cloudflare tunnel stopped successfully")
        except subprocess.TimeoutExpired:
            logger.warning("Cloudflare tunnel did not stop gracefully, forcing kill...")
            _tunnel_process.kill()
            _tunnel_process.wait()
            logger.info("Cloudflare tunnel forcefully stopped")
        
        _tunnel_process = None
        return True
        
    except Exception as e:
        logger.error(f"Error stopping Cloudflare tunnel: {e}")
        return False

def get_tunnel_public_url() -> str:
    """Get the public URL for the Cloudflare tunnel."""
    return "https://reaper.qzz.io"

def is_tunnel_running() -> bool:
    """Check if the Cloudflare tunnel is running."""
    global _tunnel_process
    return _tunnel_process is not None and _tunnel_process.poll() is None

# --- Consolidated Cloudflare Tunnel Management for Web Server Integration ---

# Global tunnel process and public URL for web server integration
_web_tunnel_process = None
_web_public_url = None

import time

async def start_cloudflare_tunnel_async():
    """Start the Cloudflare tunnel and wait for the public URL."""
    global _web_tunnel_process, _web_public_url
    
    from Systems.Functions.config import USE_CLOUDFLARE_TUNNEL
    
    if not USE_CLOUDFLARE_TUNNEL:
        logger.info("Cloudflare tunnel is disabled. Using custom domain configuration.")
        return
    
    if _web_tunnel_process and _web_tunnel_process.returncode is None:
        logger.info("Cloudflare tunnel is already running.")
        return

    if not is_cloudflared_installed():
        logger.error("cloudflared.exe not found.")
        return

    # Import tunnel configuration
    from Systems.Functions.config import CF_TUNNEL_ID, CUSTOM_DOMAIN

    config_path = os.path.join(os.getcwd(), 'cloudflared-config', 'config.yml')
    
    if not os.path.exists(config_path):
        logger.error(f"Cloudflare config file not found at {config_path}")
        # Fallback to generic tunnel if config is missing
        cmd = ['cloudflared.exe', 'tunnel', '--url', f'http://localhost:{get_service_port(SERVICE_WEB_SERVER)}']
        logger.warning(f"Starting generic Cloudflare tunnel because config was not found.")
    else:
        # Use the config file to run the tunnel
        cmd = [
            'cloudflared.exe',
            'tunnel',
            '--config',
            config_path,
            'run'
        ]
        logger.info(f"Starting Cloudflare tunnel for domain: {CUSTOM_DOMAIN} using config.")
    
    log_file = os.path.join(os.getcwd(), 'site_debug.log')
    
    log_stream = open(log_file, 'w')
    _web_tunnel_process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=log_stream
    )

    # For named tunnels, the public URL is the custom domain.
    if CF_TUNNEL_ID or CF_CREDENTIALS_FILE:
        _web_public_url = CUSTOM_DOMAIN
        logger.info(f"*** Tunnel started. Public URL will be: {CUSTOM_DOMAIN} ***")
        # Give the tunnel a moment to establish connection
        await asyncio.sleep(5)
        return

    # This part is for generic tunnels that create a random URL.
    url_regex = re.compile(r'(https://[a-zA-Z0-9-]+\.trycloudflare\.com)')
    timeout = 20
    start_time = time.time()

    while time.time() - start_time < timeout:
        try:
            with open(log_file, 'r') as f:
                for line in f:
                    match = url_regex.search(line)
                    if match:
                        _web_public_url = match.group(1)
                        logger.info(f"*** Public URL detected: {_web_public_url} ***")
                        return
        except FileNotFoundError:
            pass
        except Exception as e:
            logger.error(f"Error reading cloudflared log file: {e}")

        await asyncio.sleep(1)

    logger.error("Timed out waiting for Cloudflare tunnel URL.")


async def stop_cloudflare_tunnel_async():
    """Stop the Cloudflare tunnel process for the web server."""
    global _web_tunnel_process, _web_public_url
    
    if not _web_tunnel_process:
        logger.info("No Cloudflare tunnel process to stop for web server")
        return True
    
    try:
        logger.info("Stopping Cloudflare tunnel for web server...")
        _web_tunnel_process.terminate()
        
        # Wait for graceful termination
        await _web_tunnel_process.wait()
        logger.info("Cloudflare tunnel stopped successfully for web server")
        
        _web_tunnel_process = None
        _web_public_url = None
        return True
        
    except Exception as e:
        logger.error(f"Error stopping Cloudflare tunnel for web server: {e}")
        return False

async def monitor_tunnel_and_server(bot=None):
    """Monitors the Cloudflare tunnel and web server, restarting them if they fail."""
    import aiohttp
    global _web_tunnel_process

    from Systems.Functions.config import USE_CLOUDFLARE_TUNNEL

    logger.info("Tunnel and server monitor started.")
    web_server_port = get_service_port(SERVICE_WEB_SERVER)
    health_check_url = f"http://localhost:{web_server_port}/health"

    while True:
        await asyncio.sleep(60)  # Check every 60 seconds

        # Check web server health
        server_ok = False
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(health_check_url, timeout=5) as response:
                    if response.status == 200:
                        server_ok = True
        except Exception as e:
            logger.warning(f"Web server health check failed: {e}")

        if not server_ok:
            logger.error("Web server is unresponsive. A bot restart may be required as it cannot be restarted from here.")

        # Check Cloudflare tunnel process if it's enabled
        if USE_CLOUDFLARE_TUNNEL:
            if _web_tunnel_process and _web_tunnel_process.returncode is None:
                logger.info("Cloudflare tunnel is running normally for web server.")
            else:
                logger.warning("Cloudflare tunnel process is not running for web server. Attempting to restart...")
                try:
                    await start_cloudflare_tunnel_async()
                except Exception as e:
                    logger.error(f"Failed to restart Cloudflare tunnel for web server: {e}")

def get_web_public_url() -> str:
    """Returns the public URL for the web server."""
    from Systems.Functions.config import CUSTOM_DOMAIN, USE_CLOUDFLARE_TUNNEL
    
    # If Cloudflare tunnel is enabled and running, use dynamic URL
    if USE_CLOUDFLARE_TUNNEL and _web_public_url:
        return _web_public_url
    
    # Otherwise, use the configured custom domain
    return CUSTOM_DOMAIN

def is_web_tunnel_running() -> bool:
    """Check if the Cloudflare tunnel for the web server is running."""
    global _web_tunnel_process
    return _web_tunnel_process is not None and _web_tunnel_process.returncode is None
