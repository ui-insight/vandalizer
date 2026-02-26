#!/usr/bin/env python3
"""
Migration script to set is_output=True for existing workflow steps
that contain output task types (DocumentRenderer, FormFiller, etc.)
"""

from app import app
from app.models import WorkflowStep

# Output task types that should mark a step as an output step
OUTPUT_TASK_TYPES = {
    "DocumentRenderer",
    "FormFiller", 
    "DataExport",
    "PackageBuilder"
}

def migrate_output_steps():
    """Find all WorkflowSteps with output tasks and set is_output=True"""
    
    print("Finding workflow steps with output tasks...")
    
    updated_count = 0
    
    # Get all workflow steps
    all_steps = WorkflowStep.objects()
    
    for step in all_steps:
        # Check if this step has any output tasks
        has_output_task = False
        
        for task in step.tasks:
            if task.name in OUTPUT_TASK_TYPES:
                has_output_task = True
                break
        
        # If it has an output task but is_output is not True, update it
        if has_output_task and not step.is_output:
            print(f"  Updating step '{step.name}' (ID: {step.id})")
            step.is_output = True
            step.save()
            updated_count += 1
    
    print(f"\n✓ Migration complete! Updated {updated_count} step(s)")
    
    # Show summary
    output_steps = WorkflowStep.objects(is_output=True)
    print(f"  Total output steps in database: {output_steps.count()}")

if __name__ == "__main__":
    with app.app_context():
        migrate_output_steps()
