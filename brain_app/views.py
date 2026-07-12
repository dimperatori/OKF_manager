import os
import re
import sys
import json
import datetime
from pathlib import Path
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.contrib import messages

# Add workspace directory to path to import manager & brain
WORKSPACE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE_DIR))

import manager
import brain

def get_bundle_root(request=None):
    if request and 'bundle_root' in request.session:
        path = Path(request.session['bundle_root'])
        if path.is_dir():
            return path
            
    # Check config file
    config_file = WORKSPACE_DIR / ".okf_config.json"
    if config_file.is_file():
        try:
            with open(config_file, 'r') as f:
                cfg = json.load(f)
            path_str = cfg.get("bundle_root")
            if path_str:
                path = Path(path_str)
                if path.is_dir():
                    return path
        except Exception:
            pass
            
    return manager.find_bundle_root(WORKSPACE_DIR)


def dashboard(request):
    root = get_bundle_root(request)
    concepts = brain.scan_existing_concepts(root)
    
    # 1. Total Counts
    total_concepts = len(concepts)
    
    # 2. Type distribution
    type_counts = {}
    for c in concepts:
        c_type = c["type"]
        type_counts[c_type] = type_counts.get(c_type, 0) + 1
        
    # 3. Read log file
    log_file = root / "log.md"
    logs = []
    if log_file.is_file():
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                log_content = f.read()
                
            current_date = None
            date_entries = []
            
            for line in log_content.splitlines():
                line_str = line.strip()
                if not line_str:
                    continue
                if line_str.startswith("## "):
                    if current_date:
                        logs.append({"date": current_date, "entries": date_entries})
                    current_date = line_str[3:].strip()
                    date_entries = []
                elif line_str.startswith("- "):
                    date_entries.append(line_str[2:].strip())
            
            if current_date:
                logs.append({"date": current_date, "entries": date_entries})
        except Exception as e:
            messages.warning(request, f"Could not parse log.md: {e}")
            
    # Show last 5 days of logs
    logs = logs[:5]
    
    context = {
        "total_concepts": total_concepts,
        "type_counts": type_counts,
        "logs": logs,
        "bundle_root": root
    }
    return render(request, 'brain_app/dashboard.html', context)


def concepts_list(request):
    root = get_bundle_root(request)
    concepts = brain.scan_existing_concepts(root)
    
    query = request.GET.get('q', '').strip().lower()
    selected_type = request.GET.get('type', '').strip()
    
    # Apply filtering
    filtered_concepts = []
    for c in concepts:
        match_query = not query or (
            query in c["title"].lower() or 
            query in c["path"].lower() or 
            query in c["description"].lower()
        )
        match_type = not selected_type or c["type"] == selected_type
        
        if match_query and match_type:
            filtered_concepts.append(c)
            
    unique_types = sorted(list(set(c["type"] for c in concepts)))
    
    context = {
        "concepts": sorted(filtered_concepts, key=lambda x: x["title"].lower()),
        "unique_types": unique_types,
        "query": query,
        "selected_type": selected_type,
    }
    return render(request, 'brain_app/concepts_list.html', context)


def concept_detail(request, rel_path):
    root = get_bundle_root(request)
    
    # Clean rel_path to prevent path traversal
    clean_path = rel_path.lstrip("/")
    file_path = (root / clean_path).resolve()
    
    if not file_path.is_file() or not file_path.is_relative_to(root.resolve()):
        messages.error(request, f"Concept file not found: {rel_path}")
        return redirect('brain_app:concepts_list')
        
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        frontmatter, body = manager.parse_markdown(content)
    except Exception as e:
        messages.error(request, f"Failed to parse concept file: {e}")
        return redirect('brain_app:concepts_list')
        
    # Analyze references (Outward links) and backlinks (Inward links)
    outward_links = []
    backlinks = []
    
    # Compile graph to easily search edges
    graph_data = brain.compile_graph_data(root)
    
    my_path = f"/{clean_path}"
    
    # Search references
    for edge in graph_data["links"]:
        if edge["source"] == my_path:
            outward_links.append({
                "path": edge["target"],
                "title": edge["target"].split("/")[-1].replace(".md", "").replace("_", " ").title()
            })
        elif edge["target"] == my_path:
            backlinks.append({
                "path": edge["source"],
                "title": edge["source"].split("/")[-1].replace(".md", "").replace("_", " ").title()
            })
            
    # Derive subfolder name and retrieve existing subfolders for UI selection
    parent_dir = Path(clean_path).parent
    subfolder = "" if parent_dir == Path('.') else str(parent_dir)
    existing_subfolders = manager.get_existing_subfolders(root)

    context = {
        "rel_path": my_path,
        "frontmatter": frontmatter,
        "body": body,
        "outward_links": outward_links,
        "backlinks": backlinks,
        "filename": file_path.name,
        "subfolder": subfolder,
        "existing_subfolders": existing_subfolders
    }
    return render(request, 'brain_app/concept_detail.html', context)


