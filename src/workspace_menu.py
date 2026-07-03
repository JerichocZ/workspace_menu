#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


CONFIG_NAME = "workspace_menu.toml"


@dataclass(frozen=True)
class Check:
    key: str
    type: str
    data: dict[str, Any]


@dataclass(frozen=True)
class Command:
    key: str
    label: str
    aliases: tuple[str, ...]
    argv: tuple[str, ...] | None
    shell: str | None
    cwd: str | None
    detach: bool
    sleep_seconds: float
    checks: tuple[str, ...]


@dataclass(frozen=True)
class Project:
    key: str
    label: str
    aliases: tuple[str, ...]
    prompt: str
    examples: str
    checks: tuple[str, ...]
    commands: tuple[Command, ...]


@dataclass(frozen=True)
class MenuConfig:
    title: str
    checks: dict[str, Check]
    projects: tuple[Project, ...]


class ConfigError(ValueError):
    pass


class ResolveError(ValueError):
    pass


def normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def expand(value: str) -> str:
    return os.path.expandvars(os.path.expanduser(value))


def require_string(table: dict[str, Any], field: str, context: str) -> str:
    value = table.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{context}: expected non-empty string field '{field}'")
    return value


def optional_string(table: dict[str, Any], field: str, context: str) -> str | None:
    value = table.get(field)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ConfigError(f"{context}: expected string field '{field}'")
    return value


