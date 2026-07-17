"""Password policy contract: min length + character-class rules (S-first-run-auth)."""

from src.domain.password_policy import validate


class TestPasswordPolicy:
    def test_compliant_password_returns_no_violations(self) -> None:
        assert validate("Str0ng!Passw0rd") == []

    def test_too_short_reports_min_length(self) -> None:
        violations = validate("Sh0rt!a")

        assert "min_length" in violations

    def test_missing_uppercase_reports_rule(self) -> None:
        violations = validate("weakpassword1!")

        assert "uppercase" in violations
        assert "min_length" not in violations

    def test_missing_lowercase_reports_rule(self) -> None:
        violations = validate("WEAKPASSWORD1!")

        assert "lowercase" in violations

    def test_missing_digit_reports_rule(self) -> None:
        violations = validate("WeakPassword!")

        assert "digit" in violations

    def test_missing_special_reports_rule(self) -> None:
        violations = validate("WeakPassword1")

        assert "special" in violations

    def test_multiple_unmet_rules_all_reported(self) -> None:
        violations = validate("weak")

        assert set(violations) == {"min_length", "uppercase", "digit", "special"}

    def test_empty_password_reports_all_rules(self) -> None:
        violations = validate("")

        assert set(violations) == {"min_length", "uppercase", "lowercase", "digit", "special"}
