#!/usr/bin/env python3
import argparse
import datetime
import json
import os
import re
import sys
from pathlib import Path

# Try importing pyyaml, print a helpful installation message if it's not present
try:
    import yaml
except ImportError:
    print("Error: The 'pyyaml' package is required to run okf-manager.", file=sys.stderr)
    print("Please install it by running: pip install pyyaml", file=sys.stderr)
    sys.exit(1)


def parse_markdown(content: str):
    """
    Parses a markdown string containing YAML frontmatter.
    Returns (frontmatter: dict, body: str).
    If no frontmatter is found, returns (None, content).
    Raises ValueError if frontmatter is present but invalid.
    """
    # Regex to capture YAML frontmatter (enclosed in --- at the start of the file)
    match = re.match(r'^\s*---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
    if match:
        yaml_str = match.group(1)
        body = content[match.end():]
        try:
            frontmatter = yaml.safe_load(yaml_str)
            if not isinstance(frontmatter, dict):
                frontmatter = {}
            return frontmatter, body
        except Exception as e:
            raise ValueError(f"Failed to parse YAML frontmatter: {e}")
    return None, content


def format_markdown(frontmatter: dict, body: str) -> str:
    """
    Constructs a markdown string with frontmatter and body.
    Separates the frontmatter and body with a clean spacing structure.
    """
    yaml_str = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True)
    body_stripped = body.lstrip('\n')
    if body_stripped:
        return f"---\n{yaml_str.strip()}\n---\n\n{body_stripped}"
    else:
        return f"---\n{yaml_str.strip()}\n---\n"


def find_bundle_root(start_path: Path) -> Path:
    """
    Traverses upwards from the start_path to find the nearest ancestor
    containing a valid root index.md or log.md. Falls back to start_path if none found.
    """
    current = start_path.resolve()
    for parent in [current] + list(current.parents):
        index_file = parent / "index.md"
        if index_file.is_file():
            try:
                with open(index_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                frontmatter, _ = parse_markdown(content)
                if frontmatter and "okf_version" in frontmatter:
                    return parent
            except Exception:
                pass
        
        # Fallback to log.md existence check
        log_file = parent / "log.md"
        if log_file.is_file():
            return parent
            
    return current


def load_config() -> dict:
    """
    Loads the OKF config JSON file from the workspace directory.
    """
    config_file = Path(__file__).resolve().parent / ".okf_config.json"
    if config_file.is_file():
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_config(config_data: dict):
    """
    Saves the config JSON file.
    """
    config_file = Path(__file__).resolve().parent / ".okf_config.json"
    with open(config_file, 'w', encoding='utf-8') as f:
        json.dump(config_data, f, indent=2, ensure_ascii=False)


def get_existing_subfolders(bundle_root: Path) -> list:
    """
    Walks the bundle root and returns a sorted list of relative paths for all existing subfolders,
    excluding hidden folders, __pycache__, and Django application directories.
    """
    subfolders = []
    bundle_root_resolved = bundle_root.resolve()
    for root, dirs, files in os.walk(bundle_root_resolved):
        # Exclude hidden folders and Django code folders
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('__pycache__', 'brain_app', 'okf_web')]
        for d in dirs:
            dir_path = Path(root) / d
            try:
                rel_path = dir_path.relative_to(bundle_root_resolved)
                subfolders.append(str(rel_path))
            except ValueError:
                pass
    return sorted(list(set(subfolders)))


def adapt_subfolder(bundle_root: Path, requested_subfolder: str) -> str:
    """
    Maps the requested subfolder to an existing subfolder in the bundle root.
    If it already exists, returns it.
    Otherwise, tries to find the closest matching existing subfolder.
    If no subfolders exist, returns ".".
    """
    existing_subdirs = get_existing_subfolders(bundle_root)
    if not existing_subdirs:
        return "."
        
    requested_clean = requested_subfolder.replace("\\", "/").strip("/").strip().lower()
    if not requested_clean or requested_clean == ".":
        return "."
        
    # Check exact match (case-insensitive)
    for subdir in existing_subdirs:
        if subdir.lower() == requested_clean:
            return subdir
            
    # Check if the requested name is a substring of any existing folder, or vice-versa
    for subdir in existing_subdirs:
        subdir_clean = subdir.lower()
        if requested_clean in subdir_clean or subdir_clean in requested_clean:
            return subdir
            
    # Try fuzzy match: if there's a folder containing "concept" as a preferred fallback
    for subdir in existing_subdirs:
        if "concept" in subdir.lower():
            return subdir
            
    # Default fallback to the first existing subdirectory
    return existing_subdirs[0]


