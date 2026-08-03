from promptbrief.core.text import redact_secrets, strip_accents, terms


def test_strip_accents_folds_spanish_diacritics():
    assert strip_accents("sección configuración diseño") == "seccion configuracion diseno"


def test_accented_and_unaccented_spellings_produce_the_same_terms():
    assert terms("mejorar la sección") == terms("mejorar la seccion")


def test_terms_keeps_short_technical_tokens():
    assert {"css", "api", "seo"} <= terms("ajustar el CSS del API y el SEO")


def test_terms_drops_tokens_shorter_than_three_characters():
    assert "de" not in terms("el patron de la seccion")


def test_redact_secrets_hides_the_value_and_keeps_the_context():
    text = "Deploy key: STRIPE_KEY=sk_test_EXAMPLEKEYNOTAREALVALUE"
    redacted, found = redact_secrets(text)
    assert found is True
    assert "sk_test_EXAMPLEKEYNOTAREALVALUE" not in redacted
    assert "[REDACTED]" in redacted
    assert "STRIPE_KEY" in redacted


def test_the_labelled_pattern_keeps_the_label_and_drops_the_value():
    # Ejercita la rama del lambda con grupo de captura, que ningún otro patrón usa.
    redacted, found = redact_secrets("API_KEY=abcdefghijklmnop1234")
    assert found is True
    assert redacted == "API_KEY=[REDACTED]"


def test_redact_secrets_catches_common_token_shapes():
    for secret in (
        "ghp_16C7e42F292c6912E7710c838347Ae178B4a",
        "AKIAIOSFODNN7EXAMPLE",
        "xoxb-EXAMPLE-NOT-A-REAL-VALUE",
    ):
        redacted, found = redact_secrets(f"token: {secret}")
        assert found is True, secret
        assert secret not in redacted


def test_redact_secrets_catches_a_connection_string_password():
    redacted, found = redact_secrets("DATABASE_URL=postgres://user:S3cr3tPass@host/db")
    assert found is True
    assert "S3cr3tPass" not in redacted


def test_redact_secrets_catches_a_private_key_block():
    text = (
        "-----BEGIN OPENSSH PRIVATE KEY-----\n"
        "b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAAB\n"
        "-----END OPENSSH PRIVATE KEY-----"
    )
    redacted, found = redact_secrets(text)
    assert found is True
    assert "b3BlbnNzaC1rZXktdjEA" not in redacted


def test_redact_secrets_leaves_ordinary_prose_alone():
    text = "Usar next.config.ts con output export y images.unoptimized"
    redacted, found = redact_secrets(text)
    assert found is False
    assert redacted == text