def string_list(table: dict[str, Any], field: str, context: str) -> tuple[str, ...]:
    value = table.get(field, [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ConfigError(f"{context}: expected '{field}' to be a list of strings")
    return tuple(value)


def parse_config(config_path: Path) -> MenuConfig:
    try:
        with config_path.open("rb") as config_file:
            raw = tomllib.load(config_file)
    except FileNotFoundError as exc:
        raise ConfigError(f"Config file not found: {config_path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Invalid TOML in {config_path}: {exc}") from exc

    defaults = raw.get("defaults", {})
    if defaults is None:
        defaults = {}
    if not isinstance(defaults, dict):
        raise ConfigError("defaults: expected a table")

    default_detach = defaults.get("detach", True)
    default_sleep = defaults.get("sleep_seconds", 0.1)
    default_prompt = defaults.get("prompt", "Open which windows?")

    if not isinstance(default_detach, bool):
        raise ConfigError("defaults.detach: expected boolean")
    if not isinstance(default_sleep, (int, float)):
        raise ConfigError("defaults.sleep_seconds: expected number")
    if not isinstance(default_prompt, str):
        raise ConfigError("defaults.prompt: expected string")

    checks: dict[str, Check] = {}
    raw_checks = raw.get("checks", {})
    if not isinstance(raw_checks, dict):
        raise ConfigError("checks: expected a table")
    for check_key, check_table in raw_checks.items():
        if not isinstance(check_table, dict):
            raise ConfigError(f"checks.{check_key}: expected a table")
        check_type = require_string(check_table, "type", f"checks.{check_key}")
        checks[check_key] = Check(check_key, check_type, check_table)

    raw_projects = raw.get("projects")
    if not isinstance(raw_projects, dict) or not raw_projects:
        raise ConfigError("projects: expected at least one project table")

    projects: list[Project] = []
    for project_key, project_table in raw_projects.items():
        project_context = f"projects.{project_key}"
        if not isinstance(project_table, dict):
            raise ConfigError(f"{project_context}: expected a table")
        label = require_string(project_table, "label", project_context)
        aliases = string_list(project_table, "aliases", project_context)
        project_checks = string_list(project_table, "checks", project_context)
        prompt = optional_string(project_table, "prompt", project_context) or default_prompt
        examples = optional_string(project_table, "examples", project_context) or "db sup, draw, all, q"

        raw_commands = project_table.get("commands")
        if not isinstance(raw_commands, list) or not raw_commands:
            raise ConfigError(f"{project_context}.commands: expected at least one command")

        commands: list[Command] = []
        command_keys: set[str] = set()
        for index, command_table in enumerate(raw_commands, start=1):
            command_context = f"{project_context}.commands[{index}]"
            if not isinstance(command_table, dict):
                raise ConfigError(f"{command_context}: expected a table")
            key = require_string(command_table, "key", command_context)
            if key in command_keys:
                raise ConfigError(f"{command_context}: duplicate command key '{key}'")
            command_keys.add(key)

            command_label = require_string(command_table, "label", command_context)
            command_aliases = string_list(command_table, "aliases", command_context)
            command_checks = string_list(command_table, "checks", command_context)
            argv_value = command_table.get("argv")
            shell_value = command_table.get("shell")
            if argv_value is not None and shell_value is not None:
                raise ConfigError(f"{command_context}: use either 'argv' or 'shell', not both")
            if argv_value is None and shell_value is None:
                raise ConfigError(f"{command_context}: expected either 'argv' or 'shell'")
            if argv_value is not None:
                if not isinstance(argv_value, list) or not argv_value or not all(isinstance(item, str) for item in argv_value):
                    raise ConfigError(f"{command_context}.argv: expected a non-empty list of strings")
                argv = tuple(argv_value)
                shell = None
            else:
                argv = None
                if not isinstance(shell_value, str) or not shell_value.strip():
                    raise ConfigError(f"{command_context}.shell: expected a non-empty string")
                shell = shell_value

            detach = command_table.get("detach", default_detach)
            sleep_seconds = command_table.get("sleep_seconds", default_sleep)
            cwd = optional_string(command_table, "cwd", command_context)
            if not isinstance(detach, bool):
                raise ConfigError(f"{command_context}.detach: expected boolean")
            if not isinstance(sleep_seconds, (int, float)):
                raise ConfigError(f"{command_context}.sleep_seconds: expected number")

            commands.append(
                Command(
                    key=key,
                    label=command_label,
                    aliases=command_aliases,
                    argv=argv,
                    shell=shell,
                    cwd=cwd,
                    detach=detach,
                    sleep_seconds=float(sleep_seconds),
                    checks=command_checks,
                )
            )

        projects.append(
            Project(
                key=project_key,
                label=label,
                aliases=aliases,
                prompt=prompt,
                examples=examples,
                checks=project_checks,
                commands=tuple(commands),
            )
        )

    referenced_checks: set[str] = set()
    for project in projects:
        referenced_checks.update(project.checks)
        for command in project.commands:
            referenced_checks.update(command.checks)
    missing_checks = sorted(check_key for check_key in referenced_checks if check_key not in checks)
    if missing_checks:
        raise ConfigError(f"Unknown checks referenced by projects/commands: {', '.join(missing_checks)}")

    title = raw.get("title", "Workspace Menu")
    if not isinstance(title, str):
        raise ConfigError("title: expected string")

    return MenuConfig(title=title, checks=checks, projects=tuple(projects))


def resolve_token(token: str, items: list[tuple[str, str, tuple[str, ...]]], item_name: str) -> str:
    normalized_token = normalize(token)
    if not normalized_token:
        raise ResolveError(f"Empty {item_name} token")

    for key, _label, _aliases in items:
        if normalize(key) == normalized_token:
            return key

    exact_alias_matches: list[str] = []
    prefix_matches: list[str] = []
    seen_exact: set[str] = set()
    seen_prefix: set[str] = set()

    for key, _label, aliases in items:
        normalized_key = normalize(key)
        if normalized_key.startswith(normalized_token):
            prefix_matches.append(key)
            seen_prefix.add(key)
            continue

        for alias in aliases:
            normalized_alias = normalize(alias)
            if not normalized_alias:
                continue
            if normalized_alias == normalized_token:
                if key not in seen_exact:
                    exact_alias_matches.append(key)
                    seen_exact.add(key)
                break
            if normalized_alias.startswith(normalized_token):
                if key not in seen_prefix:
                    prefix_matches.append(key)
                    seen_prefix.add(key)
                break

    if len(exact_alias_matches) == 1:
        return exact_alias_matches[0]
    if len(exact_alias_matches) > 1:
        raise ResolveError(f"Ambiguous {item_name} '{token}': {' '.join(exact_alias_matches)}")
    if len(prefix_matches) == 1:
        return prefix_matches[0]
    if len(prefix_matches) > 1:
        raise ResolveError(f"Ambiguous {item_name} '{token}': {' '.join(prefix_matches)}")

    raise ResolveError(f"Unknown {item_name} '{token}'")


def print_projects(config: MenuConfig) -> None:
    print()
    print(config.title)
    print()
    print("Available projects:")
    for project in config.projects:
        print(f"  [{project.key:<24}] {project.label}")
    print()
    print("Type a project key or abbreviation. Use q to quit.")


def print_commands(project: Project) -> None:
    print()
    print(f"Project: {project.label}")
    print()
    print("Available commands:")
    for command in project.commands:
        print(f"  [{command.key:<15}] {command.label}")
    print()
    print(f"Type one or more commands using abbreviations. Examples: {project.examples}")


def select_project(config: MenuConfig, token: str | None) -> Project | None:
    project_items = [(project.key, project.label, project.aliases) for project in config.projects]

    if token:
        if normalize(token) in {"q", "quit", "exit"}:
            return None
        resolved_key = resolve_token(token, project_items, "project")
        return next(project for project in config.projects if project.key == resolved_key)

    print_projects(config)
    while True:
        selection = input("Use which project? ").strip()
        if normalize(selection) in {"q", "quit", "exit"}:
            return None
        if not selection:
            print("Please type a project.")
            continue
        try:
            resolved_key = resolve_token(selection, project_items, "project")
        except ResolveError as exc:
            print(exc, file=sys.stderr)
            continue
        return next(project for project in config.projects if project.key == resolved_key)


def split_command_tokens(tokens: list[str]) -> list[str]:
    split_tokens: list[str] = []
    for token in tokens:
        split_tokens.extend(part for part in token.replace(",", " ").split() if part)
    return split_tokens


def select_commands(project: Project, tokens: list[str]) -> list[Command] | None:
    command_items = [(command.key, command.label, command.aliases) for command in project.commands]

    def resolve_many(raw_tokens: list[str]) -> list[Command] | None:
        normalized_line = normalize(" ".join(raw_tokens))
        if normalized_line in {"q", "quit", "exit"}:
            return None
        if normalized_line == "all":
            return list(project.commands)

        selected: list[Command] = []
        seen: set[str] = set()
        for token in split_command_tokens(raw_tokens):
            resolved_key = resolve_token(token, command_items, "command")
            if resolved_key not in seen:
                selected.append(next(command for command in project.commands if command.key == resolved_key))
                seen.add(resolved_key)
        return selected

    if tokens:
        return resolve_many(tokens)

    print_commands(project)
    while True:
        selection = input(f"{project.prompt} ").strip()
        raw_tokens = split_command_tokens([selection])
        normalized_line = normalize(selection)
        if normalized_line in {"q", "quit", "exit"}:
            return None
        if not raw_tokens:
            print("Please type at least one command.")
            continue
        try:
            return resolve_many(raw_tokens)
        except ResolveError as exc:
            print(exc, file=sys.stderr)


def run_systemd_user_mount_check(check: Check) -> None:
    service = require_string(check.data, "service", f"checks.{check.key}")
    mount_dir = require_string(check.data, "dir", f"checks.{check.key}")
    timeout_seconds = check.data.get("timeout_seconds", 60)
    poll_seconds = check.data.get("poll_seconds", 2)
    if not isinstance(timeout_seconds, (int, float)):
        raise ConfigError(f"checks.{check.key}.timeout_seconds: expected number")
    if not isinstance(poll_seconds, (int, float)):
        raise ConfigError(f"checks.{check.key}.poll_seconds: expected number")

    active = subprocess.run(
        ["systemctl", "--user", "is-active", "--quiet", service],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if active.returncode != 0:
        print(f"Starting {service}...")
        subprocess.run(["systemctl", "--user", "start", service], check=True)

    expanded_dir = expand(mount_dir)
    deadline = time.monotonic() + float(timeout_seconds)
    while True:
        try:
            ready = os.path.isdir(expanded_dir) and any(os.scandir(expanded_dir))
        except OSError:
            ready = False

        if ready:
            print(f"OK: {expanded_dir} is non-empty")
            return

        if time.monotonic() >= deadline:
            raise RuntimeError(f"ERROR: {expanded_dir} is still empty after {timeout_seconds}[s].")

        time.sleep(float(poll_seconds))


def run_check(check: Check) -> None:
    if check.type == "systemd_user_mount":
        run_systemd_user_mount_check(check)
        return
    raise ConfigError(f"checks.{check.key}: unsupported check type '{check.type}'")


def command_display(command: Command) -> str:
    if command.argv:
        return " ".join(command.argv)
    return command.shell or ""


def run_command(command: Command) -> None:
    cwd = expand(command.cwd) if command.cwd else None
    common_kwargs: dict[str, Any] = {"cwd": cwd}

    if command.argv:
        executable: str | list[str] = [expand(part) for part in command.argv]
        use_shell = False
    else:
        executable = command.shell or ""
        use_shell = True
        common_kwargs["executable"] = "/bin/bash"

    if command.detach:
        subprocess.Popen(
            executable,
            shell=use_shell,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
            **common_kwargs,
        )
        if command.sleep_seconds > 0:
            time.sleep(command.sleep_seconds)
        return

    subprocess.run(executable, shell=use_shell, check=True, **common_kwargs)


def run_selection(config: MenuConfig, project: Project, commands: list[Command]) -> None:
    completed_checks: set[str] = set()

    def maybe_run_check(check_key: str) -> None:
        if check_key in completed_checks:
            return
        run_check(config.checks[check_key])
        completed_checks.add(check_key)

    for check_key in project.checks:
        maybe_run_check(check_key)

    for command in commands:
        for check_key in command.checks:
            maybe_run_check(check_key)
        print(f"Opening {command.label}...")
        try:
            run_command(command)
        except FileNotFoundError as exc:
            missing = exc.filename or command_display(command)
            raise RuntimeError(f"Command not found while opening '{command.key}': {missing}") from exc


def print_list(config: MenuConfig) -> None:
    print(config.title)
    for project in config.projects:
        aliases = f" aliases: {', '.join(project.aliases)}" if project.aliases else ""
        print(f"\n[{project.key}] {project.label}{aliases}")
        for command in project.commands:
            command_aliases = f" aliases: {', '.join(command.aliases)}" if command.aliases else ""
            print(f"  [{command.key}] {command.label}{command_aliases}")


def default_config_path() -> Path:
    return Path(__file__).resolve().with_name(CONFIG_NAME)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Config-driven workspace launcher.")
    parser.add_argument("tokens", nargs="*", help="Optional PROJECT followed by COMMAND tokens.")
    parser.add_argument("-c", "--config", type=Path, default=default_config_path(), help=f"Config file. Default: {CONFIG_NAME}")
    parser.add_argument("--list", action="store_true", help="List configured projects and commands.")
    parser.add_argument("--validate", action="store_true", help="Validate the config and exit.")
    return parser


def main(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        config = parse_config(args.config)
        if args.validate:
            print(f"OK: {args.config} is valid.")
            return 0
        if args.list:
            print_list(config)
            return 0

        project_token = args.tokens[0] if args.tokens else None
        command_tokens = args.tokens[1:] if args.tokens else []

        project = select_project(config, project_token)
        if project is None:
            print("No windows opened.")
            return 0

        commands = select_commands(project, command_tokens)
        if commands is None:
            print("No windows opened.")
            return 0
        if not commands:
            print("No commands selected.")
            return 0

        run_selection(config, project, commands)
        return 0
    except (ConfigError, ResolveError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(exc, file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
