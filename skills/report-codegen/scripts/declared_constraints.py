"""Explicit value and grain checks shared by plan review and generated reports."""
from collections.abc import Mapping
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import numbers
import re


RULE_KEYS = {"type", "nullable", "min", "max", "min_from", "max_from", "min_inclusive", "max_inclusive"}
JOIN_VALIDATIONS = {"one_to_one", "one_to_many", "many_to_one", "many_to_many"}
NUMBER = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?")
INTEGER = re.compile(r"[+-]?\d+")
INTEGER_ALIASES = {"INT": "Int32", "INTEGER": "Int32", "INT1": "Int8",
                   "INT SIGNED": "Int32", "INTEGER SIGNED": "Int32", "INT1 SIGNED": "Int8",
                   "INT UNSIGNED": "UInt32", "INTEGER UNSIGNED": "UInt32", "INT1 UNSIGNED": "UInt8"}


def parse_type(name):
    if isinstance(name, str):
        alias = " ".join(name.upper().split())
        alias = re.sub(r"^(INT1|INTEGER|INT)\s*\(\d+\)", lambda match: match[1], alias)
        name = INTEGER_ALIASES.get(alias, name)
    if name in {"String", "Date", "DateTime"}:
        return name, None, None
    if not isinstance(name, str):
        raise ValueError("constraint type must be a supported string")
    integer = re.fullmatch(r"(U?)Int(8|16|32|64|128|256)", name, re.IGNORECASE)
    if integer:
        unsigned, bits = bool(integer[1]), int(integer[2])
        return "integer", 0 if unsigned else -(2 ** (bits - 1)), 2 ** (bits if unsigned else bits - 1) - 1
    decimal = re.fullmatch(r"Decimal\(([1-9]\d?),\s*(\d+)\)", name)
    if decimal and 1 <= int(decimal[1]) <= 76 and 0 <= int(decimal[2]) <= int(decimal[1]):
        return "decimal", int(decimal[1]), int(decimal[2])
    if name in {"Float32", "Float64"}:
        maximum = float.fromhex("0x1.fffffep+127" if name == "Float32" else "0x1.fffffffffffffp+1023")
        return "float", None, Decimal(str(maximum))
    raise ValueError("unsupported constraint type")


def numeric_value(value):
    if isinstance(value, bool) or not isinstance(value, (str, numbers.Real, Decimal)):
        raise ValueError("expected a finite numeric scalar")
    if isinstance(value, str):
        value = value.strip()
        if not NUMBER.fullmatch(value):
            raise ValueError("expected numeric text")
    if isinstance(value, numbers.Real) and not isinstance(value, numbers.Integral):
        value = float(value)
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("expected a finite numeric scalar") from None
    if not result.is_finite():
        raise ValueError("expected a finite numeric scalar")
    return result


def parsed_value(value, type_info):
    kind, first, second = type_info
    if kind == "integer":
        integer = value if isinstance(value, numbers.Integral) and not isinstance(value, bool) else None
        if isinstance(value, str) and INTEGER.fullmatch(value.strip()):
            integer = int(value)
        if integer is not None:
            if first <= integer <= second:
                return integer
            raise ValueError("integer value is outside its declared range")
    if kind in {"integer", "decimal", "float"}:
        number = numeric_value(value)
        if kind == "integer" and (number < first or number > second or number != number.to_integral_value()):
            raise ValueError("integer value is fractional or outside its declared range")
        if kind == "decimal":
            digits, exponent = number.as_tuple().digits, number.as_tuple().exponent
            trailing = 0
            for digit in reversed(digits):
                if digit:
                    break
                trailing += 1
            if number and (number.copy_abs() >= 10 ** (first - second) or max(0, -exponent - trailing) > second):
                raise ValueError("decimal value exceeds declared precision or scale")
        if kind == "float" and number.copy_abs() > second:
            raise ValueError("float value is outside its declared range")
        return number
    if kind == "String":
        if not isinstance(value, str):
            raise ValueError("expected a string")
        return value
    if isinstance(value, str):
        pattern = r"\d{4}-\d{2}-\d{2}" if kind == "Date" else r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.0+)?(?:Z|[+-]\d{2}:\d{2})?"
        if not re.fullmatch(pattern, value):
            raise ValueError("expected an ISO date or whole-second datetime")
        value = date.fromisoformat(value) if kind == "Date" else datetime.fromisoformat(value.replace("Z", "+00:00"))
    if isinstance(value, datetime):
        if value.microsecond or getattr(value, "nanosecond", 0):
            raise ValueError("datetime precision exceeds whole seconds")
        if kind == "Date":
            if value.hour or value.minute or value.second:
                raise ValueError("Date would discard a time component")
            return value.date()
        return value.astimezone(timezone.utc) if value.utcoffset() is not None else value
    if kind == "Date" and isinstance(value, date):
        return value
    raise ValueError("expected a date or datetime scalar")


def parsed_bound(value, type_info):
    if type_info[0] in {"integer", "decimal", "float"}:
        return numeric_value(value)
    return parsed_value(value, type_info)


