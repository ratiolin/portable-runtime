from portable_runtime.public_contracts.vectors import load_vectors, verify_experience_vectors


def test_experience_vector_family_is_complete() -> None:
    document = load_vectors()
    vectors = document["vectors"]
    ids = {vector["id"] for vector in vectors}
    assert ids == {
        "EU-001", "EU-002", "EU-003", "EU-004", "EU-005", "EU-006", "EU-007", "EU-008",
        "HU-001", "HU-002", "HU-003", "HU-004", "HU-005", "HU-006",
    }
    assert all(vector.get("contract") for vector in vectors)
    assert all("expect" in vector for vector in vectors)
    assert all("forbidden" in vector for vector in vectors)


def test_python_oracle_matches_identity_critical_canonicalization_vectors() -> None:
    assert verify_experience_vectors() == ["EU-001", "EU-002"]


def test_unicode_digest_vector_is_exact() -> None:
    document = load_vectors()
    vector = next(value for value in document["vectors"] if value["id"] == "EU-002")
    assert vector["given"]["use_context"] == {"语言": "中文", "地点": "東京"}
    assert vector["expect"]["sha256"] == "3c1ed9883f948d54347e975daeb87cb148c3cac2aa74800a37c50538c10a0196"
    assert "\\u6771\\u4eac" in vector["expect"]["canonical_json"]