def ingest(request):
    if request.method == 'POST':
        source = request.POST.get('source', '').strip()
        mode = request.POST.get('mode', 'multiple')
        if not source:
            messages.error(request, "Source content cannot be empty.")
            return redirect('brain_app:ingest')
            
        root = get_bundle_root(request)
        try:
            brain.ingest_content(root, source, mode)
            messages.success(request, "Ingestion process completed successfully! Check the dashboard or visualizer.")
            return redirect('brain_app:concepts_list')
        except Exception as e:
            messages.error(request, f"Failed to ingest content: {e}")
            return redirect('brain_app:ingest')
            
    return render(request, 'brain_app/ingest.html')


def link(request):
    root = get_bundle_root(request)
    concepts = brain.scan_existing_concepts(root)
    
    if request.method == 'POST':
        from_path = request.POST.get('from_path')
        to_path = request.POST.get('to_path')
        bidirectional = request.POST.get('bidirectional') == 'on'
        
        if not from_path or not to_path:
            messages.error(request, "Please select both source and target concepts.")
            return redirect('brain_app:link')
            
        if from_path == to_path:
            messages.error(request, "Cannot link a concept to itself.")
            return redirect('brain_app:link')
            
        try:
            # Create link from source to target
            manager.link_concepts(root, from_path, to_path)
            
            # Optionally create link from target to source
            if bidirectional:
                manager.link_concepts(root, to_path, from_path)
                
            # Reindex
            manager.run_indexing(root)
            
            messages.success(request, f"Successfully created link: {from_path} {'<->' if bidirectional else '->'} {to_path}")
            return redirect('brain_app:visualizer')
        except Exception as e:
            messages.error(request, f"Failed to create link: {e}")
            return redirect('brain_app:link')
            
    # Sort concepts by title
    sorted_concepts = sorted(concepts, key=lambda x: x["title"].lower())
    context = {
        "concepts": sorted_concepts
    }
    return render(request, 'brain_app/link.html', context)


def validate_view(request):
    root = get_bundle_root(request)
    errors = []
    warnings = []
    checked_files_count = 0
    
    # We implement structural validation details dynamically to show in the browser
    root_index = root / "index.md"
    root_log = root / "log.md"
    
    # 1. Structural Checks
    if not root_index.is_file():
        errors.append("Missing root index.md file")
    else:
        try:
            with open(root_index, 'r', encoding='utf-8') as f:
                content = f.read()
            fm, _ = manager.parse_markdown(content)
            if not fm:
                errors.append("Root index.md has no frontmatter")
            elif fm.get("okf_version") != "0.1":
                errors.append(f"Root index.md frontmatter okf_version is '{fm.get('okf_version')}', expected '0.1'")
        except Exception as e:
            errors.append(f"Failed to parse root index.md: {e}")
            
    if not root_log.is_file():
        errors.append("Missing root log.md file")
    else:
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
                elif not line_str.startswith("- "):
                    errors.append(f"log.md: Line {i} has invalid structure '{line_str}'. Expected list item or date heading.")
        except Exception as e:
            errors.append(f"Failed to read log.md: {e}")
            
    # 2. File Check Walk
    parsed_files = {}
    for root_dir, dirs, files in os.walk(root):
        root_path = Path(root_dir)
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        
        for file in files:
            if file.endswith(".md"):
                file_path = root_path / file
                rel_path = file_path.relative_to(root)
                rel_str = f"/{rel_path}"
                checked_files_count += 1
                
                # Check reserved index.md
                if file == "index.md":
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                        fm, body = manager.parse_markdown(content)
                        if fm:
                            parsed_files[rel_str] = (fm, body, file_path)
                            if fm.get("type") != "index":
                                errors.append(f"/{rel_path}: Index type must be 'index', found '{fm.get('type')}'")
                        else:
                            errors.append(f"/{rel_path}: Missing frontmatter")
                    except Exception as e:
                        errors.append(f"/{rel_path}: Failed to parse: {e}")
                    continue
                    
                if file == "log.md":
                    continue
                    
                # Concept files
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    fm, body = manager.parse_markdown(content)
                    if fm is None:
                        errors.append(f"/{rel_path}: Missing YAML frontmatter")
                    else:
                        parsed_files[rel_str] = (fm, body, file_path)
                        if not fm.get("type") or not str(fm.get("type")).strip():
                            errors.append(f"/{rel_path}: Missing or empty 'type' field")
                except Exception as e:
                    errors.append(f"/{rel_path}: Failed to parse frontmatter: {e}")
                    
    # 3. Link audit
    link_pattern = re.compile(r'\[([^\]]*)\]\(([^)]+)\)')
    for rel_str, (fm, body, file_path) in parsed_files.items():
        links = link_pattern.findall(body)
        for label, target in links:
            if re.match(r'^(https?://|mailto:|ftp:|ssh:)', target) or target.startswith('#'):
                continue
                
            target_file_part = target.split('#')[0]
            if not target_file_part:
                continue
                
            if target_file_part.startswith("/"):
                resolved_target_path = (root / target_file_part.lstrip("/")).resolve()
            else:
                resolved_target_path = (file_path.parent / target_file_part).resolve()
                
            if not resolved_target_path.is_file():
                warnings.append(f"Broken link in {rel_str}: '{target}' does not resolve to a file")
            elif not resolved_target_path.is_relative_to(root.resolve()):
                warnings.append(f"External local file reference in {rel_str}: '{target}' points outside the bundle root")
                
    context = {
        "errors": errors,
        "warnings": warnings,
        "checked_files_count": checked_files_count,
        "is_valid": len(errors) == 0
    }
    return render(request, 'brain_app/validate.html', context)


