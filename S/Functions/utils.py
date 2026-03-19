import socket
import threading
import logging
from typing import Optional, Dict, List, Tuple
from contextlib import contextmanager

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
SERVICE_WARS_BD = "wars_bd"
SERVICE_COMPARE = "compare"
SERVICE_UNIVERSE = "universe"
SERVICE_BASEBALL = "baseball"
SERVICE_RESOURCE_STOCKS = "resource_stocks"

# Default port ranges for different services
DEFAULT_PORTS = {
    SERVICE_WARS_BD: 8000,
    SERVICE_COMPARE: 8001,
    SERVICE_UNIVERSE: 8002,
    SERVICE_BASEBALL: 8003,
    SERVICE_RESOURCE_STOCKS: 8004,
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

def initialize_service_ports():
    """Initialize all service ports. Call this during bot startup."""
    manager = get_port_manager()
    
    logger.info("Initializing service ports...")
    for service_name, default_port in DEFAULT_PORTS.items():
        try:
            allocated_port = manager.allocate_port(service_name, default_port)
            logger.info(f"Service '{service_name}' allocated port {allocated_port}")
        except RuntimeError as e:
            logger.error(f"Failed to allocate port for service '{service_name}': {e}")
            # Try to find any available port
            try:
                allocated_port = manager.allocate_port(service_name)
                logger.info(f"Service '{service_name}' allocated fallback port {allocated_port}")
            except RuntimeError:
                logger.error(f"No ports available for service '{service_name}'")
    
    logger.info("Service port initialization complete")
    return manager.get_all_allocated_ports()

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
    
    logger.info("Service port cleanup complete")