def validate_declaration(declaration, columns, path, errors):
    """Return parsed rules while collecting data-only declaration errors."""
    if "column_constraints" not in declaration and "unique_by" not in declaration:
        return [], []
    rules = []
    unique = declaration.get("unique_by", [])
    def issue(code, location, message):
        errors.append({"code": code, "path": location, "message": message})
    if "unique_by" in declaration:
        if (not isinstance(unique, list) or not unique or any(not isinstance(name, str) or not name for name in unique)
                or len(set(unique)) != len(unique)):
            issue("invalid_unique_by", path + ".unique_by", "unique_by requires distinct column names")
            unique = []
        elif columns is not None and any(name not in columns for name in unique):
            issue("unknown_constraint_column", path + ".unique_by", "unique_by refers to an undeclared column")
    constraints = declaration.get("column_constraints", {})
    if not isinstance(constraints, Mapping):
        issue("invalid_column_constraints", path + ".column_constraints", "column_constraints must be an object")
        return rules, unique
    for column, rule in constraints.items():
        location = path + ".column_constraints." + str(column)
        before = len(errors)
        if not isinstance(column, str) or not column or (columns is not None and column not in columns):
            issue("unknown_constraint_column", location, "constraint refers to an undeclared column")
        if not isinstance(rule, Mapping) or not rule or set(rule) - RULE_KEYS:
            issue("invalid_column_constraint", location, "constraint requires supported properties")
            continue
        type_info = None
        if "type" in rule:
            try:
                type_info = parse_type(rule["type"])
            except (ValueError, TypeError):
                issue("invalid_constraint_type", location + ".type", "unsupported constraint type")
        for key in ("nullable", "min_inclusive", "max_inclusive"):
            if key in rule and not isinstance(rule[key], bool):
                issue("invalid_constraint_flag", location + "." + key, "constraint flags must be booleans")
        bounds = {}
        for key in ("min", "max"):
            has_bound = key in rule or key + "_from" in rule
            if has_bound and (type_info is None or type_info[0] == "String"):
                issue("invalid_constraint_bound", location + "." + key, "bounds require a numeric or temporal type")
            if key in rule and key + "_from" in rule:
                issue("invalid_constraint_bound", location + "." + key, "choose one literal or runtime bound")
            if key + "_inclusive" in rule and not has_bound:
                issue("invalid_constraint_bound", location + "." + key, "inclusivity requires a bound")
            if key + "_from" in rule:
                value = rule[key + "_from"]
                prefix, _, name = value.partition(".") if isinstance(value, str) else ("", "", "")
                if prefix not in {"params", "time_range"} or not name:
                    issue("invalid_constraint_bound", location + "." + key + "_from", "bound must use params.<key> or time_range.<key>")
            if key in rule and type_info is not None:
                try:
                    bounds[key] = parsed_bound(rule[key], type_info)
                except (ValueError, TypeError, OverflowError):
                    issue("invalid_constraint_bound", location + "." + key, "bound does not match its declared type")
        if len(bounds) == 2:
            try:
                if bounds["min"] > bounds["max"]:
                    issue("invalid_constraint_bound", location, "minimum exceeds maximum")
            except TypeError:
                issue("invalid_constraint_bound", location, "datetime bounds use incompatible time zones")
        if before == len(errors):
            rules.append((column, rule, type_info))
    return rules, unique


def validate_frame(frame, declaration, path, time_range, params):
    """Check explicit constraints without coercing, rounding or copying values."""
    if "column_constraints" not in declaration and "unique_by" not in declaration:
        return
    errors = []
    rules, unique = validate_declaration(declaration, set(frame.columns), path, errors)
    if errors:
        raise ValueError(errors[0]["path"] + ": " + errors[0]["message"])
    if frame.columns.duplicated().any():
        raise ValueError(path + ": duplicate dataframe columns are ambiguous")
    for column, rule, type_info in rules:
        series = frame[column]
        missing = series.isna()
        if rule.get("nullable") is False and missing.any():
            raise ValueError(path + "." + column + ": null values violate nullable=false")
        bounds = {}
        try:
            for key in ("min", "max"):
                if key in rule:
                    bounds[key] = parsed_bound(rule[key], type_info)
                elif key + "_from" in rule:
                    prefix, _, name = rule[key + "_from"].partition(".")
                    values = params if prefix == "params" else time_range
                    bounds[key] = parsed_bound(values[name], type_info)
            if len(bounds) == 2 and bounds["min"] > bounds["max"]:
                raise ValueError("minimum exceeds maximum")
        except (KeyError, ValueError, TypeError, OverflowError):
            raise ValueError(path + "." + column + ": invalid or missing declared bounds") from None
        if type_info is not None:
            values = series[~missing]
            if type_info[0] == "integer" and series.dtype.kind in {"i", "u"}:
                values = [] if values.empty else [int(values.min()), int(values.max())]
            for value in values:
                try:
                    parsed = parsed_value(value, type_info)
                    if "min" in bounds and (parsed < bounds["min"] or (parsed == bounds["min"] and rule.get("min_inclusive") is False)):
                        raise ValueError("below minimum")
                    if "max" in bounds and (parsed > bounds["max"] or (parsed == bounds["max"] and rule.get("max_inclusive") is False)):
                        raise ValueError("above maximum")
                except (ValueError, TypeError, OverflowError):
                    raise ValueError(path + "." + column + ": value violates its declared type, precision or bounds") from None
    if unique and frame.duplicated(subset=unique).any():
        raise ValueError(path + ": duplicate rows violate unique_by")
