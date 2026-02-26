"""Security utilities for input validation and rate limiting."""

from functools import wraps
from typing import Any, Callable, Type

from flask import abort, jsonify, request
from werkzeug.exceptions import BadRequest


def validate_json_request(required_fields: dict[str, Type] | None = None) -> Callable:
    """
    Decorator to validate that request contains valid JSON data.

    Args:
        required_fields: Dict mapping field names to their expected types.
                        Example: {"uuid": str, "title": str, "count": int}

    Returns:
        Decorated function that validates JSON before execution.

    Example:
        @validate_json_request({"uuid": str, "title": str})
        def my_route():
            data = request.get_json()
            # data is guaranteed to be a dict with uuid and title as strings
    """
    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Check Content-Type
            if not request.is_json:
                return jsonify({"error": "Content-Type must be application/json"}), 400

            try:
                data = request.get_json(force=False)
            except BadRequest:
                return jsonify({"error": "Invalid JSON in request body"}), 400

            # Validate data is a dict
            if not isinstance(data, dict):
                return jsonify({"error": "Request body must be a JSON object"}), 400

            # Validate required fields if specified
            if required_fields:
                errors = []
                for field_name, expected_type in required_fields.items():
                    if field_name not in data:
                        errors.append(f"Missing required field: {field_name}")
                    elif not isinstance(data[field_name], expected_type):
                        errors.append(
                            f"Field '{field_name}' must be of type {expected_type.__name__}, "
                            f"got {type(data[field_name]).__name__}"
                        )

                if errors:
                    return jsonify({"error": "Validation failed", "details": errors}), 400

            return f(*args, **kwargs)
        return wrapper
    return decorator


def validate_request_args(required_args: dict[str, Type] | None = None) -> Callable:
    """
    Decorator to validate URL query parameters.

    Args:
        required_args: Dict mapping parameter names to their expected types.

    Returns:
        Decorated function that validates query parameters before execution.
    """
    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if required_args:
                errors = []
                for arg_name, expected_type in required_args.items():
                    value = request.args.get(arg_name)

                    if value is None:
                        errors.append(f"Missing required parameter: {arg_name}")
                    elif expected_type == int:
                        try:
                            int(value)
                        except (ValueError, TypeError):
                            errors.append(f"Parameter '{arg_name}' must be an integer")
                    elif expected_type == bool:
                        if value.lower() not in ("true", "false", "1", "0"):
                            errors.append(f"Parameter '{arg_name}' must be a boolean")

                if errors:
                    return jsonify({"error": "Validation failed", "details": errors}), 400

            return f(*args, **kwargs)
        return wrapper
    return decorator


def safe_get_document(model_class: Type, **query: Any) -> Any:
    """
    Safely retrieve a document from database with proper error handling.

    Args:
        model_class: The MongoEngine model class to query.
        **query: Query parameters to pass to the model.

    Returns:
        The document if found, otherwise aborts with 404.

    Example:
        doc = safe_get_document(SmartFolder, uuid=folder_uuid, owner_user_id=user.user_id)
    """
    document = model_class.objects(**query).first()
    if document is None:
        abort(404, description=f"{model_class.__name__} not found")
    return document


def validate_string_length(value: Any, field_name: str, max_length: int) -> str:
    """
    Validate that a value is a string and within max length.

    Args:
        value: The value to validate.
        field_name: Name of the field for error messages.
        max_length: Maximum allowed length.

    Returns:
        The validated string value.

    Raises:
        BadRequest: If validation fails.
    """
    if not isinstance(value, str):
        raise BadRequest(f"{field_name} must be a string")

    if len(value) > max_length:
        raise BadRequest(f"{field_name} exceeds maximum length of {max_length} characters")

    if len(value) == 0:
        raise BadRequest(f"{field_name} cannot be empty")

    return value


def sanitize_objectid_input(value: str, field_name: str = "id") -> str:
    """
    Validate that a string looks like a valid MongoDB ObjectId before processing.

    Args:
        value: The string to validate.
        field_name: Name of the field for error messages.

    Returns:
        The validated string if it matches ObjectId format.

    Raises:
        BadRequest: If the string doesn't match ObjectId format.
    """
    import re

    if not isinstance(value, str):
        raise BadRequest(f"{field_name} must be a string")

    # ObjectId must be exactly 24 hexadecimal characters
    if not re.match(r'^[a-fA-F0-9]{24}$', value):
        raise BadRequest(f"{field_name} is not a valid identifier")

    return value
