#!/bin/bash
cd "$(dirname "$0")"
uvicorn app.main:app --reload --port 8001
