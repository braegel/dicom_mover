#!/usr/bin/env python3
"""
Detect local IP address helper
"""

import socket
import subprocess
import re
from typing import Optional


def get_local_ip_socket() -> Optional[str]:
    """
    Get local IP by creating a UDP socket.
    This doesn't actually send data, just determines which interface would be used.
    """
    try:
        # Create a socket to a public DNS server
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.1)
        # Connect to Google DNS (doesn't actually send data)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        return local_ip
    except Exception:
        return None


def get_local_ip_ifconfig() -> Optional[str]:
    """
    Get local IP using ifconfig command (macOS/Linux).
    Looks for 192.168.x.x addresses.
    """
    try:
        result = subprocess.run(['ifconfig'], capture_output=True, text=True, timeout=2)
        output = result.stdout

        # Find all inet addresses
        pattern = r'inet (\d+\.\d+\.\d+\.\d+)'
        matches = re.findall(pattern, output)

        # Filter for local network addresses (192.168.x.x)
        for ip in matches:
            if ip.startswith('192.168.') and ip != '192.168.1.1':
                return ip

        # If no 192.168.x.x found, return first non-localhost
        for ip in matches:
            if not ip.startswith('127.'):
                return ip

    except Exception:
        pass

    return None


def detect_local_ip() -> Optional[str]:
    """
    Detect the local IP address using multiple methods.
    Returns the most likely local network IP.
    """
    # Try socket method first (more reliable)
    ip = get_local_ip_socket()
    if ip and not ip.startswith('127.'):
        return ip

    # Fall back to ifconfig
    ip = get_local_ip_ifconfig()
    if ip:
        return ip

    return None


if __name__ == "__main__":
    ip = detect_local_ip()
    if ip:
        print(f"Detected local IP: {ip}")
    else:
        print("Could not detect local IP")
