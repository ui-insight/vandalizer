#!/usr/bin/env python3
"""Passive trigger management for workflows. Handles creation and evaluation of trigger events."""

import fnmatch
from datetime import datetime, timedelta
from uuid import uuid4

from app.models import Workflow, WorkflowTriggerEvent, SmartDocument


def create_folder_watch_trigger(workflow, document):
    """
    Create a pending trigger event when a document arrives in a watched folder.
    
    Args:
        workflow: Workflow instance with folder_watch configured
        document: SmartDocument that was just uploaded
        
    Returns:
        WorkflowTriggerEvent instance
    """
    
    folder_watch_config = workflow.input_config.get('folder_watch', {})
    delay_seconds = folder_watch_config.get('delay_seconds', 300)
    
    event = WorkflowTriggerEvent(
        uuid=uuid4().hex,
        workflow=workflow,
        trigger_type='folder_watch',
        status='pending',
        documents=[document],
        document_count=1,
        trigger_context={'folder_id': document.folder},
        created_at=datetime.utcnow(),
        process_after=datetime.utcnow() + timedelta(seconds=delay_seconds)
    )
    event.save()
    return event


def apply_file_filters(documents, file_filters):
    """Filter documents based on type, name patterns, size.
    
    Args:
        documents: List of SmartDocument instances
        file_filters: Dict with 'types' and 'exclude_patterns' keys
        
    Returns:
        Filtered list of documents
    """
    if not file_filters:
        return documents
        
    filtered = []
    for doc in documents:
        # Check file type
        allowed_types = file_filters.get('types', [])
        if allowed_types and doc.extension not in allowed_types:
            continue
            
        # Check exclude patterns
        exclude_patterns = file_filters.get('exclude_patterns', [])
        if any(fnmatch.fnmatch(doc.title, pattern) for pattern in exclude_patterns):
            continue
            
        filtered.append(doc)
    
    return filtered


def evaluate_conditions(documents, conditions):
    """
    Evaluate whether documents meet workflow conditions.
    
    Args:
        documents: List of SmartDocument instances
        conditions: List of condition dicts with 'field', 'operator', 'value'
        
    Returns:
        Boolean indicating if conditions are met
    """
    if not conditions:
        return True
        
    # Simple condition evaluation (can be extended)
    for condition in conditions:
        field = condition.get('field')
        operator = condition.get('operator')
        value = condition.get('value')
        
        # Example: file size check
        if field == 'file_size':
            for doc in documents:
                try:
                    doc_size = doc.absolute_path.stat().st_size
                    if operator == 'less_than' and doc_size >= value:
                        return False
                    elif operator == 'greater_than' and doc_size <= value:
                        return False
                except Exception:
                    # If we can't get file size, skip check
                    pass
    
    return True


def check_workflow_budget(workflow):
    """
    Check if workflow has budget remaining.
    
    Args:
        workflow: Workflow instance
        
    Returns:
        Tuple of (can_run: bool, reason: str|None)
    """
    budget_config = workflow.resource_config.get('budget', {})
    stats = workflow.stats or {}
    
    # Check daily token limit
    daily_limit = budget_config.get('daily_token_limit')
    if daily_limit:
        tokens_used_today = stats.get('tokens_used', 0)  # Note: would need daily reset logic
        if tokens_used_today >= daily_limit:
            return False, 'Daily token limit reached'
    
    # Check monthly token limit
    monthly_limit = budget_config.get('monthly_token_limit')
    if monthly_limit:
        # Note: would need monthly tracking in stats
        pass
    
    return True, None


def check_throttling(workflow):
    """
    Check if workflow can run based on throttling configuration.
    
    Args:
        workflow: Workflow instance
        
    Returns:
        Tuple of (can_run: bool, reason: str|None)
    """
    throttle_config = workflow.resource_config.get('throttling', {})
    stats = workflow.stats or {}
    
    # Check minimum delay between runs
    min_delay = throttle_config.get('min_delay_between_runs', 60)
    last_run_at = stats.get('last_passive_run_at')
    
    if last_run_at:
        if isinstance(last_run_at, str):
            # Handle string datetime
            from dateutil import parser
            last_run_at = parser.parse(last_run_at)
        
        seconds_since_last_run = (datetime.utcnow() - last_run_at).total_seconds()
        if seconds_since_last_run < min_delay:
            return False, f'Throttled: {int(min_delay - seconds_since_last_run)}s remaining'
    
    # Check max concurrent runs (would need to query running events)
    max_concurrent = throttle_config.get('max_concurrent', 3)
    running_count = WorkflowTriggerEvent.objects(
        workflow=workflow,
        status__in=['queued', 'running']
    ).count()
    
    if running_count >= max_concurrent:
        return False, f'Max concurrent runs ({max_concurrent}) reached'
    
    return True, None
