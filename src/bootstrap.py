import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING

import nonebot
from msgspec import yaml as msgyaml
from nonebot.utils import deep_update, logger_wrapper, resolve_dot_notation
from pydantic import BaseModel

from .logo import print_logo

if TYPE_CHECKING:
    from nonebot.adapters import Adapter

log = logger_wrapper("Bootstrap")


class Config(BaseModel):
    adapters: set[str] = set()
    plugins: set[str] = set()
    plugin_dir: str | None = "src/plugins"


def setup_logger() -> None:
    logging.getLogger("httpx").setLevel(logging.WARNING)
    log_format = (
        "<g>{time:HH:mm:ss}</g> [<lvl>{level}</lvl>] <c><u>{name}</u></c> | {message}"
    )
    nonebot.logger.add(
        "./logs/{time:YYYY-MM-DD}.log",
        rotation="00:00",
        level="DEBUG",
        format=log_format,
    )
    nonebot.logger.add(
        "./logs/color/{time:YYYY-MM-DD}.log",
        rotation="00:00",
        level="DEBUG",
        colorize=True,
        diagnose=True,
        format=log_format,
    )


def _load_yaml(file_path: Path) -> dict[str, object]:
    data: dict[str, object] = msgyaml.decode(file_path.read_bytes()) or {}

    if data.pop("scope_compat", None):
        for key, value in list(data.items()):
            if isinstance(value, dict):
                del data[key]
                for k, v in value.items():
                    data[f"{key}_{k}"] = v

    return data


def load_config() -> dict[str, object]:
    config_dir = Path("config")
    root_config = config_dir / "config.yaml"
    if not root_config.exists():
        return {}

    config = _load_yaml(root_config)

    env = str(config.get("environment", "prod"))
    env_config = config_dir / f"{env}.yaml"
    if not env_config.exists():
        return config

    config = deep_update(config, _load_yaml(env_config))

    env_dir = config_dir / env
    if not env_dir.exists():
        return config

    for p in env_dir.iterdir():
        if p.suffix == ".yaml":
            config = deep_update(config, _load_yaml(p))

    return config


def load_adapters(config: Config) -> None:
    driver = nonebot.get_driver()

    for module_name in config.adapters:
        log("DEBUG", f"Loading adapter: <g>{module_name}</g>")
        start = time.time()

        try:
            adapter: type[Adapter] = resolve_dot_notation(
                obj_str=module_name,
                default_attr="Adapter",
                default_prefix="nonebot.adapters.",
            )
        except (ImportError, AttributeError):
            log("WARNING", f"Failed to resolve adapter: <y>{module_name}</y>")
            continue

        driver.register_adapter(adapter)
        log(
            "SUCCESS",
            f"Adapter <g>{adapter.get_name()}</g> loaded "
            f"in <y>{time.time() - start:.3f}</y>s",
        )


def load_plugins(config: Config) -> None:
    start = time.time()
    nonebot.load_all_plugins(
        module_path=config.plugins,
        plugin_dir=[config.plugin_dir] if config.plugin_dir else [],
    )
    log("SUCCESS", f"Plugins loaded in <y>{time.time() - start:.3f}</y>s")


def init_nonebot() -> object:
    config = load_config()
    config.pop("_env_file", None)
    bootstrap_config = Config.model_validate(config.pop("bootstrap", {}))

    start = time.time()
    setup_logger()
    nonebot.init(_env_file=None, **config)
    print_logo(lambda line: log("SUCCESS", line))
    load_adapters(bootstrap_config)
    load_plugins(bootstrap_config)
    log("SUCCESS", f"NoneBot initialized in <y>{time.time() - start:.3f}</y>s")

    return nonebot.get_app()
