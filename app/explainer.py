import re
from collections.abc import Mapping

FORBIDDEN_VERDICT_TERMS = re.compile(r"\b(fake|real|authentic)\b", re.IGNORECASE)
NUMBER = re.compile(r"\b(?:\d+(?:\.\d+)?)\b")


def template_explanation(input_data: Mapping) -> str:
    signals = input_data.get("signals", [])
    sentences = [
        f"The evidence tier is {input_data.get('tier', 'INCONCLUSIVE')} under rule {input_data.get('rule_id', 'R3')}."
    ]
    for signal in signals:
        sentences.append(f"{signal['name']}: {signal['reason']}")
    limitations = input_data.get("limitations", [])
    if limitations:
        sentences.append("Limitations: " + " ".join(str(item) for item in limitations[:3]))
    return " ".join(sentences)[:1200]


def validate_explanation(text: str, input_data: Mapping) -> str | None:
    if not text or len(text.split()) > 120:
        return "The explanation must contain between one and 120 words."
    if FORBIDDEN_VERDICT_TERMS.search(text):
        return "The explanation contains a forbidden verdict term."
    rule_id = str(input_data.get("rule_id", ""))
    allowed_numbers = {rule_id, *NUMBER.findall(rule_id)}
    for signal in input_data.get("signals", []):
        if signal.get("score") is not None:
            allowed_numbers.add(str(signal["score"]))
    for number in NUMBER.findall(text):
        if number not in allowed_numbers:
            return f"The explanation contains an unapproved number: {number}."
    allowed_names = {str(signal.get("name")) for signal in input_data.get("signals", [])}
    for word in re.findall(r"\b[A-Z][A-Za-z -]{2,}\b", text):
        if word.split(":")[0].strip() in {"ELA", "Limitations"}:
            continue
        if word.rstrip(".") in allowed_names:
            continue
    return None


def explain(input_data: Mapping, candidate: str | None = None) -> tuple[str, str]:
    text = candidate or template_explanation(input_data)
    if validate_explanation(text, input_data) is None:
        return text, "ai" if candidate else "template"
    return template_explanation(input_data), "template"
