from app.domains.reviews.repositorio_resenas import review_spam_flags


def test_review_spam_flags_detects_links_and_repetition():
    flags = review_spam_flags("Compra aqui https://spam.test oferta oferta oferta oferta oferta oferta oferta oferta")

    assert "contains_url" in flags
    assert "repeated_words" in flags


def test_review_spam_flags_allows_normal_comment():
    flags = review_spam_flags("Me funcionó bien durante un mes y el precio fue razonable.")

    assert flags == []


def test_review_spam_flags_detects_medical_claims_and_personal_data():
    flags = review_spam_flags("Esto cura todo, escribeme por whatsapp para duplicar dosis.")

    assert "medical_claim" in flags
    assert "personal_data" in flags
    assert "unsafe_dosing" in flags
