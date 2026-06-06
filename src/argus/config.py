"""Simple JSON config for Argus providers, tools, and agent defaults.

Schema:
- `default_provider`: name of the provider to use by default.
- `providers`: map of provider names to provider configs.
- `tools`: simple registry settings for local and future MCP tools.
- `agent`: small agent settings used by the graph.

For now, only `openai-compatible` providers are supported.
API keys are never stored in this file. Instead, each provider points to the
environment variable name that should contain the key.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, TypedDict


class ProviderModelConfig(TypedDict):
    default: str


class OpenAICompatibleProviderConfig(TypedDict):
    type: str
    base_url: str
    api_key_env: str
    models: ProviderModelConfig


class AgentConfig(TypedDict):
    max_steps: int
    temperature: float


class LocalToolsConfig(TypedDict):
    enabled: bool
    include: list[str]


class MCPToolsConfig(TypedDict):
    enabled: bool
    servers: dict[str, Any]


class ToolsConfig(TypedDict):
    local: LocalToolsConfig
    mcp: MCPToolsConfig


class ArgusConfig(TypedDict):
    default_provider: str
    providers: dict[str, OpenAICompatibleProviderConfig]
    tools: ToolsConfig
    agent: AgentConfig


CONFIG_PATH = Path.home() / ".config" / "argus" / "config.json"

DEFAULT_CONFIG: ArgusConfig = {
    "default_provider": "deepseek",
    "providers": {
        "deepseek": {
            "type": "openai-compatible",
            "base_url": "https://api.deepseek.com/v1",
            "api_key_env": "DEEPSEEK_API_KEY",
            "models": {
                "default": "deepseek-v4-pro",
            },
        }
    },
    "tools": {
        "local": {
            "enabled": True,
            "include": [
                "dns_a_lookup",
                "registration_lookup",
            ],
        },
        "mcp": {
            "enabled": False,
            "servers": {},
        },
    },
    "agent": {
        "max_steps": 8,
        "temperature": 0.2,
    },
}


def config_path() -> Path:
    return CONFIG_PATH


def default_config() -> ArgusConfig:
    return json.loads(json.dumps(DEFAULT_CONFIG))


def ensure_config_file() -> Path:
    path = config_path()
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(DEFAULT_CONFIG, indent=2) + "\n", encoding="utf-8")
    return path


def load_config() -> ArgusConfig:
    path = ensure_config_file()
    raw = json.loads(path.read_text(encoding="utf-8"))
    merged = _deep_merge(DEFAULT_CONFIG, raw)
    return _validate_config(merged)


def _deep_merge(default: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(default)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _validate_config(raw: Any) -> ArgusConfig:
    if not isinstance(raw, dict):
        raise TypeError("Argus config must be a JSON object.")

    default_provider = raw.get("default_provider")
    providers = raw.get("providers")
    tools = raw.get("tools")
    agent = raw.get("agent")

    if not isinstance(default_provider, str):
        raise TypeError("Argus config requires a string default_provider.")
    if not isinstance(providers, dict):
        raise TypeError("Argus config requires a providers object.")
    if not isinstance(tools, dict):
        raise TypeError("Argus config requires a tools object.")
    if not isinstance(agent, dict):
        raise TypeError("Argus config requires an agent object.")

    validated_providers: dict[str, OpenAICompatibleProviderConfig] = {}
    for name, provider in providers.items():
        if not isinstance(name, str) or not isinstance(provider, dict):
            raise TypeError("Provider entries must be objects keyed by string names.")
        validated_providers[name] = _validate_provider(name, provider)

    if default_provider not in validated_providers:
        raise ValueError(f"Default provider '{default_provider}' is not defined.")

    validated_tools = _validate_tools(tools)

    max_steps = agent.get("max_steps")
    temperature = agent.get("temperature")
    if not isinstance(max_steps, int):
        raise TypeError("Argus config requires agent.max_steps to be an integer.")
    if not isinstance(temperature, (int, float)):
        raise TypeError("Argus config requires agent.temperature to be a number.")

    return {
        "default_provider": default_provider,
        "providers": validated_providers,
        "tools": validated_tools,
        "agent": {
            "max_steps": max_steps,
            "temperature": float(temperature),
        },
    }


def _validate_tools(raw: dict[str, Any]) -> ToolsConfig:
    local = raw.get("local")
    mcp = raw.get("mcp")
    if not isinstance(local, dict):
        raise TypeError("Argus config requires tools.local to be an object.")
    if not isinstance(mcp, dict):
        raise TypeError("Argus config requires tools.mcp to be an object.")

    local_enabled = local.get("enabled")
    include = local.get("include")
    if not isinstance(local_enabled, bool):
        raise TypeError("Argus config requires tools.local.enabled to be a boolean.")
    if not isinstance(include, list) or any(not isinstance(item, str) for item in include):
        raise TypeError("Argus config requires tools.local.include to be a list of strings.")

    mcp_enabled = mcp.get("enabled")
    servers = mcp.get("servers")
    if not isinstance(mcp_enabled, bool):
        raise TypeError("Argus config requires tools.mcp.enabled to be a boolean.")
    if not isinstance(servers, dict):
        raise TypeError("Argus config requires tools.mcp.servers to be an object.")

    return {
        "local": {
            "enabled": local_enabled,
            "include": include,
        },
        "mcp": {
            "enabled": mcp_enabled,
            "servers": servers,
        },
    }


def _validate_provider(name: str, raw: dict[str, Any]) -> OpenAICompatibleProviderConfig:
    provider_type = raw.get("type")
    if provider_type != "openai-compatible":
        raise ValueError(f"Provider '{name}' must use type 'openai-compatible'.")

    base_url = raw.get("base_url")
    api_key_env = raw.get("api_key_env")
    models = raw.get("models")

    if not isinstance(base_url, str):
        raise TypeError(f"Provider '{name}' requires a string base_url.")
    if not isinstance(api_key_env, str):
        raise TypeError(f"Provider '{name}' requires a string api_key_env.")
    if not isinstance(models, dict):
        raise TypeError(f"Provider '{name}' requires a models object.")

    default_model = models.get("default")
    if not isinstance(default_model, str):
        raise TypeError(f"Provider '{name}' requires models.default to be a string.")

    if api_key_env.startswith("{env:") and api_key_env.endswith("}"):
        api_key_env = api_key_env.removeprefix("{env:").removesuffix("}")

    return {
        "type": "openai-compatible",
        "base_url": base_url,
        "api_key_env": api_key_env,
        "models": {
            "default": default_model,
        },
    }


def resolve_provider(config: ArgusConfig) -> tuple[str, OpenAICompatibleProviderConfig]:
    name = config["default_provider"]
    return name, config["providers"][name]


def resolve_api_key(provider: OpenAICompatibleProviderConfig) -> str:
    api_key = os.getenv(provider["api_key_env"])
    if not api_key:
        raise RuntimeError(f"{provider['api_key_env']} is required for the configured provider.")
    return api_key
