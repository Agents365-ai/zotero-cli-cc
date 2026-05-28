# Workflow Patterns

## Pattern 1: Find and Read a Paper

```bash
# Step 1: Search
zot --json search "single cell RNA sequencing"

# Step 2: Read metadata
zot --json read K853PGUG

# Step 3: PDF — check structure first, extract selectively
zot --json pdf --outline K853PGUG             # Get section headings + secid
zot --json pdf --section 10 K853PGUG          # Extract only the section you need
zot --json pdf K853PGUG                       # Full text (only if short or necessary)
```

**Token budget**: For PDFs >20k chars, always use `--outline` then `--section` instead of pulling full text.

**No PDF attached?** If `zot pdf` reports no attachment, run `zot find-pdf K853PGUG` to have Zotero desktop fetch and attach one (requires the bridge — see `references/commands.md`).

## Pattern 2: Deep Content Search via Workspace RAG

```bash
# Step 1: Create workspace and populate
zot workspace new drug-resistance --description "Cancer drug resistance mechanisms"
zot --json search "drug resistance cancer" --limit 20
zot workspace add drug-resistance KEY1 KEY2 KEY3

# Step 2: Build index
zot workspace index drug-resistance

# Step 3: Query
zot --json workspace query "mechanisms of acquired resistance" --workspace drug-resistance --top-k 5

# Step 4: Drill into specific chunks for more context
zot --json pdf --outline ITEMKEY
zot --json pdf --section SECID ITEMKEY
```

## Pattern 3: Batch Export from Collections

```python
import subprocess, json, os

env = os.environ.copy()
env['PYTHONIOENCODING'] = 'utf-8'  # Required on Windows CJK systems (older versions)

collections = {
    'topic_a': 'COLLKEY1',
    'topic_b': 'COLLKEY2',
}

for name, key in collections.items():
    result = subprocess.run(
        ['zot', '--json', 'collection', 'items', key],
        capture_output=True, env=env,
    )
    if result.returncode != 0:
        print(f'{name}: error - {result.stderr.decode("utf-8", errors="replace")}')
        continue

    data = json.loads(result.stdout.decode('utf-8'))
    with open(f'batch_{name}.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f'{name}: {data["meta"]["count"]} items')
```

## Pattern 4: Library Reorganization

```bash
# Step 1: Export all abstracts
zot --json summarize-all > abstracts.json

# Step 2: Analyze and classify (AI or manual)
# Step 3: Create collections and move items
zot collection create "Category A"
zot collection move ITEMKEY COLLECTIONKEY
```

## Pattern 5: Literature Review Pipeline

```bash
# 1. Import papers from DOI list
zot add --from-file dois.txt

# 2. Organize into workspace
zot workspace new lit-review --description "Systematic review papers"
zot workspace import lit-review --tag "review-candidate"

# 3. Build index for deep search
zot workspace index lit-review

# 4. Query for themes
zot --json workspace query "methodology comparison" --workspace lit-review --top-k 10
```
