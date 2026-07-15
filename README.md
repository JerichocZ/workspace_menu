# Workspace Menu

Config-driven launcher for project/workspace menus.

This replaces the older per-project Bash scripts where every option had to be
edited inside Bash arrays and `case` blocks. New projects and commands now live
in `workspace_menu.toml`; the runner code should rarely need changes.

## Files

- `workspace_menu.sh`: Bash wrapper. Run this from the terminal or desktop launchers.
- `workspace_menu.py`: Menu runner and TOML validator.
- `workspace_menu.toml`: Editable project, command, alias, and check config.
- `*.sh`: Legacy launchers kept for reference and gradual migration.

## Requirements

- Bash.
- Python 3.11 or newer. The script uses Python's built-in TOML parser.
- The external commands you configure, such as `code`, `drawio`, `okular`,
  `docker`, or `systemctl`.

## Usage

Interactive mode:

```bash
./workspace_menu.sh
```

From the project prompt, you can also launch commands directly:

```text
Use which project? typst model
Use which project? alqueria db superset
```

List configured projects and commands:

```bash
./workspace_menu.sh --list
```

Validate the TOML config:

```bash
./workspace_menu.sh --validate
```

Open a project menu directly:

```bash
./workspace_menu.sh alqueria
./workspace_menu.sh maleta
```

Run project commands directly:

```bash
./workspace_menu.sh alqueria db superset
./workspace_menu.sh iberplast offer ofk
./workspace_menu.sh base python
```

Open every command in a project:

```bash
./workspace_menu.sh alqueria all
```

Quit without opening anything:

```bash
./workspace_menu.sh alqueria q
```

The menu accepts abbreviations. For example, `alq db sup` can resolve to the
Alqueria project and its `db` and `superset` commands, as long as the abbreviation
is not ambiguous.

## Config Format

All editable menu data is in `workspace_menu.toml`.

Top-level defaults:

```toml
title = "Workspace Menu"

[defaults]
detach = true
sleep_seconds = 0.1
prompt = "Open which windows?"
```

- `detach = true` is best for GUI apps. The launcher starts the app and returns.
- `detach = false` is best for terminal commands where you want to see output.
- `sleep_seconds` adds a small delay after detached commands.
- `prompt` is the default text used when asking which commands to run.

## Add a Project

Add a new `[projects.project_key]` table:

```toml
[projects.my_project]
label = "My Project"
aliases = ["mine", "project"]
examples = "root app, all, q"
```

Fields:

- `project_key`: Stable ID used by the launcher. Use simple names like
  `my_project`, `maleta_1`, or `alqueria_tanqueros`.
- `label`: Human-readable name shown in the menu.
- `aliases`: Extra names or shortcuts accepted by the resolver.
- `examples`: Help text shown under the command menu.
- `checks`: Optional list of preflight checks to run before project commands.

## Add a Command

Under the project, add a `[[projects.project_key.commands]]` block:

```toml
[[projects.my_project.commands]]
key = "root"
label = "VS Code: root folder"
aliases = ["root", "rt"]
argv = ["code", "/home/iotlaptop/Documents/projects/my_project"]
```

Fields:

- `key`: Stable command ID shown in brackets.
- `label`: Human-readable command label.
- `aliases`: Extra names or shortcuts accepted by the resolver.
- `argv`: Preferred command format. Each item is one command argument.
- `shell`: Alternative command format when shell features are needed.
- `cwd`: Optional working directory for the command.
- `detach`: Optional override for this command.
- `sleep_seconds`: Optional delay override for this command.
- `checks`: Optional list of checks to run before this command.

Prefer `argv` for simple commands:

```toml
argv = ["code", "/path/to/folder"]
```

Use `shell` only when you need shell behavior such as `&&`, pipes, redirects,
environment assignments, or command expansion:

```toml
[[projects.my_project.commands]]
key = "up"
label = "Docker compose up"
aliases = ["up", "docker"]
cwd = "/home/iotlaptop/Documents/projects/my_project"
shell = "docker compose up -d"
detach = false
```

## Remove a Project or Command

To remove a command, delete its whole command block:

```toml
[[projects.my_project.commands]]
key = "old-command"
label = "Old command"
aliases = ["old"]
argv = ["code", "/old/path"]
```

To remove a project, delete the project table and all of its command blocks:

```toml
[projects.my_project]
label = "My Project"
aliases = ["mine"]

[[projects.my_project.commands]]
key = "root"
label = "VS Code: root folder"
aliases = ["root"]
argv = ["code", "/path/to/project"]
```

After editing, run:

```bash
./workspace_menu.sh --validate
```

## Checks

Checks are reusable preflight tasks. The current config defines one check that
starts and waits for the Sensomatic rclone mount:

```toml
[checks.sensomatic_drive]
type = "systemd_user_mount"
service = "rclone_drive_sensomatic_drive.service"
dir = "/home/iotlaptop/Documents/sensomatic_drive"
timeout_seconds = 60
poll_seconds = 2
```

Attach a check to a whole project:

```toml
[projects.alqueria_tanqueros]
label = "Alqueria Tanqueros"
checks = ["sensomatic_drive"]
```

Or attach it to only one command:

```toml
[[projects.iberplast_vibration.commands]]
key = "diagrams"
label = "Drawio: diagrams"
checks = ["sensomatic_drive"]
argv = ["drawio", "/path/to/diagrams.drawio"]
```

Each selected check runs only once per launcher execution.

## Resolver Rules

When you type a token, the launcher tries to resolve it in this order:

1. Exact key match.
2. Exact alias match.
3. Unique key or alias prefix.

If more than one project or command matches, the launcher prints an ambiguous
option error and asks again.

Examples:

```bash
./workspace_menu.sh alq db
./workspace_menu.sh mal model
./workspace_menu.sh iber ofk
```

## Desktop Launchers
This app comes with a default desktop entry that can be easily installed using:

```sh
bash desktop/install_desktop.sh
```

Once it is ran, this folder directory is called from the desktop entry. So, directory should not be moved.

### Custom

Desktop entries can call this wrapper directly. For example:

```desktop
Exec=/home/iotlaptop/Documents/workspaces/workspace_menu.sh iberplast
```

Or open a fixed set of commands:

```desktop
Exec=/home/iotlaptop/Documents/workspaces/workspace_menu.sh iberplast offer ofk
```

## Good Editing Habits

- Keep keys short and stable.
- Put user-facing text in `label`.
- Add a few aliases for the words you naturally type.
- Prefer `argv` for GUI apps and simple commands.
- Use `shell` only when command-line shell features are required.
- Run `./workspace_menu.sh --validate` after every config edit.
