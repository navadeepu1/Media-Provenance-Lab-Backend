from app.explainer import explain, template_explanation, validate_explanation


def payload():
    return {
        "tier": "WEAK_SIGNALS",
        "rule_id": "R2",
        "signals": [{"name": "ELA", "score": 0.4, "reason": "A test signal was observed."}],
        "limitations": ["Synthetic fixture."],
    }


def test_template_is_bounded_and_readable():
    text = template_explanation(payload())
    assert "WEAK_SIGNALS" in text
    assert "Limitations" in text
    assert len(text.split()) <= 120


def test_unknown_number_and_verdict_are_rejected():
    assert validate_explanation("The score is 0.9.", payload()) is not None
    assert validate_explanation("The image is fake.", payload()) is not None


def test_invalid_candidate_falls_back_to_template():
    text, source = explain(payload(), "The score is 999.")
    assert source == "template"
    assert "WEAK_SIGNALS" in text
