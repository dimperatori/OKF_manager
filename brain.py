#!/usr/bin/env python3
import argparse
import datetime
import json
import os
import re
import sys
import urllib.request
import urllib.error
from pathlib import Path

# Add the workspace directory to path to import manager
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import manager
except ImportError:
    print("Error: Could not import 'manager.py'. Please make sure it is in the same directory.", file=sys.stderr)
    sys.exit(1)


def scan_existing_concepts(bundle_root: Path) -> list:
    """
    Scans the bundle for existing concepts to pass as context to the LLM.
    """
    concepts = []
    for root, dirs, files in os.walk(bundle_root):
        root_path = Path(root)
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        
        for file in files:
            if file.endswith(".md"):
                if file in ("index.md", "log.md", "visualizer.html"):
                    continue
                file_path = root_path / file
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    fm, _ = manager.parse_markdown(content)
                    if fm and "type" in fm:
                        rel_path = file_path.relative_to(bundle_root)
                        concepts.append({
                            "path": f"/{rel_path}",
                            "title": fm.get("title", file_path.stem),
                            "type": fm.get("type"),
                            "description": fm.get("description", "")
                        })
                except Exception:
                    pass
    return concepts


def get_source_content(source_str: str) -> str:
    """
    Retrieves source content from raw text, a local file path, or a URL.
    """
    if source_str.startswith("http://") or source_str.startswith("https://"):
        try:
            print(f"Fetching content from URL: {source_str}")
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            import ssl
            context = ssl._create_unverified_context()
            req = urllib.request.Request(source_str, headers=headers)
            with urllib.request.urlopen(req, context=context) as response:
                html = response.read().decode("utf-8", errors="ignore")
                
                # Simple HTML tag and script removal to feed clean text to LLM
                text = re.sub(r'<script.*?</script>', '', html, flags=re.DOTALL)
                text = re.sub(r'<style.*?</style>', '', text, flags=re.DOTALL)
                text = re.sub(r'<[^>]+>', ' ', text)
                text = re.sub(r'\s+', ' ', text).strip()
                return text
        except Exception as e:
            raise RuntimeError(f"Failed to fetch content from URL: {e}")
            
    # Check if file path
    path = Path(source_str)
    if path.is_file():
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()
        except Exception as e:
            raise RuntimeError(f"Failed to read local file: {e}")
            
    return source_str


def call_gemini_api(api_key: str, prompt: str) -> str:
    """
    Calls the Gemini API (gemini-2.5-flash) using standard libraries.
    Enforces JSON mode.
    """
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    headers = {
        "Content-Type": "application/json"
    }
    data = {
        "contents": [{
            "parts": [{"text": prompt}]
        }],
        "generationConfig": {
            "responseMimeType": "application/json"
        }
    }
    
    req_body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=req_body, headers=headers, method="POST")
    
    try:
        import ssl
        context = ssl._create_unverified_context()
    except Exception:
        context = None

    try:
        with urllib.request.urlopen(req, context=context) as response:
            res_body = response.read().decode("utf-8")
            res_json = json.loads(res_body)
            # Traverse Gemini response path
            text = res_json['candidates'][0]['content']['parts'][0]['text']
            return text
    except urllib.error.HTTPError as e:
        err_content = e.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Gemini API request failed (HTTP {e.code}): {err_content}")
    except Exception as e:
        raise RuntimeError(f"Failed to communicate with Gemini API: {e}")


def get_mock_ingest_response(source_text: str) -> dict:
    """
    Generates mock concepts for testing when no GEMINI_API_KEY is configured.
    """
    print("Generating mock concepts for dry-run/offline testing...")
    # Derive some terms from the text
    words = [w.strip(".,;:?!()\"'") for w in source_text.split() if len(w) > 5]
    keyword = words[0].title() if words else "ConceptoEjemplo"
    keyword_clean = re.sub(r'[^a-zA-Z0-9]', '', keyword)
    
    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    
    mock_data = {
        "concepts": [
            {
                "subfolder": "conceptos",
                "filename": f"{keyword_clean.lower()}_resumen.md",
                "type": "concepto",
                "title": f"Resumen de {keyword}",
                "description": f"Un concepto simulado generado automáticamente a partir de la fuente: {keyword}.",
                "tags": ["simulado", "ingestado", keyword.lower()],
                "body": f"# Resumen de {keyword}\n\nEste es un concepto simulado generado automáticamente porque no se encontró `GEMINI_API_KEY`.\n\n### Fragmento de origen\n> {source_text[:120]}...\n\n### Principios clave\n1. La extracción de conceptos aísla nodos atómicos.\n2. El visualizador mapea conexiones de forma dinámica.",
                "cross_links": []
            }
        ]
    }
    return mock_data


