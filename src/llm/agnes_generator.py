from typing import Dict, List, Optional

from openai import (
    APIConnectionError,
    APIStatusError,
    AuthenticationError,
    OpenAI,
    RateLimitError,
)

from src.settings import settings


class AgnesGenerator:
    """
    Text-generation client for the OpenAI-compatible Agnes AI API.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = settings.agnes_base_url,
        model: str = settings.agnes_model,
    ):
        resolved_api_key = settings.agnes_api_key if api_key is None else api_key

        if not resolved_api_key:
            raise ValueError(
                "AGNES_API_KEY is missing. Add it to the root .env file."
            )

        self.model = model

        self.client = OpenAI(
            api_key=resolved_api_key,
            base_url=base_url,
            timeout=60.0,
            max_retries=2,
        )

    def generate(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = settings.max_tokens,
        temperature: float = settings.temperature,
    ) -> str:
        """
        Send chat messages to Agnes and return the response text.
        """

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )

        except AuthenticationError as exc:
            raise RuntimeError(
                "Agnes authentication failed. Check AGNES_API_KEY."
            ) from exc

        except RateLimitError as exc:
            raise RuntimeError(
                "Agnes rate limit reached. Try again after the limit resets."
            ) from exc

        except APIConnectionError as exc:
            raise RuntimeError(
                "Could not connect to the Agnes API."
            ) from exc

        except APIStatusError as exc:
            raise RuntimeError(
                f"Agnes API returned status {exc.status_code}: "
                f"{exc.message}"
            ) from exc

        if not response.choices:
            raise RuntimeError("Agnes returned no completion choices.")

        choice = response.choices[0]
        if choice.finish_reason == "length":
            raise RuntimeError(
                "Agnes exhausted the completion token budget; the partial answer "
                "was not accepted. Increase max_tokens or reduce retrieved context."
            )
        content = choice.message.content
        if not content or not content.strip():
            raise RuntimeError("Agnes returned an empty response.")
        return content.strip()
