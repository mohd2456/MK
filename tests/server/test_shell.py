"""Tests for the server shell safety utilities."""

from __future__ import annotations

import pytest

from mk.server._shell import safe_quote, validate_calendar, validate_name


class TestValidateName:
    """Tests for validate_name."""

    def test_accepts_simple_alphanumeric(self):
        assert validate_name("mypool", "pool") == "mypool"

    def test_accepts_name_with_dots(self):
        assert validate_name("my.dataset", "dataset") == "my.dataset"

    def test_accepts_name_with_hyphens(self):
        assert validate_name("my-container", "container") == "my-container"

    def test_accepts_name_with_underscores(self):
        assert validate_name("my_service", "service") == "my_service"

    def test_accepts_name_with_at_sign(self):
        assert validate_name("snap@1", "snapshot") == "snap@1"

    def test_accepts_name_with_slashes(self):
        assert validate_name("pool/dataset", "path") == "pool/dataset"

    def test_accepts_device_path(self):
        assert validate_name("/dev/sda", "disk") == "/dev/sda"

    def test_rejects_name_with_spaces(self):
        with pytest.raises(ValueError, match="Invalid"):
            validate_name("my share", "share")

    def test_accepts_numeric_start(self):
        assert validate_name("1pool", "pool") == "1pool"

    def test_rejects_empty_string(self):
        with pytest.raises(ValueError, match="Invalid"):
            validate_name("", "name")

    def test_rejects_semicolon(self):
        with pytest.raises(ValueError, match="Invalid"):
            validate_name("pool;rm -rf /", "pool")

    def test_rejects_pipe(self):
        with pytest.raises(ValueError, match="Invalid"):
            validate_name("pool|cat", "pool")

    def test_rejects_ampersand(self):
        with pytest.raises(ValueError, match="Invalid"):
            validate_name("pool&bg", "pool")

    def test_rejects_dollar(self):
        with pytest.raises(ValueError, match="Invalid"):
            validate_name("$HOME", "path")

    def test_rejects_backtick(self):
        with pytest.raises(ValueError, match="Invalid"):
            validate_name("`whoami`", "name")

    def test_rejects_newline(self):
        with pytest.raises(ValueError, match="Invalid"):
            validate_name("pool\nmalicious", "pool")

    def test_rejects_parentheses(self):
        with pytest.raises(ValueError, match="Invalid"):
            validate_name("$(cmd)", "name")

    def test_rejects_quotes(self):
        with pytest.raises(ValueError, match="Invalid"):
            validate_name("it's", "name")

    def test_rejects_start_with_space(self):
        with pytest.raises(ValueError, match="Invalid"):
            validate_name(" leading", "name")

    def test_rejects_start_with_dot(self):
        with pytest.raises(ValueError, match="Invalid"):
            validate_name(".hidden", "name")

    def test_rejects_start_with_hyphen(self):
        with pytest.raises(ValueError, match="Invalid"):
            validate_name("-flag", "name")

    def test_label_appears_in_error(self):
        with pytest.raises(ValueError, match="pool"):
            validate_name(";bad", "pool")


class TestValidateCalendar:
    """Tests for validate_calendar (systemd OnCalendar / cron expressions)."""

    def test_accepts_common_daily(self):
        assert validate_calendar("*-*-* 02:00:00") == "*-*-* 02:00:00"

    def test_accepts_weekday_prefix(self):
        assert validate_calendar("Mon *-*-* 02:00:00") == "Mon *-*-* 02:00:00"

    def test_accepts_keyword(self):
        assert validate_calendar("daily") == "daily"

    def test_accepts_interval_and_ranges(self):
        assert validate_calendar("Mon..Fri *:0/15") == "Mon..Fri *:0/15"

    def test_rejects_newline_injection(self):
        # The core fix: a newline would let the value inject extra systemd
        # unit directives when written into a timer file.
        with pytest.raises(ValueError, match="Invalid"):
            validate_calendar("*-*-* 02:00:00\n[Service]\nExecStart=/bin/sh")

    def test_rejects_bracket(self):
        with pytest.raises(ValueError, match="Invalid"):
            validate_calendar("[Service]")

    def test_rejects_empty(self):
        with pytest.raises(ValueError, match="Invalid"):
            validate_calendar("")

    def test_rejects_shell_metacharacters(self):
        with pytest.raises(ValueError, match="Invalid"):
            validate_calendar("$(reboot)")


class TestSafeQuote:
    """Tests for safe_quote."""

    def test_simple_string_safe(self):
        # shlex.quote does not add quotes to strings that are already safe
        result = safe_quote("hello")
        assert result == "hello"

    def test_empty_string_quoted(self):
        result = safe_quote("")
        assert result == "''"

    def test_string_with_spaces(self):
        result = safe_quote("hello world")
        assert result == "'hello world'"

    def test_string_with_single_quote_escaped(self):
        result = safe_quote("it's")
        # shlex.quote escapes single quotes
        assert "it" in result
        assert "s" in result
        # The result should be safe to paste into a shell
        assert "'" not in result.strip("'") or "\\'" in result or "'\"'\"'" in result

    def test_string_with_semicolon(self):
        result = safe_quote("a;b")
        assert result == "'a;b'"

    def test_string_with_dollar(self):
        result = safe_quote("$HOME")
        assert result == "'$HOME'"

    def test_string_with_backtick(self):
        result = safe_quote("`whoami`")
        assert result == "'`whoami`'"
