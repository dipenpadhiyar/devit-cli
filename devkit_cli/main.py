# -*- coding: utf-8 -*-
"""Main CLI entry point for devkit-cli."""

import difflib
import sys

import click
from rich.console import Console
from rich import print as rprint
from devkit_cli import __version__

from devkit_cli.commands.init import init
from devkit_cli.commands.clean import clean
from devkit_cli.commands.info import info
from devkit_cli.commands.find import find
from devkit_cli.commands.archive import zip_cmd, unzip_cmd
from devkit_cli.commands.env import env
from devkit_cli.commands.run import run, build, dev, test
from devkit_cli.commands.deps import deps

console = Console()


class _DevkitGroup(click.Group):
    """Click Group subclass that suggests corrections for mistyped commands."""

    def resolve_command(self, ctx: click.Context, args: list):
        try:
            return super().resolve_command(ctx, args)
        except click.UsageError:
            cmd_name = args[0] if args else ""
            all_cmds = self.list_commands(ctx)
            suggestions = difflib.get_close_matches(cmd_name, all_cmds, n=1, cutoff=0.6)
            if suggestions:
                console.print(
                    f"[red]Error:[/red] No such command [bold]'{cmd_name}'[/bold].\n"
                    f"       Did you mean [bold green]{suggestions[0]}[/bold green]?\n\n"
                    f"Run [bold]devit --help[/bold] to see all available commands."
                )
            else:
                console.print(
                    f"[red]Error:[/red] No such command [bold]'{cmd_name}'[/bold].\n\n"
                    f"Run [bold]devit --help[/bold] to see all available commands."
                )
            sys.exit(2)

LOGO = """
[bold cyan]
  ██████╗ ███████╗██╗   ██╗██╗████████╗
  ██╔══██╗██╔════╝██║   ██║██║╚══██╔══╝
  ██║  ██║█████╗  ██║   ██║██║   ██║   
  ██║  ██║██╔══╝  ╚██╗ ██╔╝██║   ██║   
  ██████╔╝███████╗ ╚████╔╝ ██║   ██║   
  ╚═════╝ ╚══════╝  ╚═══╝  ╚═╝   ╚═╝   
[/bold cyan]
[dim]  Professional Developer CLI Toolkit  v{version}[/dim]
"""


@click.group(cls=_DevkitGroup, invoke_without_command=True, context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, "-v", "--version", message="devit %(version)s")
@click.pass_context
def cli(ctx: click.Context) -> None:
    """
    \b
    devit — A full-featured CLI framework for professional developers.

    Run `devit COMMAND --help` for details on any command.
    """
    if ctx.invoked_subcommand is None:
        console.print(LOGO.format(version=__version__))
        click.echo(ctx.get_help())


# Register all commands
cli.add_command(init)
cli.add_command(clean)
cli.add_command(info)
cli.add_command(find)
cli.add_command(zip_cmd, name="zip")
cli.add_command(unzip_cmd, name="unzip")
cli.add_command(env)
cli.add_command(run)
cli.add_command(build)
cli.add_command(dev)
cli.add_command(test)
cli.add_command(deps)


if __name__ == "__main__":
    cli()