def ingest_content(bundle_root: Path, source_str: str, mode: str = "multiple"):
    """
    Processes source content, calls LLM, saves generated concepts and appends cross-links.
    """
    # 1. Fetch content
    source_content = get_source_content(source_str)
    
    # 2. Gather existing files structure and folders tree
    existing_concepts = scan_existing_concepts(bundle_root)
    existing_subfolders = manager.get_existing_subfolders(bundle_root)
    
    # Load directory descriptions/purposes from config
    config_data = manager.load_config()
    directories_config = config_data.get("directories", {})
    
    dir_descriptions_list = []
    for folder in existing_subfolders:
        desc = directories_config.get(folder, "No se proporcionó explicación sobre su propósito.")
        dir_descriptions_list.append(f"- Carpeta '{folder}': {desc}")
    dir_descriptions_str = "\n".join(dir_descriptions_list)
    
    # 3. Call API or fallback
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Warning: GEMINI_API_KEY environment variable not found.", file=sys.stderr)
        print("To trigger actual LLM concept extraction, please run: export GEMINI_API_KEY='your_key'", file=sys.stderr)
        concepts_data = get_mock_ingest_response(source_content)
    else:
        if mode == "single":
            mode_instruction = (
                "INSTRUCCIÓN DE MODO ÚNICO: Debes extraer EXACTAMENTE UN SOLO concepto exhaustivo que consolide y sintetice la totalidad del material de origen. "
                "La lista de conceptos ('concepts') en tu JSON de salida debe contener EXACTAMENTE UN SOLO objeto de concepto consolidado, en lugar de dividir la información en múltiples notas."
            )
        else:
            mode_instruction = (
                "INSTRUCCIÓN DE MODO MÚLTIPLE: Debes identificar y extraer múltiples conceptos atómicos separados presentes en el material de origen, dividiendo la información de forma lógica en múltiples notas."
            )

        prompt = f"""You are an expert Systems Architect and Knowledge Engineer.
Your task is to analyze the source material and extract core atomic "concepts" to build an Open Knowledge Format (OKF) v0.1 bundle.

CRITICAL INSTRUCTION: All extracted concepts, subfolders, filenames, types, titles, descriptions, tags, cross-link references, and markdown body content MUST be written in Spanish (español), regardless of the language of the source material.
For example:
- Filenames should use Spanish (e.g. `metodo_cientifico.md` or `mecanica_cuantica.md` instead of `scientific_method.md` or `quantum_mechanics.md`).
- Subfolders should be in Spanish (e.g. `conceptos`, `metodos`, `arquitectura` instead of `concepts`, `methods`, `architecture`).
- Titles, types, descriptions, tags, and body text must be entirely in Spanish.

{mode_instruction}

Here is the source material to analyze:
---
{source_content}
---

Here is a list of already existing concepts in the local OKF bundle:
{json.dumps(existing_concepts, indent=2)}

Here is a list of the existing subfolders in the bundle and their specific purposes/explanations:
{dir_descriptions_str}

Please perform the following operations:
1. Identify the core, atomic concepts present in the source material.
2. For each identified concept, determine:
   - A short, clean filename in Spanish (lowercase, e.g. `mecanica_cuantica.md`).
   - A target subfolder. CRITICAL: You MUST choose from one of the following existing subfolders in the bundle: {existing_subfolders}. Analyze the concept content and map it to the subfolder whose purpose/explanation is most relevant to the concept. Do NOT invent or output any other subfolder name. If there are no existing subfolders, use '.' as the subfolder.
   - The concept type in Spanish (e.g. `concepto`, `metodologia`, `formula`, `esquema`).
   - A concise, descriptive title in Spanish.
   - A one-sentence description in Spanish.
   - A list of tags in Spanish.
   - A detailed Markdown body explaining the concept in Spanish. The body must NOT contain the frontmatter, just the content.
   - A list of cross-links to existing concepts that are semantically related. Use the exact paths from the existing concepts list.

Format your output as a single valid JSON object containing a "concepts" key. Do not include markdown code block syntax (like ```json) in your raw response.

JSON Schema:
{{
  "concepts": [
    {{
      "subfolder": "string (MUST be one of the existing subfolders: {existing_subfolders})",
      "filename": "string (ends with .md, in Spanish)",
      "type": "string (concept type, in Spanish)",
      "title": "string (Title, in Spanish)",
      "description": "string (Short description, in Spanish)",
      "tags": ["string"],
      "body": "string (Markdown content body explaining the concept, in Spanish)",
      "cross_links": [
        {{
          "target_path": "string (exact bundle-relative path of existing concept, e.g. /metodos/metodo_cientifico.md)",
          "title": "string (title of target)"
        }}
      ]
    }}
  ]
}}
"""
        try:
            print("Calling Gemini API for concept extraction...")
            response_text = call_gemini_api(api_key, prompt)
            concepts_data = json.loads(response_text)
        except Exception as e:
            print(f"Error calling LLM: {e}", file=sys.stderr)
            print("Falling back to mock ingestion.", file=sys.stderr)
            concepts_data = get_mock_ingest_response(source_content)
            
    # 4. Save concepts to file
    newly_created_files = []
    for concept in concepts_data.get("concepts", []):
        subfolder = concept.get("subfolder", "concepts")
        filename = concept.get("filename")
        if not filename:
            continue
        if not filename.endswith(".md"):
            filename += ".md"
            
        # Adapt to existing subfolders
        subfolder = manager.adapt_subfolder(bundle_root, subfolder)
        target_dir = (bundle_root / subfolder).resolve()
        if not target_dir.is_dir():
            print(f"Warning: Adapted target directory does not exist: {target_dir}. Skipping concept.", file=sys.stderr)
            continue
        
        file_path = target_dir / filename
        if file_path.is_file():
            print(f"File already exists, skipping: {file_path.relative_to(bundle_root)}")
            continue
            
        timestamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        frontmatter = {
            "type": concept.get("type", "concept"),
            "title": concept.get("title", filename.rsplit(".", 1)[0].replace("_", " ").title()),
            "description": concept.get("description", ""),
            "tags": concept.get("tags", []),
            "timestamp": timestamp
        }
        
        body = concept.get("body", "").strip()
        
        # Format and save
        content = manager.format_markdown(frontmatter, body)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
            
        rel_path = file_path.relative_to(bundle_root)
        print(f"Ingested concept: /{rel_path}")
        manager.log_message(bundle_root, f"Ingested concept: /{rel_path} (type: {frontmatter['type']})")
        newly_created_files.append((file_path, concept.get("cross_links", [])))
        
    # 5. Apply cross-links
    for source_file, cross_links in newly_created_files:
        for link in cross_links:
            target_path_str = link.get("target_path")
            if target_path_str:
                try:
                    # Link from new concept to existing
                    manager.link_concepts(bundle_root, f"/{source_file.relative_to(bundle_root)}", target_path_str)
                    # Link back from existing to new (bidirectional graph connection)
                    manager.link_concepts(bundle_root, target_path_str, f"/{source_file.relative_to(bundle_root)}")
                except Exception as e:
                    print(f"Warning: Could not link to {target_path_str}: {e}", file=sys.stderr)
                    
    # 6. Regenerate bundle indexes
    print("Updating indexes...")
    manager.run_indexing(bundle_root)
    print("Ingest cycle completed.")


