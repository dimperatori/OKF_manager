import json
import urllib.request
import urllib.error
import ssl

def call_gemini_chat(api_key: str, history: list, context_data: str) -> str:
    """
    Sends the chat history and bundle context to the Gemini API (gemini-2.5-flash)
    using standard libraries.
    """
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    headers = {
        "Content-Type": "application/json"
    }
    
    # System instruction guiding the LLM
    system_instruction = f"""Eres el "Asistente OKF", un experto Ingeniero de Conocimiento y Arquitecto de Sistemas.
Tu tarea es ayudar al usuario a consultar, comprender, editar y expandir su repositorio local de conocimientos estructurado bajo el estándar Open Knowledge Format (OKF) v0.1.

INSTRUCCIÓN CRÍTICA:
1. Toda tu comunicación y respuestas deben estar en Español (español).
2. Tienes acceso completo al contenido actual de su base de conocimientos OKF local que se incluye a continuación.
3. Responde a las preguntas basándote en este contexto. Si el usuario te pide redactar una nueva nota o concepto, devuélvela con el formato OKF v0.1 válido (con frontmatter YAML delimitado por `---` que contenga `type`, `title`, `description`, `tags` y `timestamp`).

Aquí está el contexto de la base de conocimientos OKF actual:
---
{context_data}
---
"""

    data = {
        "contents": history,
        "systemInstruction": {
            "parts": [{"text": system_instruction}]
        }
    }
    
    req_body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=req_body, headers=headers, method="POST")
    
    try:
        context = ssl._create_unverified_context()
    except Exception:
        context = None
        
    try:
        with urllib.request.urlopen(req, context=context) as response:
            res_body = response.read().decode("utf-8")
            res_json = json.loads(res_body)
            text = res_json['candidates'][0]['content']['parts'][0]['text']
            return text
    except urllib.error.HTTPError as e:
        err_content = e.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Gemini Chat API request failed (HTTP {e.code}): {err_content}")
    except Exception as e:
        raise RuntimeError(f"Failed to communicate with Gemini Chat API: {e}")
