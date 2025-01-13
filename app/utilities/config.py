#!/usr/bin/env python3

# the model type to use, either openai or insight server (ollama)
# model_type = "insight"
model_type = "openai"

# 128K is the max context length for the GPT-4o model
# we use less than this to be safe
# max_context_length = 16 * 1024  # 16k tokens

max_context_length = 90 * 1024  # 90k tokens
