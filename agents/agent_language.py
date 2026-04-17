"""Language instruction helpers for agent system prompts."""


def response_language_instruction(language: str) -> str:
    """Return a language instruction for the system prompt.

    Args:
        language: "de" for German, "en" for English, or other language code

    Returns:
        Instruction string to append to system prompt
    """
    if language == "de":
        return "Antworte auf Deutsch."
    return "Respond in English."


def response_language_with_fixed_codes(language: str, codes: list[str]) -> str:
    """For agents using fixed verdict codes that must not be translated.

    Instructs the LLM to write analysis text in the target language
    while using exact, untranslated verdict codes.

    Args:
        language: "de" for German, "en" for English
        codes: List of verdict codes that must not be translated

    Returns:
        Instruction string combining language + fixed-code requirement
    """
    if language == "de":
        return "Antworte auf Deutsch."
    code_list = ", ".join(f'"{c}"' for c in codes)
    return (
        f"Write all analysis and explanatory text in English. "
        f"IMPORTANT: Use EXACTLY these codes as-is (do NOT translate): {code_list}"
    )