def generate_visualization(bundle_root: Path):
    """
    Compiles local OKF files and outputs a self-contained visualizer.html.
    """
    graph_data = compile_graph_data(bundle_root)
    
    html_template = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OKF Brain Network Visualizer</title>
    
    <!-- D3.js v7 CDN -->
    <script src="https://d3js.org/d3.v7.min.js"></script>
    <!-- Marked.js CDN (for rendering node bodies as rich Markdown) -->
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    
    <style>
        :root {
            --bg-gradient-start: #0f172a;
            --bg-gradient-end: #1e293b;
            --panel-bg: rgba(30, 41, 59, 0.7);
            --panel-border: rgba(255, 255, 255, 0.08);
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --accent: #38bdf8;
            --accent-hover: #0ea5e9;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background: radial-gradient(circle at center, var(--bg-gradient-end), var(--bg-gradient-start));
            color: var(--text-primary);
            overflow: hidden;
            width: 100vw;
            height: 100vh;
        }

        #canvas-container {
            width: 100%;
            height: 100%;
            position: absolute;
            top: 0;
            left: 0;
            z-index: 1;
        }

        /* Glassmorphism Sidebar */
        .glass-panel {
            background: var(--panel-bg);
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
            border: 1px solid var(--panel-border);
            border-radius: 12px;
            box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
        }

        #sidebar {
            position: absolute;
            top: 20px;
            right: 20px;
            width: 420px;
            height: calc(100% - 40px);
            z-index: 10;
            display: flex;
            flex-direction: column;
            padding: 24px;
            transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            transform: translateX(460px); /* Hidden by default */
        }

        #sidebar.open {
            transform: translateX(0);
        }

        #control-panel {
            position: absolute;
            top: 20px;
            left: 20px;
            width: 320px;
            z-index: 10;
            padding: 20px;
        }

        h1 {
            font-size: 1.25rem;
            font-weight: 700;
            margin-bottom: 8px;
            background: linear-gradient(to right, #38bdf8, #818cf8);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        h2 {
            font-size: 1.1rem;
            font-weight: 600;
            margin-bottom: 12px;
        }

        .subtitle {
            font-size: 0.8rem;
            color: var(--text-secondary);
            margin-bottom: 16px;
        }

        .search-box {
            width: 100%;
            padding: 10px 14px;
            background: rgba(15, 23, 42, 0.6);
            border: 1px solid var(--panel-border);
            border-radius: 8px;
            color: var(--text-primary);
            font-size: 0.9rem;
            outline: none;
            margin-bottom: 16px;
            transition: border-color 0.2s;
        }

        .search-box:focus {
            border-color: var(--accent);
        }

        .filter-section {
            margin-top: 12px;
        }

        .filter-title {
            font-size: 0.85rem;
            font-weight: 600;
            color: var(--text-secondary);
            margin-bottom: 8px;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }

        .checkbox-group {
            display: flex;
            flex-direction: column;
            gap: 8px;
            max-height: 150px;
            overflow-y: auto;
            padding-right: 4px;
        }

        .checkbox-item {
            display: flex;
            align-items: center;
            font-size: 0.85rem;
            cursor: pointer;
            color: var(--text-primary);
        }

        .checkbox-item input {
            margin-right: 8px;
            accent-color: var(--accent);
        }

        .checkbox-color {
            width: 12px;
            height: 12px;
            border-radius: 50%;
            margin-right: 8px;
            display: inline-block;
        }

        /* Detail Sidebar Items */
        #detail-close {
            position: absolute;
            top: 16px;
            right: 16px;
            background: none;
            border: none;
            color: var(--text-secondary);
            font-size: 1.5rem;
            cursor: pointer;
            line-height: 1;
        }

        #detail-close:hover {
            color: var(--text-primary);
        }

        .detail-header {
            border-bottom: 1px solid var(--panel-border);
            padding-bottom: 16px;
            margin-bottom: 16px;
        }

        .badge {
            display: inline-block;
            padding: 4px 10px;
            font-size: 0.75rem;
            font-weight: 600;
            border-radius: 9999px;
            margin-right: 6px;
            margin-bottom: 6px;
            background: rgba(255, 255, 255, 0.1);
        }

        .type-badge {
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }

        #detail-body {
            flex-grow: 1;
            overflow-y: auto;
            padding-right: 8px;
            font-size: 0.95rem;
            line-height: 1.6;
        }

        /* Markdown Rendering Styles */
        #detail-body h1, #detail-body h2, #detail-body h3 {
            margin-top: 16px;
            margin-bottom: 8px;
            font-weight: 600;
            color: var(--text-primary);
        }
        #detail-body h1 { font-size: 1.3rem; }
        #detail-body h2 { font-size: 1.15rem; }
        #detail-body h3 { font-size: 1rem; }
        #detail-body p { margin-bottom: 12px; color: #cbd5e1; }
        #detail-body ul, #detail-body ol { margin-left: 20px; margin-bottom: 12px; }
        #detail-body li { margin-bottom: 4px; }
        #detail-body blockquote {
            border-left: 3px solid var(--accent);
            padding-left: 12px;
            color: var(--text-secondary);
            margin: 12px 0;
            font-style: italic;
        }
        #detail-body code {
            background: rgba(15, 23, 42, 0.6);
            padding: 2px 6px;
            border-radius: 4px;
            font-family: monospace;
            font-size: 0.85rem;
        }

        /* SVG Graph elements */
        .node {
            cursor: pointer;
            stroke-width: 2px;
            transition: stroke-width 0.15s, filter 0.15s;
        }
        
        .node:hover {
            stroke-width: 3px;
            filter: drop-shadow(0 0 8px var(--accent));
        }

        .link {
            stroke-opacity: 0.3;
            stroke-width: 1.5px;
            fill: none;
            transition: stroke-opacity 0.15s, stroke-width 0.15s;
        }

        .link-label {
            font-size: 8px;
            fill: var(--text-secondary);
            pointer-events: none;
            text-anchor: middle;
            display: none; /* Toggle label visibility on hover */
        }

        /* Map Legend */
        .legend-container {
            margin-top: 16px;
            display: flex;
            flex-wrap: wrap;
            gap: 12px;
        }

        .legend-item {
            display: flex;
            align-items: center;
            font-size: 0.75rem;
            color: var(--text-secondary);
        }

        .legend-color {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            margin-right: 6px;
        }

        /* Help Info */
        .help-info {
            font-size: 0.75rem;
            color: var(--text-secondary);
            margin-top: 16px;
            border-top: 1px solid var(--panel-border);
            padding-top: 12px;
        }

        button.reset-btn {
            background: var(--accent);
            color: #0f172a;
            border: none;
            border-radius: 6px;
            padding: 8px 12px;
            font-size: 0.85rem;
            font-weight: 600;
            cursor: pointer;
            width: 100%;
            transition: background 0.2s;
            margin-bottom: 12px;
        }

        button.reset-btn:hover {
            background: var(--accent-hover);
        }

        /* Scrollbar styles */
        ::-webkit-scrollbar {
            width: 6px;
        }
        ::-webkit-scrollbar-track {
            background: transparent;
        }
        ::-webkit-scrollbar-thumb {
            background: rgba(255, 255, 255, 0.1);
            border-radius: 3px;
        }
        ::-webkit-scrollbar-thumb:hover {
            background: rgba(255, 255, 255, 0.2);
        }
    </style>
