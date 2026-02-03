from rich.console import Console

console = Console()


def info(msg: str):
    console.print(msg)


def success(msg: str):
    console.print(f'[green]✓[/green] {msg}')


def warning(msg: str):
    console.print(f'[yellow]![/yellow] {msg}')


def error(msg: str):
    console.print(f'[red]✗[/red] {msg}')


def added(msg: str):
    console.print(f'[green]  + {msg}[/green]')


def removed(msg: str):
    console.print(f'[red]  - {msg}[/red]')


def header(msg: str):
    console.print(f'\n[bold]{msg}[/bold]')
