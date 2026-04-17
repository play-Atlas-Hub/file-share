"""
Configuration validation and environment variable handling.

Ensures all required config values are present and valid.
"""

import os
import json
from typing import Dict, Any, Tuple, Optional
from dotenv import load_dotenv
import logging

logger = logging.getLogger(__name__)


def load_env_file(env_path: str = ".env") -> None:
    """
    Load environment variables from .env file.

    Args:
        env_path: Path to .env file
    """
    if os.path.exists(env_path):
        load_dotenv(env_path)
        logger.info(f"Loaded environment variables from {env_path}")
    else:
        logger.warning(f"Environment file {env_path} not found")


def get_env_var(key: str, default: Optional[str] = None, required: bool = False) -> str:
    """
    Get environment variable with optional validation.

    Args:
        key: Environment variable name
        default: Default value if not set
        required: If True, raises error if not found

    Returns:
        Environment variable value

    Raises:
        ValueError: If required variable is not set
    """
    value = os.getenv(key, default)
    if required and value is None:
        raise ValueError(f"Required environment variable '{key}' not set")
    return value


def validate_config(config: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Validate configuration structure and values.

    Args:
        config: Configuration dictionary

    Returns:
        Tuple of (is_valid, error_message)
    """
    required_sections = [
        'server', 'world', 'player', 'bullet', 'blobs',
        'teams', 'tanks', 'upgrades', 'ranks', 'game_modes', 'chat'
    ]

    for section in required_sections:
        if section not in config:
            return False, f"Missing required config section: {section}"

    # Validate server config
    server = config.get('server', {})
    if not isinstance(server.get('port'), int) or server['port'] < 1024:
        return False, "Invalid server port"
    if not isinstance(server.get('max_players'), int) or server['max_players'] < 1:
        return False, "Invalid max_players"

    # Validate world config
    world = config.get('world', {})
    if world.get('width', 0) <= 0 or world.get('height', 0) <= 0:
        return False, "Invalid world dimensions"

    # Validate player config
    player = config.get('player', {})
    if player.get('speed', 0) <= 0 or player.get('radius', 0) <= 0:
        return False, "Invalid player config"

    # Validate game balance
    upgrades = config.get('upgrades', {})
    if upgrades.get('cost_per_upgrade', 0) <= 0:
        return False, "Invalid upgrade cost"

    return True, ""


def validate_env() -> Tuple[bool, str]:
    """
    Validate that all required environment variables are set.

    Returns:
        Tuple of (is_valid, error_message)
    """
    required_vars = {
        'JWT_SECRET': 'JSON Web Token secret key',
    }

    missing_vars = []
    for var, description in required_vars.items():
        if not os.getenv(var):
            missing_vars.append(f"{var} ({description})")

    if missing_vars:
        msg = f"Missing required environment variables: {', '.join(missing_vars)}"
        return False, msg

    # Warn about weak JWT secret
    jwt_secret = os.getenv('JWT_SECRET', '')
    if len(jwt_secret) < 32:
        logger.warning("JWT_SECRET is less than 32 characters. Use a stronger secret in production.")

    return True, ""


def sanitize_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sanitize config by removing sensitive information.

    Args:
        config: Configuration dictionary

    Returns:
        Sanitized copy of config
    """
    import copy
    sanitized = copy.deepcopy(config)

    # Remove admin credentials from admin section
    if 'admin' in sanitized and 'credentials' in sanitized['admin']:
        sanitized['admin']['credentials'] = {
            k: '***REDACTED***' for k in sanitized['admin']['credentials'].keys()
        }

    return sanitized