</head>
<body>

    <div id="canvas-container"></div>

    <!-- Controls Panel -->
    <div id="control-panel" class="glass-panel">
        <h1>OKF Brain</h1>
        <p class="subtitle">Semantic Knowledge Graph Visualizer</p>
        
        <input type="text" id="search-input" class="search-box" placeholder="Search title, tag, or path...">
        
        <button id="reset-view" class="reset-btn">Reset Graph Zoom</button>

        <div class="filter-section">
            <div class="filter-title">Filter by Type</div>
            <div id="filter-checkboxes" class="checkbox-group">
                <!-- Checkboxes generated dynamically -->
            </div>
        </div>

        <div class="help-info">
            <strong>Controls:</strong><br>
            • Drag nodes to reposition them<br>
            • Scroll mouse wheel to Zoom in/out<br>
            • Click nodes to view file description & body
        </div>
    </div>

    <!-- Sidebar Detail Panel -->
    <div id="sidebar" class="glass-panel">
        <button id="detail-close">&times;</button>
        <div class="detail-header">
            <div style="margin-bottom: 8px;">
                <span id="detail-type" class="badge type-badge">Concept</span>
            </div>
            <h2 id="detail-title">Concept Title</h2>
            <div id="detail-path" class="subtitle" style="margin-bottom: 0;">/folder/filename.md</div>
        </div>
        
        <div id="detail-body">
            <p id="detail-desc" style="font-weight: 500; margin-bottom: 16px;"></p>
            <div id="detail-tags" style="margin-bottom: 16px;"></div>
            <div id="detail-markdown"></div>
        </div>
    </div>

    <script>
        // Graph Data injected directly from Python
        const graphData = {DATA_JSON};

        // Standard Premium Palette
        const colors = {
            "concept": "#38bdf8",     // Sky Blue
            "physics": "#f43f5e",     // Rose
            "methodology": "#10b981", // Emerald
            "formula": "#f59e0b",     // Amber
            "schema": "#8b5cf6",      // Purple
            "index": "#ec4899",       // Pink
            "default": "#94a3b8"      // Slate
        };

        const uniqueTypes = [...new Set(graphData.nodes.map(n => n.type))];
        
        // Dynamically append missing type colors
        const typeColorScale = d3.scaleOrdinal(d3.schemeCategory10);
        function getNodeColor(type) {
            return colors[type.toLowerCase()] || typeColorScale(type);
        }

        // Initialize Filter Checkboxes
        const checkboxGroup = d3.select("#filter-checkboxes");
        uniqueTypes.forEach(type => {
            const color = getNodeColor(type);
            const label = checkboxGroup.append("label").attr("class", "checkbox-item");
            
            label.append("input")
                .attr("type", "checkbox")
                .attr("checked", true)
                .attr("value", type)
                .on("change", updateGraphFilters);

            label.append("span")
                .attr("class", "checkbox-color")
                .style("background-color", color);
                
            label.append("span").text(type);
        });

        // Setup Layout Variables
        const container = document.getElementById("canvas-container");
        const width = container.clientWidth;
        const height = container.clientHeight;

        const svg = d3.select("#canvas-container")
            .append("svg")
            .attr("width", "100%")
            .attr("height", "100%")
            .attr("viewBox", [0, 0, width, height]);

        // Define Arrow Markers for Directed Graph Links
        svg.append("defs").append("marker")
            .attr("id", "arrow")
            .attr("viewBox", "0 -5 10 10")
            .attr("refX", 20) // Offsets marker relative to node radius
            .attr("refY", 0)
            .attr("markerWidth", 6)
            .attr("markerHeight", 6)
            .attr("orient", "auto")
            .append("path")
            .attr("fill", "rgba(255,255,255,0.15)")
            .attr("d", "M0,-5L10,0L0,5");

        const g = svg.append("g");

        // Zoom & Pan Configuration
        const zoomBehavior = d3.zoom()
            .scaleExtent([0.15, 4])
            .on("zoom", (event) => {
                g.attr("transform", event.transform);
            });
            
        svg.call(zoomBehavior);

        d3.select("#reset-view").on("click", () => {
            svg.transition().duration(750).call(
                zoomBehavior.transform,
                d3.zoomIdentity.translate(width / 2, height / 2).scale(0.85)
            );
        });

        // Set initial zoom centered
        svg.call(zoomBehavior.transform, d3.zoomIdentity.translate(width / 2, height / 2).scale(0.85));

        // Node & Edge Filtering State
        let activeTypes = new Set(uniqueTypes);
        let searchQuery = "";

        // D3 Force Simulation
        const simulation = d3.forceSimulation()
            .force("link", d3.forceLink().id(d => d.id).distance(120))
            .force("charge", d3.forceManyBody().strength(-250))
            .force("center", d3.forceCenter(0, 0))
            .force("collision", d3.forceCollide().radius(32));

        let linkElements = g.append("g").attr("class", "links-group").selectAll(".link");
        let nodeElements = g.append("g").attr("class", "nodes-group").selectAll(".node-container");

        // Initial rendering
        renderGraph();

        function renderGraph() {
            // Filter nodes based on type and search query
            const filteredNodes = graphData.nodes.filter(n => {
                const typeMatches = activeTypes.has(n.type);
                const searchMatches = !searchQuery || 
                    n.title.toLowerCase().includes(searchQuery) ||
                    n.id.toLowerCase().includes(searchQuery) ||
                    n.tags.some(t => t.toLowerCase().includes(searchQuery));
                return typeMatches && searchMatches;
            });

            const filteredNodeIds = new Set(filteredNodes.map(n => n.id));

            // Only show links between filtered nodes
            const filteredLinks = graphData.links.filter(l => 
                filteredNodeIds.has(l.source.id || l.source) && 
                filteredNodeIds.has(l.target.id || l.target)
            );

            // Bind Links
            linkElements = linkElements.data(filteredLinks, d => `${d.source.id || d.source}-${d.target.id || d.target}`);
            linkElements.exit().remove();
            
            const linkEnter = linkElements.enter()
                .append("line")
                .attr("class", "link")
                .attr("stroke", "rgba(255,255,255,0.15)")
                .attr("marker-end", "url(#arrow)");
                
            linkElements = linkEnter.merge(linkElements);

            // Bind Nodes
            nodeElements = nodeElements.data(filteredNodes, d => d.id);
            nodeElements.exit().remove();

            const nodeEnter = nodeElements.enter()
                .append("g")
                .attr("class", "node-container")
                .call(d3.drag()
                    .on("start", dragstarted)
                    .on("drag", dragged)
                    .on("end", dragended))
                .on("click", (event, d) => showNodeDetail(d));

            // Draw Node Circles
            nodeEnter.append("circle")
                .attr("class", "node")
                .attr("r", 12)
                .attr("fill", d => getNodeColor(d.type))
                .attr("stroke", "#0f172a")
                .attr("stroke-width", 2);

            // Draw Text Labels
            nodeEnter.append("text")
                .attr("dx", 16)
                .attr("dy", 4)
                .text(d => d.title)
                .attr("fill", "var(--text-primary)")
                .style("font-size", "11px")
                .style("font-weight", "500")
                .style("text-shadow", "0 1px 3px rgba(0,0,0,0.8)")
                .style("pointer-events", "none");

            nodeElements = nodeEnter.merge(nodeElements);

            // Update simulation datasets
            simulation.nodes(filteredNodes);
            simulation.force("link").links(filteredLinks);
            simulation.alpha(0.3).restart();

            // Track node hover details
            nodeElements.on("mouseover", function(event, d) {
                // Dim other nodes
                const neighborIds = new Set([d.id]);
                filteredLinks.forEach(l => {
                    if (l.source.id === d.id) neighborIds.add(l.target.id);
                    if (l.target.id === d.id) neighborIds.add(l.source.id);
                });

                nodeElements.style("opacity", n => neighborIds.has(n.id) ? 1 : 0.15);
                linkElements.style("opacity", l => (l.source.id === d.id || l.target.id === d.id) ? 1 : 0.05);
                linkElements.style("stroke", l => (l.source.id === d.id || l.target.id === d.id) ? varColor(d.type) : "rgba(255,255,255,0.15)");
            }).on("mouseout", function() {
                nodeElements.style("opacity", 1);
                linkElements.style("opacity", 1);
                linkElements.style("stroke", "rgba(255,255,255,0.15)");
            });
        }

        function varColor(type) {
            return colors[type.toLowerCase()] || "#38bdf8";
        }

        // D3 Simulation Tick Update
        simulation.on("tick", () => {
            linkElements
                .attr("x1", d => d.source.x)
                .attr("y1", d => d.source.y)
                .attr("x2", d => d.target.x)
                .attr("y2", d => d.target.y);

            nodeElements.attr("transform", d => `translate(${d.x}, ${d.y})`);
        });

        // Filter Actions
        function updateGraphFilters() {
            activeTypes = new Set();
            d3.selectAll("#filter-checkboxes input").each(function() {
                if (this.checked) activeTypes.add(this.value);
            });
            renderGraph();
        }

        // Search Action
        d3.select("#search-input").on("input", function() {
            searchQuery = this.value.toLowerCase();
            renderGraph();
        });

        // Detail Sidebar Rendering
        function showNodeDetail(node) {
            d3.select("#detail-title").text(node.title);
            d3.select("#detail-path").text(node.id);
            
            const typeBadge = d3.select("#detail-type");
            typeBadge.text(node.type).style("background-color", getNodeColor(node.type));
            
            d3.select("#detail-desc").text(node.description || "No description provided.");
            
            // Clear and add Tag badges
            const tagsDiv = d3.select("#detail-tags").html("");
            if (node.tags && node.tags.length > 0) {
                node.tags.forEach(tag => {
                    tagsDiv.append("span").attr("class", "badge").text(`#${tag}`);
                });
            }
            
            // Parse Markdown Body using marked.js
            const mdContainer = d3.select("#detail-markdown");
            if (node.body) {
                mdContainer.html(marked.parse(node.body));
            } else {
                mdContainer.html("<em style='color: var(--text-secondary)'>Empty concept body.</em>");
            }
            
            d3.select("#sidebar").classed("open", true);
        }

        // Close Detail Sidebar
        d3.select("#detail-close").on("click", () => {
            d3.select("#sidebar").classed("open", false);
        });

        // Drag functions
        function dragstarted(event, d) {
            if (!event.active) simulation.alphaTarget(0.3).restart();
            d.fx = d.x;
            d.fy = d.y;
        }

        function dragged(event, d) {
            d.fx = event.x;
            d.fy = event.y;
        }

        function dragended(event, d) {
            if (!event.active) simulation.alphaTarget(0);
            d.fx = null;
            d.fy = null;
        }

        // Resize behavior
        window.addEventListener("resize", () => {
            const w = container.clientWidth;
            const h = container.clientHeight;
            svg.attr("viewBox", [0, 0, w, h]);
            simulation.force("center", d3.forceCenter(0, 0));
            simulation.alpha(0.1).restart();
        });
    </script>
