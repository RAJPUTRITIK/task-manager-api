"""Input validation for task data and list filters.

Everything that comes from outside (HTTP body, query string, CLI) is
validated here, so the rest of the code can trust its input.
"""

from datetime import date, datetime

from .models import DATE_FORMAT, PRIORITIES, STATUSES

MAX_TITLE_LENGTH = 100
MAX_DESCRIPTION_LENGTH = 1000
DEFAULT_LIMIT = 50
MAX_LIMIT = 100

TASK_FIELDS = ("title", "description", "status", "priority", "due_date")
SORT_FIELDS = ("id", "created_at", "due_date", "priority", "title")
FILTER_KEYS = (
    "status", "priority", "search", "overdue",
    "due_before", "due_after", "sort_by", "order", "limit", "offset",
)


class ValidationError(Exception):
    """Raised when input data is invalid. Holds one or more messages."""

    def __init__(self, errors):
        if isinstance(errors, str):
            errors = [errors]
        self.errors = list(errors)
        super().__init__("; ".join(self.errors))


# Single-field cleaners. Each returns the cleaned value or raises ValueError.

def parse_date(value, field):
    """Parse a YYYY-MM-DD string into a date object."""
    if not isinstance(value, str):
        raise ValueError("'%s' must be a string in YYYY-MM-DD format" % field)
    try:
        return datetime.strptime(value.strip(), DATE_FORMAT).date()
    except ValueError:
        raise ValueError(
            "'%s' must be a valid date in YYYY-MM-DD format" % field)


def _clean_title(value):
    if not isinstance(value, str):
        raise ValueError("'title' must be a string")
    value = value.strip()
    if not value:
        raise ValueError("'title' must not be empty")
    if len(value) > MAX_TITLE_LENGTH:
        raise ValueError(
            "'title' must be at most %d characters" % MAX_TITLE_LENGTH)
    return value


def _clean_description(value):
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError("'description' must be a string")
    value = value.strip()
    if len(value) > MAX_DESCRIPTION_LENGTH:
        raise ValueError(
            "'description' must be at most %d characters"
            % MAX_DESCRIPTION_LENGTH)
    return value


def _choice_cleaner(field, choices):
    def clean(value):
        if not isinstance(value, str) or value.strip().lower() not in choices:
            raise ValueError(
                "'%s' must be one of: %s" % (field, ", ".join(choices)))
        return value.strip().lower()
    return clean


def _clean_due_date(value):
    if value is None:
        return None
    return parse_date(value, "due_date").isoformat()


_CLEANERS = {
    "title": _clean_title,
    "description": _clean_description,
    "status": _choice_cleaner("status", STATUSES),
    "priority": _choice_cleaner("priority", PRIORITIES),
    "due_date": _clean_due_date,
}


# Public validators

def validate_task_data(data, partial=False, creating=False, today=None):
    """Validate a task payload and return a cleaned dictionary.

    partial:  only validate the keys that are present (PATCH semantics).
    creating: additionally reject due dates that are already in the past.
    """
    if not isinstance(data, dict):
        raise ValidationError("Request body must be a JSON object")

    errors = []
    unknown = sorted(set(data) - set(TASK_FIELDS))
    if unknown:
        errors.append("Unknown field(s): %s" % ", ".join(unknown))

    if not partial and "title" not in data:
        errors.append("'title' is required")

    cleaned = {}
    for field in TASK_FIELDS:
        if field not in data:
            continue
        try:
            cleaned[field] = _CLEANERS[field](data[field])
        except ValueError as exc:
            errors.append(str(exc))

    if creating and cleaned.get("due_date"):
        today = today or date.today()
        if cleaned["due_date"] < today.isoformat():
            errors.append("'due_date' cannot be in the past")

    if errors:
        raise ValidationError(errors)
    return cleaned


def _parse_bool(value, field):
    lowered = value.strip().lower()
    if lowered in ("true", "1", "yes"):
        return True
    if lowered in ("false", "0", "no"):
        return False
    raise ValueError("'%s' must be true or false" % field)


def _parse_int(value, field, minimum, maximum=None):
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValueError("'%s' must be an integer" % field)
    if number < minimum or (maximum is not None and number > maximum):
        raise ValueError("'%s' must be between %d and %s" % (
            field, minimum, maximum if maximum is not None else "infinity"))
    return number


def validate_filters(params):
    """Validate list filters (query-string values, all strings)."""
    errors = []
    unknown = sorted(set(params) - set(FILTER_KEYS))
    if unknown:
        errors.append("Unknown filter(s): %s" % ", ".join(unknown))

    filters = {"sort_by": "id", "order": "asc",
               "limit": DEFAULT_LIMIT, "offset": 0}

    def attempt(key, func):
        if key in params:
            try:
                result = func(params[key])
            except ValueError as exc:
                errors.append(str(exc))
                return
            if result is not None:
                filters[key] = result

    attempt("status", _choice_cleaner("status", STATUSES))
    attempt("priority", _choice_cleaner("priority", PRIORITIES))
    attempt("search", lambda v: v.strip() or None)
    attempt("overdue", lambda v: _parse_bool(v, "overdue"))
    attempt("due_before", lambda v: parse_date(v, "due_before").isoformat())
    attempt("due_after", lambda v: parse_date(v, "due_after").isoformat())
    attempt("sort_by", _choice_cleaner("sort_by", SORT_FIELDS))
    attempt("order", _choice_cleaner("order", ("asc", "desc")))
    attempt("limit", lambda v: _parse_int(v, "limit", 1, MAX_LIMIT))
    attempt("offset", lambda v: _parse_int(v, "offset", 0))

    if errors:
        raise ValidationError(errors)
    return filters
