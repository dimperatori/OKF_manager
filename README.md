# OKF Manager

`okf-manager` is a domain-agnostic, general-purpose local command-line tool (CLI) written in Python to automate the creation, cross-linking, and lifecycle management of an **Open Knowledge Format (OKF) v0.1** bundle.

## Features
- **Initialize Bundle**: Setup a conformant OKF root layout containing `/index.md` (declaring `okf_version: "0.1"`) and `/log.md`.
- **Create Concepts**: Generate markdown files with valid UTF-8 and perfectly formatted YAML frontmatter blocks containing key metadata (type, title, description, timestamp, tags).
- **Index Generation**: Scan the bundle to recursively build subdirectory index files. It groups files by type and implements progressive disclosure of description tags while preserving human-written text blocks.
- **Semantic Linking**: Append bundle-relative hyperlinks to the bottom of files to form a connected knowledge graph.
- **Audit & Validation**: Validate the conformance of all files inside the bundle (checks root structure, frontmatter format, missing keys, and broken links).
- **Blueprint Scaffolding**: Dynamically initialize folders and concept files from a simple configuration YAML file.

---

## Installation & Requirements

The only dependency is `pyyaml`.

```bash
pip install pyyaml
```

Make the script executable:

```bash
chmod +x manager.py
```

---

## Command Reference

### 1. Initialize a Bundle
Create a new conformant OKF bundle in a specified folder (defaults to current directory).
```bash
./manager.py init [directory]
```
This automatically sets up `index.md` and `log.md` in that directory.

### 2. Create a Concept
Generate a new concept file in a subfolder with structured YAML frontmatter.
```bash
./manager.py create --dir <subfolder> --name <filename> --type <concept_type> --title "<Title>" --desc "<Description>"
```
Example:
```bash
./manager.py create --dir physics --name quantum.md --type concept --title "Quantum Mechanics" --desc "An introduction to quantum physics."
```

### 3. Generate and Update Indexes
Traverses the tree to automatically update or create `index.md` in every directory containing concepts. It preserves any human edits placed outside the `<!-- OKF-INDEX-START -->` and `<!-- OKF-INDEX-END -->` markers.
```bash
./manager.py index
```

### 4. Create a Semantic Cross-Link
Appends a bundle-relative markdown hyperlink to the bottom of the source file pointing to the target file.
```bash
./manager.py link --from <source_path> --to <target_path>
```
Example:
```bash
./manager.py link --from physics/quantum.md --to methods/scientific_method.md
```

### 5. Append Operation Logs
Append an entry to the root `/log.md` file tracking modifications under a `## YYYY-MM-DD` date heading.
```bash
./manager.py log --msg "<action_description>"
```

### 6. Audit & Validation
Check if files are conforming to OKF v0.1 standards and detect broken internal links.
```bash
./manager.py validate
```

### 7. Scaffolding
Bulk-create folder structures and blank concept files using a blueprint file.
```bash
./manager.py scaffold --config blueprint.yaml
```

#### Blueprint YAML Schema:
```yaml
directories:
  - path: "concepts"
    files:
      - name: "quantum_physics.md"
        type: "physics"
        title: "Quantum Physics"
        description: "An introduction to quantum mechanics."
      - name: "general_relativity.md"
        type: "physics"
        title: "General Relativity"
        description: "Einstein's theory of gravitation."
  - path: "methods"
    files:
      - name: "scientific_method.md"
        type: "methodology"
        title: "Scientific Method"
        description: "Systematic observation, measurement, and experiment."
```

## Django Web Interface Integration

A complete Django web control center has been integrated into the OKF bundle, allowing you to manage, ingest, validate, and visualize your knowledge graph directly in a web dashboard.

### Setup and Execution

1. **Install Django**:
   Ensure you have Django installed:
   ```bash
   pip install django
   ```
2. **Apply Migrations**:
   Run the database setup for session and auth layers:
   ```bash
   python3 manage.py migrate
   ```
3. **Start the Web Server**:
   Launch Django's local development server:
   ```bash
   python3 manage.py runserver
   ```
4. **Open in Browser**:
   Navigate to [http://127.0.0.1:8000/](http://127.0.0.1:8000/) in your web browser.

### Web Interface Features
- **Dashboard**: High-level counters, type distributions, and recent modifications parsed from `log.md`.
- **Browse Concepts**: Search, filter, and read markdown concept bodies with automatic backlinks (inward links) and outward reference listings.
- **Dynamic Ingestion**: Submit raw text snippets or URLs to call Gemini LLM and parse atomic concepts.
- **Link Builder**: Select source and target concepts from dropdown selectors and establish single or bidirectional semantic connections.
- **Network Visualizer**: An embedded interactive D3.js force-directed graph displaying nodes, categories, hover highlights, search, filtering, and side panel detail drawers.
- **Audit Conformance**: A graphical audit reporter outlining errors and warnings.