def visualizer_view(request):
    root = get_bundle_root(request)
    graph_data = brain.compile_graph_data(root)
    context = {
        "graph_data_json": json.dumps(graph_data, indent=2)
    }
    return render(request, 'brain_app/visualizer.html', context)


def graph_api(request):
    root = get_bundle_root(request)
    graph_data = brain.compile_graph_data(root)
    return JsonResponse(graph_data)


def change_root(request):
    if request.method == 'POST':
        new_path_str = request.POST.get('new_root_path', '').strip()
        init_if_missing = request.POST.get('init_if_missing') == 'on'
        
        if not new_path_str:
            messages.error(request, "Path cannot be empty.")
            return redirect('brain_app:dashboard')
            
        new_path = Path(new_path_str).resolve()
        
        # Check if exists
        if not new_path.is_dir():
            if init_if_missing:
                try:
                    manager.init_bundle(new_path)
                    messages.success(request, f"Created and initialized a new OKF bundle at: {new_path}")
                except Exception as e:
                    messages.error(request, f"Failed to initialize directory: {e}")
                    return redirect('brain_app:dashboard')
            else:
                messages.error(request, f"Directory does not exist: {new_path_str}. Check 'Initialize if missing' to create it.")
                return redirect('brain_app:dashboard')
        else:
            # Check if it has a root index.md, if not warn/init
            root_index = new_path / "index.md"
            if not root_index.is_file():
                if init_if_missing:
                    try:
                        manager.init_bundle(new_path)
                        messages.success(request, f"Initialized existing directory as OKF bundle: {new_path}")
                    except Exception as e:
                        messages.error(request, f"Failed to initialize: {e}")
                        return redirect('brain_app:dashboard')
                else:
                    messages.warning(request, f"The selected directory is not a initialized OKF bundle (missing index.md).")
                    
        # Save to session and config
        request.session['bundle_root'] = str(new_path)
        
        config_file = WORKSPACE_DIR / ".okf_config.json"
        try:
            with open(config_file, 'w') as f:
                json.dump({"bundle_root": str(new_path)}, f)
        except Exception as e:
            messages.warning(request, f"Failed to save configuration file: {e}")
            
        messages.success(request, f"Switched active OKF bundle to: {new_path}")
        
    return redirect('brain_app:dashboard')


def chat_view(request):
    return render(request, 'brain_app/chat.html')


