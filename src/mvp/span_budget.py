"""Pure declared span-budget proxy; independent of retrieval and UI contracts."""
import re

BUDGET_TOKENS = re.compile(r'\w+|[^\w\s]', re.UNICODE)


def budget_token_count(text: str) -> int:
    """Count the declared lexical proxy, never claiming a model-token count."""
    return sum(1 for _ in BUDGET_TOKENS.finditer(text))
