#!/usr/bin/env python3
import asyncio
import nest_asyncio
from functools import wraps


def function_event_loop_decorator():
    @wraps
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                nest_asyncio.apply(loop)

            return func(*args, **kwargs)

        return wrapper

    return decorator


def class_method_event_loop_decorator():
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            # Set up event loop for this thread
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                nest_asyncio.apply(loop)

            return func(self, *args, **kwargs)

        return wrapper

    return decorator
