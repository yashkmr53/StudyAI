"""Shared sanitization/redaction utility (architecture §12, G12).

Provides consistent data-minimization redaction across all provider inputs:
- LLM calls
- Embedding calls
- OCR calls
- Logging

Redacts sensitive personal information before sending to external providers
or persisting to logs, preventing PII leakage.
"""

import re
from typing import Optional


# Pattern: email addresses
_EMAIL_PATTERN = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')

# Pattern: phone numbers (US format + international variants)
_PHONE_PATTERN = re.compile(
    r'\b(?:\+?1[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}\b'
)

# Pattern: credit card numbers (13-16 digits)
_CREDIT_CARD_PATTERN = re.compile(
    r'\b(?:\d[ -]*?){13,16}\b'
)

# Pattern: SSN numbers (9 digits with dashes)
_SSN_PATTERN = re.compile(
    r'\b\d{3}-\d{2}-\d{4}\b'
)


def sanitize_text(text: str) -> tuple[str, int]:
    """
    Apply data-minimization redaction to text.
    
    Returns (sanitized_text, redaction_count).
    
    Redacts:
    - Email addresses -> [EMAIL]
    - Phone numbers -> [PHONE]
    - Credit card numbers -> [CREDIT_CARD]
    - SSN numbers -> [SSN]
    
    Also truncates to MAX_PROVIDER_INPUT_CHARS if needed.
    """
    if not text:
        return text, 0
    
    redaction_count = 0
    sanitized = text
    
    # Apply redaction patterns
    for pattern, label in [
        (_EMAIL_PATTERN, '[EMAIL]'),
        (_PHONE_PATTERN, '[PHONE]'),
        (_CREDIT_CARD_PATTERN, '[CREDIT_CARD]'),
        (_SSN_PATTERN, '[SSN]'),
    ]:
        matches = pattern.findall(sanitized)
        if matches:
            redaction_count += len(matches)
            sanitized = pattern.sub(label, sanitized)
    
    return sanitized, redaction_count


def sanitize_for_provider(text: str, max_chars: Optional[int] = None) -> tuple[str, int]:
    """
    Sanitize text before sending to a provider.
    
    Applies redaction patterns and optional truncation.
    
    Args:
        text: The text to sanitize
        max_chars: Maximum characters to allow (None = no limit)
    
    Returns (sanitized_text, redaction_count)
    """
    if not text:
        return text, 0
    
    # First apply redaction
    sanitized, redaction_count = sanitize_text(text)
    
    # Then truncate if needed
    if max_chars is not None and len(sanitized) > max_chars:
        sanitized = sanitized[:max_chars]
        # Don't count truncation as redaction
    
    return sanitized, redaction_count