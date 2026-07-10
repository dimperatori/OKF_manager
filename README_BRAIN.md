# OKF Brain Ingestion & Visualizer

`brain.py` is a Python utility to automate the ingestion of raw knowledge sources into an OKF v0.1 bundle using LLM concept extraction, and to render the bundle as an interactive, beautiful D3.js semantic graph.

## Quick Start

### 1. Ingest Raw Content (LLM-driven)

To extract concepts and construct relationships dynamically, provide your `GEMINI_API_KEY` as an environment variable. If the key is not set, the tool runs in a dry-run mock mode to allow offline testing.

```bash
export GEMINI_API_KEY="YOUR_GEMINI_API_KEY"
```

Then, execute concept ingestion from raw text, a local text file, or a public URL:

* **Ingest from raw text**:
  ```bash
  ./brain.py ingest --source "Quantum Mechanics is a fundamental theory in physics that describes the physical properties of nature at the scale of atoms and subatomic particles."
  ```

* **Ingest from a website**:
  ```bash
  ./brain.py ingest --source "https://en.wikipedia.org/wiki/Quantum_mechanics"
  ```

During ingestion, the tool will:
1. Contact the Gemini API using `gemini-2.5-flash`.
2. Map the context against your existing OKF directory contents.
3. Automatically determine atomic concepts, filenames, and subdirectories.
4. Establish cross-links (internal markdown links) between new concepts and existing concepts.
5. Create markdown files under target subdirectories.
6. Automatically run `index` to update all indexes.

---

### 2. Generate Interactive Visualization

Compile all nodes (concepts) and links (cross-links) within the bundle into a single self-contained HTML visualizer.

```bash
./brain.py visualizer
```

This compiles your graph and outputs `visualizer.html` in your bundle root.

---

### 3. Open the Visualizer

Open the generated `visualizer.html` file directly in any modern web browser. **No local server is required.**

```bash
open visualizer.html
```

#### Visualizer Features:
- **Interactive Force Graph**: Click and drag nodes, zoom in/out with the mouse wheel, and pan around the workspace.
- **Glassmorphism Detail Panel**: Click any node to slide in a semi-transparent sidebar displaying the concept's frontmatter tags, badges, and its parsed body content rendered as rich HTML.
- **Hover Highlights**: Mouse over any node to highlight its direct neighbors and fade out the rest of the network.
- **Filter by Type**: Use the checkboxes in the control panel to toggle visibility of different concept types.
- **Search Panel**: Type in the search input to highlight nodes by title, path, or tag in real-time.
