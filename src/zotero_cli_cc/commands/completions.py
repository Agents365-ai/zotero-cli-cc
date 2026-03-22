from __future__ import annotations

import click


SHELLS = {
    "bash": {
        "var": "_ZOT_COMPLETE=bash_source",
        "script": 'eval "$(_ZOT_COMPLETE=bash_source zot)"',
        "file": "~/.bashrc",
    },
    "zsh": {
        "var": "_ZOT_COMPLETE=zsh_source",
        "script": 'eval "$(_ZOT_COMPLETE=zsh_source zot)"',
        "file": "~/.zshrc",
    },
    "fish": {
        "var": "_ZOT_COMPLETE=fish_source",
        "script": "_ZOT_COMPLETE=fish_source zot | source",
        "file": "~/.config/fish/completions/zot.fish",
    },
}


@click.command("completions")
@click.argument("shell", type=click.Choice(["bash", "zsh", "fish"]))
def completions_cmd(shell: str) -> None:
    """Generate shell completion script.

    Add the output to your shell profile to enable tab completions.

    \b
    Examples:
      zot completions bash >> ~/.bashrc
      zot completions zsh >> ~/.zshrc
      zot completions fish > ~/.config/fish/completions/zot.fish
    """
    import subprocess
    import os

    env = os.environ.copy()
    env[SHELLS[shell]["var"].split("=")[0]] = SHELLS[shell]["var"].split("=")[1]
    result = subprocess.run(
        ["zot"], env=env, capture_output=True, text=True,
    )
    if result.stdout:
        click.echo(result.stdout)
    else:
        # Fallback: print the eval one-liner
        info = SHELLS[shell]
        click.echo(f"# Add this to {info['file']}:")
        click.echo(info["script"])
