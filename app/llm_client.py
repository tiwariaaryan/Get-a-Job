import os
import json
import requests
from typing import Optional, List, Dict, Any

# Load environment variables from .env
ENV_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env"))
if os.path.exists(ENV_PATH):
    with open(ENV_PATH, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip()

# Model Hierarchy: 3.5 Main -> 3.5-lite -> 2.5-flash fallback
MODEL_HIERARCHY = [
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-2.5-flash"
]

class GeminiClient:
    """Gemini client with dedicated per-agent keys and clean fallback handling."""

    def __init__(self, agent_role: str = "general", default_model: str = "gemini-3.5-flash"):
        self.agent_role = agent_role
        self.default_model = os.getenv("DEFAULT_MODEL", default_model)
        self.api_keys = self._get_keys_for_role(agent_role)
        self.current_key_index = 0

    def _get_keys_for_role(self, role: str) -> List[str]:
        primary_key_map = {
            "linkedin": os.getenv("LINKEDIN_AGENT_API_KEY"),
            "resume": os.getenv("RESUME_AGENT_API_KEY"),
            "email": os.getenv("EMAIL_AGENT_API_KEY"),
            "general": os.getenv("BACKUP_API_KEY")
        }
        
        keys = []
        pri = primary_key_map.get(role)
        if pri:
            keys.append(pri)
            
        all_env_keys = [
            os.getenv("BACKUP_API_KEY"),
            os.getenv("EMAIL_AGENT_API_KEY"),
            os.getenv("RESUME_AGENT_API_KEY"),
            os.getenv("LINKEDIN_AGENT_API_KEY"),
            os.getenv("GEMINI_API_KEY")
        ]
        for k in all_env_keys:
            if k and k not in keys:
                keys.append(k)
        return keys

    def generate_text(self, prompt: str, model: Optional[str] = None, system_instruction: Optional[str] = None) -> str:
        """Generate text with automatic model hierarchy fallback."""
        requested_model = model or self.default_model
        
        models_to_try = [requested_model]
        for m in MODEL_HIERARCHY:
            if m not in models_to_try:
                models_to_try.append(m)

        last_error = ""
        total_keys = len(self.api_keys)

        for current_model in models_to_try:
            for attempt in range(total_keys):
                api_key = self.api_keys[self.current_key_index]
                try:
                    res = self._call_api(prompt, api_key, current_model, system_instruction)
                    if res:
                        return res
                except Exception as e:
                    err_msg = str(e)
                    last_error = err_msg

                    # If Google model is busy/overloaded (503) or times out, immediately try next model
                    if "503" in err_msg or "overloaded" in err_msg.lower():
                        print(f"[{self.agent_role.title()} Agent] {current_model} is temporarily overloaded at Google (503). Switching to fallback model...")
                        break
                    
                    # For rate limit (429) or key quota, rotate to next key
                    if "429" in err_msg or "quota" in err_msg.lower():
                        print(f"[{self.agent_role.title()} Agent] Quota limit on key. Rotating to next key...")
                        self.current_key_index = (self.current_key_index + 1) % total_keys
                    else:
                        self.current_key_index = (self.current_key_index + 1) % total_keys

        raise RuntimeError(f"All models and API keys failed for {self.agent_role} agent. Last error: {last_error}")

    def _call_api(self, prompt: str, api_key: str, model: str, system_instruction: Optional[str] = None) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        
        contents = [{"parts": [{"text": prompt}]}]
        body: Dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": 0.3,
                "maxOutputTokens": 2048
            }
        }
        if system_instruction:
            body["systemInstruction"] = {
                "parts": [{"text": system_instruction}]
            }

        headers = {"Content-Type": "application/json"}
        resp = requests.post(url, json=body, headers=headers, timeout=14)
        
        if resp.status_code != 200:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text}")

        data = resp.json()
        candidates = data.get("candidates", [])
        if not candidates:
            return ""
        
        parts = candidates[0].get("content", {}).get("parts", [])
        if parts:
            return parts[0].get("text", "").strip()
        return ""

    def generate_json(self, prompt: str, model: Optional[str] = None, system_instruction: Optional[str] = None) -> Dict[str, Any]:
        """Generate structured JSON response."""
        full_prompt = (
            f"{prompt}\n\n"
            f"IMPORTANT: Output ONLY valid JSON without markdown fences (no ```json or ```). "
            f"Do not include any conversational filler."
        )
        raw = self.generate_text(full_prompt, model=model, system_instruction=system_instruction)
        
        clean = raw.strip()
        if clean.startswith("```json"):
            clean = clean[7:]
        elif clean.startswith("```"):
            clean = clean[3:]
        if clean.endswith("```"):
            clean = clean[:-3]
        clean = clean.strip()
        
        try:
            return json.loads(clean)
        except Exception:
            start = clean.find("{")
            end = clean.rfind("}")
            if start != -1 and end != -1:
                return json.loads(clean[start:end+1])
            raise ValueError(f"Failed to parse JSON from LLM: {raw[:150]}...")