def chat_message_api(request):
    if request.method != 'POST':
        return JsonResponse({"error": "POST method required"}, status=405)
        
    try:
        data = json.loads(request.body)
        user_message = data.get("message", "").strip()
        history = data.get("history", [])
    except Exception:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
        
    if not user_message:
        return JsonResponse({"error": "Message cannot be empty"}, status=400)
        
    root = get_bundle_root(request)
    
    # 1. Compile all bundle files and content as context
    context_parts = []
    for root_dir, dirs, files in os.walk(root):
        root_path = Path(root_dir)
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for file in files:
            if file.endswith(".md"):
                if file in ("index.md", "log.md", "visualizer.html"):
                    continue
                file_path = root_path / file
                rel_path = f"/{file_path.relative_to(root)}"
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    context_parts.append(f"Archivo: {rel_path}\nContenido:\n{content}\n-------------------")
                except Exception:
                    pass
    context_data = "\n\n".join(context_parts)
    
    # 2. Check for Gemini Key
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        concepts = brain.scan_existing_concepts(root)
        mock_reply = (
            "*(Modo de prueba: GEMINI_API_KEY no configurado en el servidor)*\n\n"
            "¡Hola! Soy tu asistente OKF local. Actualmente estoy ejecutándome en modo de prueba sin conexión a la IA de Gemini.\n\n"
            f"He escaneado tu base de conocimientos en **`{root}`** y he encontrado estos conceptos:\n"
        )
        for c in concepts:
            mock_reply += f"- **{c['title']}** (tipo: `{c['type']}`, ruta: `{c['path']}`)\n"
        mock_reply += "\nPara poderme hacer preguntas complejas, redactar nuevos temas o analizar tu grafo, por favor establece la variable `GEMINI_API_KEY` antes de iniciar el servidor."
        return JsonResponse({"response": mock_reply})
        
    # 3. Call Chat API
    try:
        from .chat_helper import call_gemini_chat
        
        # Append the new user message to history
        # History format: [{"role": "user"|"model", "parts": [{"text": "..."}]}]
        history.append({
            "role": "user",
            "parts": [{"text": user_message}]
        })
        
        reply = call_gemini_chat(api_key, history, context_data)
        return JsonResponse({"response": reply})
    except Exception as e:
        return JsonResponse({"error": f"Error calling Gemini Chat: {e}"}, status=500)


def rename_concept_view(request, rel_path):
    if request.method != 'POST':
        return HttpResponse("Method not allowed", status=405)
        
    root = get_bundle_root(request)
    old_rel = rel_path.lstrip("/")
    
    new_title = request.POST.get('title', '').strip()
    new_subfolder = request.POST.get('subfolder', '').strip().lower()
    new_filename = request.POST.get('filename', '').strip().lower()
    
    if not new_filename:
        messages.error(request, "Filename cannot be empty.")
        return redirect('brain_app:concept_detail', rel_path=rel_path)
        
    if not new_filename.endswith(".md"):
        new_filename += ".md"
        
    # Default to same subfolder if empty
    if not new_subfolder:
        parent_dir = Path(old_rel).parent
        if parent_dir == Path('.'):
            new_subfolder = ""
        else:
            new_subfolder = parent_dir.name
            
    if new_subfolder == "." or not new_subfolder:
        new_rel = new_filename
    else:
        new_rel = f"{new_subfolder}/{new_filename}"
        
    try:
        updated_refs = manager.rename_concept(root, old_rel, new_rel, new_title)
        messages.success(request, f"Concept renamed successfully! {updated_refs} referencing link(s) updated.")
        return redirect('brain_app:concept_detail', rel_path=new_rel)
    except Exception as e:
        messages.error(request, f"Failed to rename concept: {e}")
        return redirect('brain_app:concept_detail', rel_path=rel_path)


def delete_concept_view(request, rel_path):
    if request.method != 'POST':
        return HttpResponse("Method not allowed", status=405)
        
    root = get_bundle_root(request)
    rel = rel_path.lstrip("/")
    
    try:
        updated_refs = manager.delete_concept(root, rel)
        messages.success(request, f"Concept deleted successfully! Removed referring links in {updated_refs} file(s).")
        return redirect('brain_app:concepts_list')
    except Exception as e:
        messages.error(request, f"Failed to delete concept: {e}")
        return redirect('brain_app:concept_detail', rel_path=rel_path)


def rebuild_bundle_view(request):
    if request.method != 'POST':
        return HttpResponse("Method not allowed", status=405)
        
    root = get_bundle_root(request)
    try:
        removed_links = manager.rebuild_bundle(root)
        messages.success(request, f"Bundle rebuilt and synchronized successfully! Removed {removed_links} broken link reference(s).")
    except Exception as e:
        messages.error(request, f"Failed to rebuild bundle: {e}")
        
    return redirect('brain_app:dashboard')
