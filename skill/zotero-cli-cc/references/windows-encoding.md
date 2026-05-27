# Windows CJK Encoding Fix

## Problem

`zot` is a Python/Click application. On Windows with CJK system locale (Chinese, Japanese, Korean), stdout defaults to GBK/CP936 encoding. This causes two failures:

### Failure 1: zot crashes on output

`click.echo()` encodes output as GBK. Unicode characters outside GBK range (e.g. emoji `⛔` U+26D4) cause:

```
UnicodeEncodeError: 'gbk' codec can't encode character '\u26d4' in position 1061
```

The JSON output never reaches stdout — subprocess gets an empty result or a traceback.

### Failure 2: subprocess decode error

Even when zot outputs GBK bytes successfully, Python's `subprocess` defaults to UTF-8 decoding:

```
UnicodeDecodeError: 'utf-8' codec can't decode byte 0xd6
```

## Solution (v0.6+)

Starting from v0.6, `zot` auto-reconfigures stdout/stderr to UTF-8 on Windows when the system encoding is not UTF-8. No user action required.

## Solution (pre-v0.6 or subprocess calls)

Set `PYTHONIOENCODING=utf-8` in the environment before invoking `zot`. This forces Python's stdin/stdout/stderr to use UTF-8, fixing both failures simultaneously.

### Python subprocess

```python
import subprocess, os

env = os.environ.copy()
env['PYTHONIOENCODING'] = 'utf-8'

result = subprocess.run(
    ['zot', '--json', 'search', 'query'],
    capture_output=True,
    env=env,
)

text = result.stdout.decode('utf-8')
```

### PowerShell

```powershell
$env:PYTHONIOENCODING = "utf-8"
zot --json search "transformer"
```

### CMD

```cmd
set PYTHONIOENCODING=utf-8
zot --json search "transformer"
```

### Persistent (recommended)

Set as a user environment variable so all new terminals inherit it:

```powershell
[Environment]::SetEnvironmentVariable("PYTHONIOENCODING", "utf-8", "User")
```

## Why Not Other Approaches

| Approach | Problem |
|----------|---------|
| `chcp 65001` | Only changes console code page, not Python's `sys.stdout.encoding` |
| PowerShell `Out-File -Encoding utf8` | PowerShell decodes zot's GBK output first, corrupting CJK characters |
| `result.stdout.decode('gbk')` | Only fixes Failure 2; Failure 1 (zot crash) still produces no output |

## Fallback Decoding

If `PYTHONIOENCODING` is not set and you are on a pre-v0.6 version, use multi-stage decoding:

```python
raw = result.stdout
try:
    text = raw.decode('utf-8')
except UnicodeDecodeError:
    text = raw.decode('gbk', errors='replace')
```
