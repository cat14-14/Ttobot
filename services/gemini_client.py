from __future__ import annotations

import json
from dataclasses import dataclass

import aiohttp


class GeminiError(Exception):
    pass


class GeminiConfigurationError(GeminiError):
    pass


@dataclass(frozen=True)
class CommandPlan:
    status: str
    action: str
    amount: int
    message: str


class GeminiService:
    def __init__(self, api_key: str | None, model: str):
        self.api_key = api_key
        self.model = model

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    async def generate_text(
        self,
        *,
        prompt: str,
        system_instruction: str,
        temperature: float = 0.7,
        max_output_tokens: int = 1024,
    ) -> str:
        payload = {
            "systemInstruction": {
                "parts": [{"text": system_instruction}],
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}],
                }
            ],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_output_tokens,
                "thinkingConfig": {
                    "thinkingBudget": 0,
                },
            },
        }
        return await self._request_text(payload)

    async def generate_json(
        self,
        *,
        prompt: str,
        system_instruction: str,
        response_json_schema: dict[str, object],
        temperature: float = 0.0,
        max_output_tokens: int = 256,
    ) -> dict[str, object]:
        payload = {
            "systemInstruction": {
                "parts": [{"text": system_instruction}],
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}],
                }
            ],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_output_tokens,
                "responseMimeType": "application/json",
                "responseJsonSchema": response_json_schema,
                "thinkingConfig": {
                    "thinkingBudget": 0,
                },
            },
        }
        text = await self._request_text(payload)
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as error:
            raise GeminiError(f"JSON 응답 파싱 실패: {error}") from error

        if not isinstance(parsed, dict):
            raise GeminiError("JSON 응답 형식이 올바르지 않습니다.")

        return parsed

    async def plan_command(
        self,
        *,
        prompt: str,
        system_instruction: str,
    ) -> CommandPlan:
        schema = {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["execute", "clarify", "reject"],
                    "description": "실행 가능 여부",
                },
                "action": {
                    "type": "string",
                    "enum": ["clear", "clear_all", "unsupported"],
                    "description": "지원되는 내부 액션 이름",
                },
                "amount": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 100,
                    "description": "clear 실행 시 삭제할 메시지 개수. 없으면 0",
                },
                "message": {
                    "type": "string",
                    "description": "사용자에게 보여줄 한국어 안내 문구",
                },
            },
            "required": ["status", "action", "amount", "message"],
            "additionalProperties": False,
        }

        data = await self.generate_json(
            prompt=prompt,
            system_instruction=system_instruction,
            response_json_schema=schema,
            temperature=0.0,
            max_output_tokens=200,
        )

        try:
            status = str(data["status"])
            action = str(data["action"])
            amount = int(data["amount"])
            message = str(data["message"])
        except (KeyError, TypeError, ValueError) as error:
            raise GeminiError(f"명령 계획 형식이 올바르지 않습니다: {error}") from error

        return CommandPlan(
            status=status,
            action=action,
            amount=amount,
            message=message,
        )

    async def _request_text(self, payload: dict[str, object]) -> str:
        if not self.api_key:
            raise GeminiConfigurationError("GEMINI_API_KEY가 설정되지 않았습니다.")

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent"
        )
        headers = {
            "x-goog-api-key": self.api_key,
            "Content-Type": "application/json",
        }
        timeout = aiohttp.ClientTimeout(total=45)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, headers=headers, json=payload) as response:
                if response.status >= 400:
                    error_text = await response.text()
                    raise GeminiError(
                        f"Gemini API 요청 실패 ({response.status}): {error_text}"
                    )
                data = await response.json()

        return self._extract_text(data)

    def _extract_text(self, data: dict[str, object]) -> str:
        candidates = data.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            prompt_feedback = data.get("promptFeedback")
            if prompt_feedback:
                raise GeminiError(f"Gemini 응답이 차단되었습니다: {prompt_feedback}")
            raise GeminiError("Gemini 응답 후보가 없습니다.")

        candidate = candidates[0]
        if not isinstance(candidate, dict):
            raise GeminiError("Gemini 응답 형식이 올바르지 않습니다.")

        content = candidate.get("content")
        if not isinstance(content, dict):
            raise GeminiError("Gemini 응답 본문이 없습니다.")

        parts = content.get("parts")
        if not isinstance(parts, list) or not parts:
            raise GeminiError("Gemini 응답 파트가 없습니다.")

        texts: list[str] = []
        for part in parts:
            if isinstance(part, dict):
                text = part.get("text")
                if isinstance(text, str):
                    texts.append(text)

        if not texts:
            raise GeminiError("Gemini 응답 텍스트가 없습니다.")

        return "".join(texts).strip()
