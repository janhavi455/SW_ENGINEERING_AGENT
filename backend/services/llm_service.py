import json
import os
import re
from typing import Dict, Any, Optional, List
import requests
from backend.utils.helpers import load_env_file

load_env_file()


class LLMService:
    """
    Configurable LLM provider service supporting:
    - Gemini API (direct REST / generative API)
    - OpenAI / Groq / OpenRouter / Ollama (OpenAI-compatible chat completions)
    - Resilient fallback parser for JSON responses
    """
    def __init__(
        self,
        api_key: Optional[str] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None
    ):
        self.provider = (provider or os.getenv("LLM_PROVIDER", "gemini")).lower()
        self.api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("OPENAI_API_KEY") or os.getenv("GROQ_API_KEY")
        self.model = model or os.getenv("LLM_MODEL")

        if not self.model:
            if self.provider == "gemini":
                self.model = "gemini-2.5-flash"
            elif self.provider == "groq":
                self.model = "llama-3.3-70b-versatile"
            else:
                self.model = "gpt-4o"

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def generate_text(self, system_prompt: str, user_prompt: str, temperature: float = 0.2) -> str:
        """
        Generate plain text response from the configured LLM.
        """
        if not self.api_key:
            return self._heuristic_fallback(system_prompt, user_prompt)

        try:
            if self.provider == "gemini":
                return self._call_gemini(system_prompt, user_prompt, temperature)
            else:
                return self._call_openai_compatible(system_prompt, user_prompt, temperature)
        except Exception as e:
            # Fall back gracefully with clear message
            return f"LLM Generation Note: API call encountered error ({str(e)}). Using heuristic analysis."

    def generate_json(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        """
        Generate structured JSON response, extracting from code blocks if needed.
        """
        prompt_with_json_instruction = (
            f"{user_prompt}\n\nIMPORTANT: Return ONLY a valid JSON object matching the requested schema. "
            "Do NOT wrap with conversational preamble. Wrap solely in ```json ... ``` or raw JSON."
        )
        response_text = self.generate_text(system_prompt, prompt_with_json_instruction)
        
        parsed = self._extract_json(response_text)
        if parsed is not None:
            return parsed

        return {
            "error": "Failed to parse structured JSON from LLM response.",
            "raw_response": response_text
        }

    def _call_gemini(self, system_prompt: str, user_prompt: str, temperature: float) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "system_instruction": {
                "parts": [{"text": system_prompt}]
            },
            "contents": [
                {
                    "parts": [{"text": user_prompt}]
                }
            ],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": 4096
            }
        }
        res = requests.post(url, headers=headers, json=payload, timeout=60)
        if res.status_code != 200:
            raise RuntimeError(f"Gemini API error ({res.status_code}): {res.text}")
        data = res.json()
        candidates = data.get("candidates", [])
        if candidates and "content" in candidates[0]:
            parts = candidates[0]["content"].get("parts", [])
            if parts and "text" in parts[0]:
                return parts[0]["text"]
        return ""

    def _call_openai_compatible(self, system_prompt: str, user_prompt: str, temperature: float) -> str:
        base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        if self.provider == "groq":
            base_url = "https://api.groq.com/openai/v1"

        url = f"{base_url.rstrip('/')}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": temperature
        }
        res = requests.post(url, headers=headers, json=payload, timeout=60)
        if res.status_code != 200:
            raise RuntimeError(f"OpenAI compatible API error ({res.status_code}): {res.text}")
        data = res.json()
        return data["choices"][0]["message"]["content"]

    def _extract_json(self, text: str) -> Optional[Dict[str, Any]]:
        # Match ```json ... ```
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        # Try raw { ... }
        match = re.search(r"(\{.*\})", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        return None

    def _heuristic_fallback(self, system_prompt: str, user_prompt: str) -> str:
        """
        Deterministic fallback when no LLM API key is provided, enabling full offline testing.
        """
        if "planner" in system_prompt.lower():
            return json.dumps({
                "problem_understanding": "Identified issue requirements from title and description.",
                "root_cause_hypothesis": "The specified functionality is missing or behaving incorrectly in the target repository.",
                "relevant_files": ["app.py", "main.py"],
                "required_modifications": ["Implement requested feature logic", "Add validation checks"],
                "implementation_tasks": [
                    "Locate core module implementation",
                    "Add required functions or fix bug",
                    "Verify against test suite"
                ],
                "expected_behavior": "Feature behaves in accordance with issue requirements.",
                "testing_strategy": "Run existing pytest suite and execute targeted regression tests."
            })
        elif "debugger" in system_prompt.lower():
            return json.dumps({
                "failure_description": "Test assertion failure detected during pytest execution.",
                "root_cause": "Mismatch between actual return value and expected assertion.",
                "affected_files": ["app.py"],
                "proposed_correction": "Update function logic to handle edge cases appropriately.",
                "expected_result": "All test assertions pass."
            })
        elif "reviewer" in system_prompt.lower():
            return json.dumps({
                "approved": True,
                "overall_status": "Approved",
                "issue_resolution_assessment": "The changes directly address the reported issue.",
                "code_quality_assessment": "Clean code adhering to standard conventions.",
                "potential_bugs": [],
                "security_observations": ["No secret leakage", "Input properly handled"],
                "unresolved_concerns": [],
                "recommendation": "Ready to commit and push to user's fork."
            })
        return "Deterministic analysis complete."
