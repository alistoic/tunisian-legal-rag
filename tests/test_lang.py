from src.lang import detect_lang, looks_like_derja


def test_detect_lang():
    assert detect_lang("Quelle est la durée du travail ?") == "fr"
    assert detect_lang("ما هي مدة العمل؟") == "ar"
    assert detect_lang("La durée du travail ما هي") == "mix"


def test_looks_like_derja():
    assert looks_like_derja("chnowa el chourout lel mariage ?")
    assert looks_like_derja("قداش من يوم عطلة؟")
    assert not looks_like_derja("Quelle est la durée légale du travail ?")