def init_bundle(target_dir: Path):
    """
    Initializes a new OKF v0.1 bundle in the target directory.
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    
    index_file = target_dir / "index.md"
    log_file = target_dir / "log.md"
    
    # Handle index.md creation/verification
    if index_file.is_file():
        print(f"index.md already exists at {index_file.resolve()}")
        try:
            with open(index_file, 'r', encoding='utf-8') as f:
                content = f.read()
            frontmatter, body = parse_markdown(content)
            if frontmatter is None:
                frontmatter = {}
        except Exception:
            frontmatter = {}
            body = content
            
        frontmatter["okf_version"] = "0.1"
        frontmatter.setdefault("type", "index")
        frontmatter.setdefault("title", "Root Index")
        frontmatter.setdefault("description", "Root index of the OKF bundle")
        
        new_content = format_markdown(frontmatter, body)
        with open(index_file, 'w', encoding='utf-8') as f:
            f.write(new_content)
    else:
        frontmatter = {
            "okf_version": "0.1",
            "type": "index",
            "title": "Root Index",
            "description": "Root index of the OKF bundle"
        }
        body = "<!-- OKF-INDEX-START -->\n<!-- OKF-INDEX-END -->\n"
        new_content = format_markdown(frontmatter, body)
        with open(index_file, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"Created index.md at {index_file}")

    # Handle log.md creation
    if not log_file.is_file():
        with open(log_file, 'w', encoding='utf-8') as f:
            f.write("")
        print(f"Created empty log.md at {log_file}")
    else:
        print(f"log.md already exists at {log_file}")
        
    log_message(target_dir, "Initialized OKF bundle")


def log_message(bundle_root: Path, message: str):
    """
    Appends an entry in /log.md under a ## YYYY-MM-DD heading.
    """
    log_file = bundle_root / "log.md"
    if not log_file.is_file():
        if not bundle_root.is_dir():
            raise FileNotFoundError(f"Bundle root directory does not exist: {bundle_root}")
        with open(log_file, 'w', encoding='utf-8') as f:
            f.write("")
            
    now = datetime.datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")
    
    with open(log_file, 'r', encoding='utf-8') as f:
        content = f.read()
        
    heading = f"## {date_str}"
    log_line = f"- [{time_str}] {message}"
    
    lines = content.splitlines()
    heading_index = -1
    for i, line in enumerate(lines):
        if line.strip() == heading:
            heading_index = i
            break
            
    if heading_index != -1:
        # Insert line before the next date heading or at the end of the section
        insert_index = heading_index + 1
        while insert_index < len(lines) and not lines[insert_index].startswith("## "):
            insert_index += 1
        lines.insert(insert_index, log_line)
    else:
        # Insert a new date heading section
        if lines and lines[-1].strip() != "":
            lines.append("")
        lines.append(heading)
        lines.append(log_line)
        
    with open(log_file, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines) + "\n")


def create_concept(bundle_root: Path, subfolder: str, name: str, concept_type: str, title: str, description: str):
    """
    Generates a new concept file with valid UTF-8 markdown and a YAML frontmatter block.
    """
    target_dir = (bundle_root / subfolder).resolve()
    if not target_dir.is_relative_to(bundle_root.resolve()):
        raise ValueError("Cannot create concept files outside the bundle root.")
        
    if not target_dir.is_dir():
        raise FileNotFoundError(f"Subfolder directory does not exist: '{subfolder}'. Directory creation is disabled.")
    
    if not name.endswith(".md"):
        name += ".md"
        
    file_path = target_dir / name
    if file_path.is_file():
        raise FileExistsError(f"Concept file already exists: {file_path.relative_to(bundle_root)}")
        
    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    
    frontmatter = {
        "type": concept_type,
        "title": title,
        "description": description,
        "tags": [],
        "timestamp": timestamp
    }
    
    content = format_markdown(frontmatter, "")
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
        
    rel_path = file_path.relative_to(bundle_root)
    print(f"Created concept file: /{rel_path}")
    log_message(bundle_root, f"Created concept: /{rel_path} (type: {concept_type})")


def update_index_file(bundle_root: Path, dir_path: Path, concepts: list):
    """
    Generates or updates index.md inside dir_path, listing concepts recursively.
    """
    index_file = dir_path / "index.md"
    is_root = (dir_path.resolve() == bundle_root.resolve())
    
    # Group concepts by type
    grouped = {}
    for c in concepts:
        grouped.setdefault(c["type"], []).append(c)
        
    generated_lines = []
    for c_type in sorted(grouped.keys()):
        generated_lines.append(f"### {c_type}")
        # Sort concepts by title
        sorted_concepts = sorted(grouped[c_type], key=lambda x: x["title"].lower())
        for c in sorted_concepts:
            desc_part = f" - {c['description']}" if c['description'] else ""
            generated_lines.append(f"- [{c['title']}]({c['bundle_relative_path']}){desc_part}")
        generated_lines.append("")  # Blank line spacing
        
    generated_content = "\n".join(generated_lines).strip()
    
    frontmatter = {}
    custom_before = ""
    custom_after = ""
    
    if index_file.is_file():
        try:
            with open(index_file, 'r', encoding='utf-8') as f:
                content = f.read()
            fm, body = parse_markdown(content)
            if fm:
                frontmatter = fm
            
            # Locate index markers to preserve custom human text
            start_marker = "<!-- OKF-INDEX-START -->"
            end_marker = "<!-- OKF-INDEX-END -->"
            
            if start_marker in body and end_marker in body:
                idx_start = body.index(start_marker)
                idx_end = body.index(end_marker) + len(end_marker)
                custom_before = body[:idx_start]
                custom_after = body[idx_end:]
            else:
                custom_before = body
                custom_after = ""
        except Exception:
            custom_before = content
            custom_after = ""
            frontmatter = {}
    else:
        # Default frontmatter structure
        rel_dir = dir_path.relative_to(bundle_root)
        dir_name = rel_dir.name if rel_dir.name else "Root"
        frontmatter = {
            "type": "index",
            "title": f"{dir_name} Index",
            "description": f"Index of concepts in {rel_dir}" if rel_dir.name else "Root index of the OKF bundle"
        }
        custom_before = ""
        custom_after = ""
        
    if is_root:
        frontmatter["okf_version"] = "0.1"
        
    # Override description with user-specified purpose from config if available
    rel_dir = dir_path.relative_to(bundle_root)
    rel_dir_str = str(rel_dir).replace("\\", "/")
    if rel_dir_str == ".":
        rel_dir_str = ""
    config = load_config()
    directories = config.get("directories", {})
    custom_desc = directories.get(rel_dir_str)
    if custom_desc:
        frontmatter["description"] = custom_desc
        
    # Build updated body
    new_body_parts = []
    if custom_before.strip():
        new_body_parts.append(custom_before.rstrip())
        new_body_parts.append("")
    new_body_parts.append("<!-- OKF-INDEX-START -->")
    if generated_content:
        new_body_parts.append(generated_content)
    new_body_parts.append("<!-- OKF-INDEX-END -->")
    if custom_after.strip():
        new_body_parts.append("")
        new_body_parts.append(custom_after.lstrip())
        
    new_body = "\n".join(new_body_parts)
    
    new_content = format_markdown(frontmatter, new_body)
    with open(index_file, 'w', encoding='utf-8') as f:
        f.write(new_content)
        
    print(f"Updated index: /{index_file.relative_to(bundle_root)}")


def run_indexing(bundle_root: Path):
    """
    Scans the entire bundle, parses frontmatter of all non-reserved .md files,
    and updates/generates index.md in every directory.
    """
    # 1. Collect all non-reserved markdown files and their metadata
    all_concepts = []
    all_dirs = set()
    
    # We walk the directory tree
    for root, dirs, files in os.walk(bundle_root):
        root_path = Path(root)
        
        # Don't walk inside hidden directories (like .git)
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        
        for file in files:
            if file.endswith(".md"):
                file_path = root_path / file
                rel_path = file_path.relative_to(bundle_root)
                
                # Check if reserved
                if file in ("index.md", "log.md"):
                    continue
                    
                # Parse frontmatter
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    fm, _ = parse_markdown(content)
                    if fm and "type" in fm:
                        c_type = fm.get("type") or "unknown"
                        c_title = fm.get("title") or file_path.stem.replace("_", " ").title()
                        c_desc = fm.get("description") or fm.get("desc") or ""
                        
                        concept_info = {
                            "file_path": file_path,
                            "bundle_relative_path": f"/{rel_path}",
                            "type": c_type,
                            "title": c_title,
                            "description": c_desc
                        }
                        all_concepts.append(concept_info)
                        
                        # Trace directories containing concepts
                        parent = file_path.parent
                        while parent.is_relative_to(bundle_root):
                            all_dirs.add(parent)
                            parent = parent.parent
                except Exception as e:
                    print(f"Warning: Skipping {rel_path} due to parsing error: {e}", file=sys.stderr)
                    
    # Ensure the root is always index updated
    all_dirs.add(bundle_root)
    
    # Ensure all directories configured in .okf_config.json are indexed too (even if empty)
    config = load_config()
    for rel_dir_str in config.get("directories", {}).keys():
        if rel_dir_str:
            dir_path = (bundle_root / rel_dir_str).resolve()
            if dir_path.is_dir() and dir_path.is_relative_to(bundle_root.resolve()):
                all_dirs.add(dir_path)
    
    # 2. Update index.md in each relevant directory
    for d in sorted(all_dirs):
        # Find concepts recursively inside directory d
        d_concepts = [c for c in all_concepts if c["file_path"].is_relative_to(d)]
        update_index_file(bundle_root, d, d_concepts)
        
    log_message(bundle_root, "Regenerated bundle indexes")


def link_concepts(bundle_root: Path, from_path_str: str, to_path_str: str):
    """
    Appends an absolute, bundle-relative markdown hyperlink to the bottom of the source file.
    """
    # Resolve source path
    if from_path_str.startswith("/"):
        source_path = (bundle_root / from_path_str.lstrip("/")).resolve()
    else:
        source_path = Path(from_path_str).resolve()
        if not source_path.is_file():
            alt_path = (bundle_root / from_path_str).resolve()
            if alt_path.is_file():
                source_path = alt_path
        
    # Resolve target path
    if to_path_str.startswith("/"):
        target_path = (bundle_root / to_path_str.lstrip("/")).resolve()
    else:
        target_path = Path(to_path_str).resolve()
        if not target_path.is_file():
            alt_path = (bundle_root / to_path_str).resolve()
            if alt_path.is_file():
                target_path = alt_path
        
    # Validation checks
    if not source_path.is_file():
        raise FileNotFoundError(f"Source file does not exist: {source_path}")
    if not target_path.is_file():
        raise FileNotFoundError(f"Target file does not exist: {target_path}")
        
    if not source_path.is_relative_to(bundle_root.resolve()):
        raise ValueError("Source file is outside the bundle root.")
    if not target_path.is_relative_to(bundle_root.resolve()):
        raise ValueError("Target file is outside the bundle root.")
        
    # Read target title from frontmatter
    target_title = target_path.stem.replace("_", " ").title()
    try:
        with open(target_path, 'r', encoding='utf-8') as f:
            target_content = f.read()
        fm, _ = parse_markdown(target_content)
        if fm and "title" in fm:
            target_title = fm["title"]
    except Exception:
        pass
        
    bundle_relative_target = f"/{target_path.relative_to(bundle_root)}"
    bundle_relative_source = f"/{source_path.relative_to(bundle_root)}"
    
    link_str = f"[{target_title}]({bundle_relative_target})"
    
    # Read source file
    with open(source_path, 'r', encoding='utf-8') as f:
        source_content = f.read()
        
    # Check if this exact link target exists already to prevent duplication
    # We match standard markdown link syntax with the exact target path
    link_regex = re.compile(rf'\[([^\]]*)\]\({re.escape(bundle_relative_target)}\)')
    if link_regex.search(source_content):
        print(f"Link to {bundle_relative_target} already exists in {bundle_relative_source}. Skipping.")
        return
        
    # Append to bottom safely
    if source_content and not source_content.endswith("\n"):
        source_content += "\n"
    source_content += f"\n{link_str}\n"
    
    with open(source_path, 'w', encoding='utf-8') as f:
        f.write(source_content)
        
    print(f"Linked: /{source_path.relative_to(bundle_root)} -> {bundle_relative_target}")
    log_message(bundle_root, f"Linked /{source_path.relative_to(bundle_root)} to {bundle_relative_target}")


def validate_bundle(bundle_root: Path) -> bool:
    """
    Audits the local directory to ensure OKF v0.1 conformance.
    Returns True if valid, False if errors are found.
    """
    print(f"Auditing OKF Bundle at: {bundle_root.resolve()}")
    errors = []
    warnings = []
    checked_files_count = 0
    
    # 1. Structural Checks on Root Reserved Files
    root_index = bundle_root / "index.md"
    root_log = bundle_root / "log.md"
    
    if not root_index.is_file():
        errors.append("Missing root index.md file")
    else:
        try:
            with open(root_index, 'r', encoding='utf-8') as f:
                content = f.read()
            fm, _ = parse_markdown(content)
            if not fm:
                errors.append("Root index.md has no frontmatter")
            elif fm.get("okf_version") != "0.1":
                errors.append(f"Root index.md frontmatter okf_version is '{fm.get('okf_version')}', expected '0.1'")
        except Exception as e:
            errors.append(f"Failed to parse root index.md: {e}")
            
    if not root_log.is_file():
        errors.append("Missing root log.md file")
    else:
        # Validate log structure
        try:
            with open(root_log, 'r', encoding='utf-8') as f:
                log_content = f.read()
            for i, line in enumerate(log_content.splitlines(), 1):
                line_str = line.strip()
                if not line_str:
                    continue
                if line_str.startswith("## "):
                    date_part = line_str[3:].strip()
                    if not re.match(r'^\d{4}-\d{2}-\d{2}$', date_part):
                        errors.append(f"log.md: Line {i} has invalid date heading '{line_str}'. Expected format: '## YYYY-MM-DD'")
                elif line_str.startswith("- "):
                    # Checks format: - [HH:MM:SS] msg
                    pass
                else:
                    errors.append(f"log.md: Line {i} has invalid structure '{line_str}'. Expected date heading or list item.")
        except Exception as e:
            errors.append(f"Failed to read log.md: {e}")
            
    # 2. Scan for Markdown Files and Check Conformance & Links
    # Map from relative file path to its parsed content (if valid) for link checking
    parsed_files = {}
    
    for root, dirs, files in os.walk(bundle_root):
        root_path = Path(root)
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        
        for file in files:
            if file.endswith(".md"):
                file_path = root_path / file
                rel_path = file_path.relative_to(bundle_root)
                rel_str = f"/{rel_path}"
                checked_files_count += 1
                
                # Check reserved index.md at any level
                if file == "index.md":
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                        fm, body = parse_markdown(content)
                        if fm:
                            parsed_files[rel_str] = (fm, body, file_path)
                            if fm.get("type") != "index":
                                errors.append(f"/{rel_path}: Index file frontmatter 'type' field should be 'index', found '{fm.get('type')}'")
                        else:
                            errors.append(f"/{rel_path}: Missing frontmatter")
                    except Exception as e:
                        errors.append(f"/{rel_path}: Failed to parse: {e}")
                    continue
                    
                if file == "log.md":
                    continue
                    
                # Parse non-reserved concept files
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    fm, body = parse_markdown(content)
                    if fm is None:
                        errors.append(f"/{rel_path}: Missing YAML frontmatter block")
                    else:
                        parsed_files[rel_str] = (fm, body, file_path)
                        # Check type field
                        c_type = fm.get("type")
                        if not c_type or not str(c_type).strip():
                            errors.append(f"/{rel_path}: Missing or empty 'type' field in frontmatter")
                except Exception as e:
                    errors.append(f"/{rel_path}: Failed to parse frontmatter: {e}")
                    
    # 3. Cross-Link Validation
    # Regex to capture markdown link targets: [label](target)
    link_pattern = re.compile(r'\[([^\]]*)\]\(([^)]+)\)')
    
    for rel_str, (fm, body, file_path) in parsed_files.items():
        # Find all markdown links in body
        links = link_pattern.findall(body)
        for label, target in links:
            # Ignore absolute URLs (http, https, mailto, etc.) and anchor-only links
            if re.match(r'^(https?://|mailto:|ftp:|ssh:)', target) or target.startswith('#'):
                continue
                
            # Strip anchors
            target_file_part = target.split('#')[0]
            if not target_file_part:
                continue
                
            # Resolve target path relative to the bundle
            if target_file_part.startswith("/"):
                # Bundle-relative path
                resolved_target_path = (bundle_root / target_file_part.lstrip("/")).resolve()
            else:
                # Relative to current file's directory
                resolved_target_path = (file_path.parent / target_file_part).resolve()
                
            # Verify file existence
            if not resolved_target_path.is_file():
                warnings.append(f"Broken link in {rel_str}: '{target}' does not resolve to a file")
            elif not resolved_target_path.is_relative_to(bundle_root.resolve()):
                warnings.append(f"External local file reference in {rel_str}: '{target}' points outside the bundle root")
                
    # 4. Report results
    print("\n--- Validation Audit Report ---")
    print(f"Total markdown files checked: {checked_files_count}")
    
    if warnings:
        print(f"\nWarnings ({len(warnings)}):")
        for warning in warnings:
            print(f"  [WARN] {warning}")
            
    if errors:
        print(f"\nErrors ({len(errors)}):")
        for error in errors:
            print(f"  [ERROR] {error}")
        print("\nAudit Status: FAILED")
        return False
    else:
        print("\nAudit Status: SUCCESS")
        return True


def scaffold_bundle(bundle_root: Path, blueprint_path: Path):
    """
    Scaffolds the directory structure and placeholder files specified by the blueprint.
    """
    if not blueprint_path.is_file():
        raise FileNotFoundError(f"Blueprint file not found: {blueprint_path}")
        
    with open(blueprint_path, 'r', encoding='utf-8') as f:
        try:
            blueprint = yaml.safe_load(f)
        except Exception as e:
            raise ValueError(f"Failed to parse blueprint YAML: {e}")
            
    # Standardize to list of directory definitions
    directories_config = []
    if isinstance(blueprint, dict):
        if "directories" in blueprint:
            directories_config = blueprint["directories"]
        elif "dirs" in blueprint:
            directories_config = blueprint["dirs"]
        else:
            raise ValueError("Blueprint YAML must contain a list or a 'directories' key at its root.")
    elif isinstance(blueprint, list):
        directories_config = blueprint
    else:
        raise ValueError("Blueprint top-level must be a dictionary or a list.")
        
    # Auto-initialize the bundle root if needed
    init_bundle(bundle_root)
    
    for folder_spec in directories_config:
        if not isinstance(folder_spec, dict):
            continue
            
        subfolder = folder_spec.get("path") or folder_spec.get("dir")
        if not subfolder:
            print("Warning: Skipping blueprint item containing no path/dir.", file=sys.stderr)
            continue
            
        files_spec = folder_spec.get("files", [])
        for file_spec in files_spec:
            if not isinstance(file_spec, dict):
                continue
                
            name = file_spec.get("name") or file_spec.get("filename")
            if not name:
                print(f"Warning: Skipping file spec in directory '{subfolder}' due to missing file name.", file=sys.stderr)
                continue
                
            concept_type = file_spec.get("type", "concept")
            title = file_spec.get("title") or name.rsplit(".", 1)[0].replace("_", " ").title()
            description = file_spec.get("description") or file_spec.get("desc", "")
            
            try:
                create_concept(
                    bundle_root=bundle_root,
                    subfolder=subfolder,
                    name=name,
                    concept_type=concept_type,
                    title=title,
                    description=description
                )
            except FileExistsError as e:
                print(f"Warning: File already exists, skipping: {e}", file=sys.stderr)
            except Exception as e:
                print(f"Error creating file {name} in {subfolder}: {e}", file=sys.stderr)


def rename_concept(bundle_root: Path, old_rel_path: str, new_rel_path: str, new_title: str = None) -> int:
    """
    Renames a concept file from old_rel_path to new_rel_path.
    Updates title inside YAML frontmatter if new_title is provided.
    Scans all other markdown files to update any cross-links.
    Regenerates index files.
    Returns the number of referencing files updated.
    """
    old_rel = old_rel_path.lstrip("/")
    new_rel = new_rel_path.lstrip("/")
    
    old_file = (bundle_root / old_rel).resolve()
    new_file = (bundle_root / new_rel).resolve()
    
    if not old_file.is_file():
        raise FileNotFoundError(f"Concept file not found at: {old_rel}")
        
    if new_file.exists() and new_file.resolve() != old_file.resolve():
        raise FileExistsError(f"Target path already exists: {new_rel}")
        
    # Ensure parent dir of target exists
    if not new_file.parent.is_dir():
        raise FileNotFoundError(f"Target parent directory does not exist: '{new_file.parent.relative_to(bundle_root)}'. Directory creation is disabled.")
    
    # 1. Read file content and update frontmatter if needed
    with open(old_file, 'r', encoding='utf-8') as f:
        content = f.read()
        
    frontmatter, body = parse_markdown(content)
    if new_title and frontmatter:
        frontmatter['title'] = new_title
        content = format_markdown(frontmatter, body)
        
    # 2. Write to new location
    with open(new_file, 'w', encoding='utf-8') as f:
        f.write(content)
        
    # Remove old file if it's different
    if old_file.resolve() != new_file.resolve():
        old_file.unlink()
        # Clean up empty parent directories
        parent = old_file.parent
        while parent != bundle_root:
            try:
                if not any(parent.iterdir()):
                    parent.rmdir()
                    parent = parent.parent
                else:
                    break
            except Exception:
                break
                
    # 3. Update references in other files
    old_href = f"/{old_rel}"
    new_href = f"/{new_rel}"
    
    updated_count = 0
    for root, dirs, files in os.walk(bundle_root):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for file in files:
            if file.endswith(".md"):
                file_path = Path(root) / file
                if file_path.resolve() == new_file.resolve():
                    continue
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        file_content = f.read()
                    
                    modified = False
                    # Absolute links like [text](/old_rel)
                    if f"({old_href})" in file_content:
                        file_content = file_content.replace(f"({old_href})", f"({new_href})")
                        modified = True
                        
                    # Relative links (if filenames differ)
                    if old_file.name != new_file.name and f"({old_file.name})" in file_content:
                        file_content = file_content.replace(f"({old_file.name})", f"({new_file.name})")
                        modified = True
                        
                    if modified:
                        with open(file_path, 'w', encoding='utf-8') as f:
                            f.write(file_content)
                        updated_count += 1
                except Exception:
                    pass
                    
    # 4. Regenerate indices
    run_indexing(bundle_root)
    
    return updated_count


def delete_concept(bundle_root: Path, rel_path: str) -> int:
    """
    Deletes the concept file at rel_path relative to bundle_root.
    Scans all other markdown files to remove references.
    If the reference is a list item, removes the whole line.
    If it is inline, removes the link markup keeping the anchor text.
    Regenerates index files.
    Returns the number of referencing files updated.
    """
    rel = rel_path.lstrip("/")
    target_file = (bundle_root / rel).resolve()
    
    if not target_file.is_file():
        raise FileNotFoundError(f"Concept file not found at: {rel}")
        
    filename = target_file.name
    
    # 1. Unlink file
    target_file.unlink()
    
    # Clean up empty parent directories
    parent = target_file.parent
    while parent != bundle_root:
        try:
            if not any(parent.iterdir()):
                parent.rmdir()
                parent = parent.parent
            else:
                break
        except Exception:
            break
            
    # 2. Update references in other files
    href = f"/{rel}"
    import re
    abs_pattern = re.compile(rf'\[([^\]]+)\]\({re.escape(href)}\)')
    rel_pattern = re.compile(rf'\[([^\]]+)\]\({re.escape(filename)}\)')
    
    updated_count = 0
    for root_dir, dirs, files in os.walk(bundle_root):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for file in files:
            if file.endswith(".md"):
                file_path = Path(root_dir) / file
                if file_path.resolve() == target_file.resolve():
                    continue
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        file_content = f.read()
                        
                    lines = file_content.splitlines()
                    new_lines = []
                    modified = False
                    
                    for line in lines:
                        if f"({href})" in line or f"({filename})" in line:
                            stripped = line.strip()
                            if stripped.startswith("- ") or stripped.startswith("* ") or (stripped and stripped[0].isdigit()):
                                modified = True
                                continue
                            else:
                                line = abs_pattern.sub(r'\1', line)
                                line = rel_pattern.sub(r'\1', line)
                                modified = True
                        new_lines.append(line)
                        
                    if modified:
                        result = "\n".join(new_lines)
                        if file_content.endswith("\n") and not result.endswith("\n"):
                            result += "\n"
                        with open(file_path, 'w', encoding='utf-8') as f:
                            f.write(result)
                        updated_count += 1
                except Exception:
                    pass
                    
    # 3. Regenerate indices
    run_indexing(bundle_root)
    
    return updated_count


def rebuild_bundle(bundle_root: Path) -> int:
    """
    Rebuilds the OKF bundle by resolving and removing all broken internal references
    and updating index files.
    """
    # 1. Gather all existing concept files relative to bundle root
    existing_rel_paths = set()
    for root_dir, dirs, files in os.walk(bundle_root):
        root_path = Path(root_dir)
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for file in files:
            if file.endswith(".md"):
                if file in ("index.md", "log.md"):
                    continue
                file_path = root_path / file
                rel_path = f"/{file_path.relative_to(bundle_root)}"
                existing_rel_paths.add(rel_path)
                
    # 2. Scan all concept files and clean up references that are not in existing_rel_paths
    import re
    link_regex = re.compile(r'\[([^\]]+)\]\((/[^)]+\.md)\)')
    
    broken_links_removed = 0
    
    for root_dir, dirs, files in os.walk(bundle_root):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for file in files:
            if file.endswith(".md"):
                if file in ("index.md", "log.md"):
                    continue
                file_path = Path(root_dir) / file
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        file_content = f.read()
                        
                    lines = file_content.splitlines()
                    new_lines = []
                    modified = False
                    
                    for line in lines:
                        matches = link_regex.findall(line)
                        line_broken = False
                        
                        for anchor, target in matches:
                            if target.startswith('/') and target not in existing_rel_paths:
                                line_broken = True
                                break
                                
                        if line_broken:
                            stripped = line.strip()
                            if stripped.startswith("- ") or stripped.startswith("* ") or (stripped and stripped[0].isdigit()):
                                modified = True
                                broken_links_removed += 1
                                continue
                            else:
                                for anchor, target in matches:
                                    if target.startswith('/') and target not in existing_rel_paths:
                                        target_pattern = re.compile(rf'\[{re.escape(anchor)}\]\({re.escape(target)}\)')
                                        line = target_pattern.sub(anchor, line)
                                modified = True
                                broken_links_removed += 1
                                
                        new_lines.append(line)
                        
                    if modified:
                        result = "\n".join(new_lines)
                        if file_content.endswith("\n") and not result.endswith("\n"):
                            result += "\n"
                        with open(file_path, 'w', encoding='utf-8') as f:
                            f.write(result)
                except Exception:
                    pass
                    
    # 3. Clean up empty parent directories
    for root_dir, dirs, files in os.walk(bundle_root, topdown=False):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for d in dirs:
            dir_path = Path(root_dir) / d
            try:
                if not any(dir_path.iterdir()):
                    dir_path.rmdir()
            except Exception:
                pass
                
    # 4. Regenerate all index files
    run_indexing(bundle_root)
    
    return broken_links_removed


def main():
    parser = argparse.ArgumentParser(
        description="okf-manager: A CLI lifecycle tool for Open Knowledge Format (OKF) v0.1 bundles."
    )
    parser.add_argument("--root", "-r", help="Specify the OKF bundle root directory (overrides auto-detection)")
    subparsers = parser.add_subparsers(dest="command", required=True, help="Subcommand to run")
    
    # init
    init_parser = subparsers.add_parser("init", help="Initialize a conformant OKF bundle in a directory")
    init_parser.add_argument("directory", nargs="?", default=".", help="Directory to initialize (default: current)")
    
    # create
    create_parser = subparsers.add_parser("create", help="Create a new concept file with valid frontmatter")
    create_parser.add_argument("--dir", required=True, help="Subfolder inside the bundle relative to root")
    create_parser.add_argument("--name", required=True, help="Filename of the concept (e.g. general_relativity.md)")
    create_parser.add_argument("--type", required=True, help="Type of the concept")
    create_parser.add_argument("--title", required=True, help="Title of the concept")
    create_parser.add_argument("--desc", required=True, help="Description of the concept")
    
    # index
    subparsers.add_parser("index", help="Scan the bundle tree and update/generate all index.md files")
    
    # link
    link_parser = subparsers.add_parser("link", help="Append an absolute, bundle-relative hyperlink in a source file")
    link_parser.add_argument("--from", dest="from_path", required=True, help="Source markdown file path")
    link_parser.add_argument("--to", dest="to_path", required=True, help="Target markdown file path")
    
    # log
    log_parser = subparsers.add_parser("log", help="Append a timestamped operation line to log.md")
    log_parser.add_argument("--msg", required=True, help="Modification operation description")
    
    # validate
    subparsers.add_parser("validate", help="Validate conformance of the local directory to OKF v0.1")
    
    # scaffold
    scaffold_parser = subparsers.add_parser("scaffold", help="Bulk-generate directories and concepts from a blueprint YAML")
    scaffold_parser.add_argument("--config", required=True, help="Path to blueprint config YAML file")
    
    # rename
    rename_parser = subparsers.add_parser("rename", help="Rename a concept and update all cross-links pointing to it")
    rename_parser.add_argument("--from", dest="from_path", required=True, help="Current bundle-relative path of the concept (e.g. concepts/quantum.md)")
    rename_parser.add_argument("--to", dest="to_path", required=True, help="Target bundle-relative path of the concept (e.g. concepts/quantum_mechanics.md)")
    rename_parser.add_argument("--title", help="New title for the concept frontmatter (optional)")
    
    # delete
    delete_parser = subparsers.add_parser("delete", help="Delete a concept and update all cross-links pointing to it")
    delete_parser.add_argument("--path", required=True, help="Bundle-relative path of the concept to delete (e.g. concepts/quantum.md)")
    
    # rebuild
    subparsers.add_parser("rebuild", help="Scan bundle, resolve all broken links, remove empty folders, and rebuild indexes")
    
    args = parser.parse_args()
    
    # Resolve target directory for init
    if args.command == "init":
        if args.root and args.directory == ".":
            target_dir = Path(args.root).resolve()
        else:
            target_dir = Path(args.directory)
        init_bundle(target_dir)
        sys.exit(0)
        
    # Resolve the bundle root
    if args.root:
        bundle_root = Path(args.root).resolve()
    else:
        cwd = Path.cwd()
        bundle_root = find_bundle_root(cwd)
    
    # Check if we are outside any valid bundle directory tree for commands that require it
    if args.command != "init" and not (bundle_root / "index.md").is_file():
        print(f"Error: Directory '{bundle_root}' is not part of a valid OKF bundle (missing root index.md).", file=sys.stderr)
        print("Run 'okf-manager init' first to initialize a new bundle.", file=sys.stderr)
        sys.exit(1)
        
    try:
        if args.command == "create":
            create_concept(
                bundle_root=bundle_root,
                subfolder=args.dir,
                name=args.name,
                concept_type=args.type,
                title=args.title,
                description=args.desc
            )
        elif args.command == "index":
            run_indexing(bundle_root)
        elif args.command == "link":
            link_concepts(bundle_root, args.from_path, args.to_path)
        elif args.command == "log":
            log_message(bundle_root, args.msg)
            print(f"Logged action: '{args.msg}' to /log.md")
        elif args.command == "validate":
            success = validate_bundle(bundle_root)
            sys.exit(0 if success else 1)
        elif args.command == "scaffold":
            blueprint_path = Path(args.config)
            scaffold_bundle(bundle_root, blueprint_path)
            print("Scaffolding complete.")
        elif args.command == "rename":
            count = rename_concept(bundle_root, args.from_path, args.to_path, args.title)
            print(f"Successfully renamed {args.from_path} to {args.to_path}.")
            print(f"Updated {count} referencing file(s).")
            # Log action
            log_message(bundle_root, f"Renamed concept from {args.from_path} to {args.to_path}")
        elif args.command == "delete":
            count = delete_concept(bundle_root, args.path)
            print(f"Successfully deleted concept: {args.path}")
            print(f"Removed references in {count} file(s).")
            # Log action
            log_message(bundle_root, f"Deleted concept: {args.path}")
        elif args.command == "rebuild":
            count = rebuild_bundle(bundle_root)
            print("Bundle rebuilt successfully.")
            print(f"Removed {count} broken link reference(s).")
            # Log action
            log_message(bundle_root, "Rebuilt and synchronized bundle structure")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