</body>
</html>
"""
    # Replace placeholder with JSON data
    html_content = html_template.replace("{DATA_JSON}", json.dumps(graph_data, indent=2))
    
    output_path = bundle_root / "visualizer.html"
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
        
    print(f"Generated visualizer.html at /{output_path.relative_to(bundle_root)}")
    manager.log_message(bundle_root, "Regenerated network visualizer")


def compile_graph_data(bundle_root: Path) -> dict:
    """
    Traverses the bundle root to collect all concepts (nodes) and references (links).
    """
    nodes = []
    links = []
    node_map = {}
    
    # Walk directory to find concept files
    for root, dirs, files in os.walk(bundle_root):
        root_path = Path(root)
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        
        for file in files:
            if file.endswith(".md"):
                if file in ("index.md", "log.md", "visualizer.html"):
                    continue
                file_path = root_path / file
                rel_path = f"/{file_path.relative_to(bundle_root)}"
                
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    fm, body = manager.parse_markdown(content)
                    if fm and "type" in fm:
                        node_id = rel_path
                        node_data = {
                            "id": node_id,
                            "title": fm.get("title", file_path.stem.replace("_", " ").title()),
                            "type": fm.get("type"),
                            "tags": fm.get("tags", []),
                            "description": fm.get("description", ""),
                            "body": body.strip()
                        }
                        nodes.append(node_data)
                        node_map[node_id] = node_data
                except Exception:
                    pass
                    
    # Scan bodies for local cross-links
    link_pattern = re.compile(r'\[([^\]]*)\]\(([^)]+)\)')
    for node in nodes:
        node_id = node["id"]
        file_path = bundle_root / node_id.lstrip("/")
        
        links_found = link_pattern.findall(node["body"])
        for label, target in links_found:
            if re.match(r'^(https?://|mailto:|ftp:|ssh:)', target) or target.startswith('#'):
                continue
                
            target_file_part = target.split('#')[0]
            if not target_file_part:
                continue
                
            if target_file_part.startswith("/"):
                resolved_target = target_file_part
            else:
                resolved_path = (file_path.parent / target_file_part).resolve()
                try:
                    resolved_target = f"/{resolved_path.relative_to(bundle_root.resolve())}"
                except ValueError:
                    continue
                    
            if resolved_target in node_map:
                links.append({
                    "source": node_id,
                    "target": resolved_target,
                    "label": label
                })
                
    return {"nodes": nodes, "links": links}


def main():
    parser = argparse.ArgumentParser(
        description="okf-brain: An automated concept ingest engine and graph visualizer for OKF v0.1 bundles."
    )
    parser.add_argument("--root", "-r", help="Specify the OKF bundle root directory (overrides auto-detection)")
    subparsers = parser.add_subparsers(dest="command", required=True, help="Subcommand to run")
    
    # ingest
    ingest_parser = subparsers.add_parser("ingest", help="Extract atomic concepts from source text or URL")
    ingest_parser.add_argument("--source", required=True, help="Raw text, path to local text file, or URL to ingest")
    ingest_parser.add_argument("--mode", choices=["single", "multiple"], default="multiple", help="Specify whether to consolidate info into a single concept file or split into multiple atomic files (default: multiple)")
    
    # visualizer
    subparsers.add_parser("visualizer", help="Regenerate static HTML visualizer graph")
    
    args = parser.parse_args()
    
    if args.root:
        bundle_root = Path(args.root).resolve()
    else:
        cwd = Path.cwd()
        bundle_root = manager.find_bundle_root(cwd)
    
    # Verify we are in a valid bundle or fail
    if not (bundle_root / "index.md").is_file():
        print(f"Error: Directory '{bundle_root}' is not part of a valid OKF bundle (missing root index.md).", file=sys.stderr)
        print("Please run './manager.py init' first to initialize a bundle.", file=sys.stderr)
        sys.exit(1)
        
    try:
        if args.command == "ingest":
            ingest_content(bundle_root, args.source, args.mode)
        elif args.command == "visualizer":
            generate_visualization(bundle_root)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
