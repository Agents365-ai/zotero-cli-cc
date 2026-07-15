# Setup

## Data Directory

!!! info "What is the data directory?"
    The **data directory** is the folder containing the `zotero.sqlite` database file — not the Zotero installation directory or PDF sync directory. Find it in **Zotero Settings → Advanced → Data Directory Location**.

Read operations work out of the box. `zot` automatically detects the Zotero data directory:

| Platform | Detection Order |
|----------|----------------|
| **Windows** | Registry `HKCU\Software\Zotero\Zotero\dataDir` → `%APPDATA%\Zotero` → `%LOCALAPPDATA%\Zotero` |
| **macOS / Linux** | `~/Zotero` |

If your data is not in the default location:

=== "Config file (recommended)"

    ```bash
    zot config init --data-dir "D:\MyZotero"
    ```

=== "Environment variable"

    ```bash
    export ZOT_DATA_DIR="/path/to/zotero/data"
    ```

=== "Manual config edit"

    Edit `~/.config/zot/config.toml`:

    ```toml
    [zotero]
    data_dir = "D:\\MyZotero"
    ```

## API Credentials

Write operations (add, delete, update, tag, note, collection management) require a Zotero API key.

1. Go to [https://www.zotero.org/settings/keys](https://www.zotero.org/settings/keys)
2. Create a new key with read/write access to your library
3. Run the setup wizard:

```bash
zot config init
```

This saves your Library ID and API Key to `~/.config/zot/config.toml`.

## Configuration File

Full example:

```toml
[zotero]
data_dir = "D:\\MyZotero"
library_id = "12345"
api_key = "xxx"

[output]
default_format = "table"
limit = 50

[export]
default_style = "bibtex"
```

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `ZOT_DATA_DIR` | Override Zotero data directory path |
| `ZOT_LIBRARY_ID` | Override Library ID (write operations) |
| `ZOT_API_KEY` | Override API Key (write operations) |
| `ZOT_PROFILE` | Override default config profile |
| `S2_API_KEY` | Semantic Scholar API key (for `update-status`) |
| `ZOT_EMBEDDING_URL` | Embedding API endpoint (default: Jina AI) |
| `ZOT_EMBEDDING_KEY` | Embedding API key (enables semantic workspace search) |
| `ZOT_EMBEDDING_MODEL` | Embedding model name (default: `jina-embeddings-v3`) |
| `ZOT_EMBEDDING_PROVIDER` | Embedding provider: `jina` (default), `aliyun`, or `openai` (any OpenAI-compatible `/v1/embeddings` endpoint — set `ZOT_EMBEDDING_URL` to its base URL) |

## Multiple Profiles

```bash
zot config profile list        # List all profiles
zot config profile set lab     # Set default profile
zot --profile lab search "X"   # Use a specific profile
```
