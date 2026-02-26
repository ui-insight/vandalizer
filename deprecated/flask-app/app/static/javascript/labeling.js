document.addEventListener('DOMContentLoaded', () => {
    const app = document.getElementById('labeling-app');
    const recordingId = app.dataset.recordingId;

    // State
    let steps = [];
    let labels = {}; // stepIndex -> string
    let variables = {}; // stepIndex -> boolean (isVariable)

    // Load data
    fetch(`/api/recording/${recordingId}`)
        .then(response => response.json())
        .then(data => {
            steps = data.steps;
            renderSteps();
        })
        .catch(err => {
            document.getElementById('steps-container').innerHTML =
                `<div class="alert alert-danger">Error loading recording: ${err.message}</div>`;
        });

    function renderSteps() {
        const container = document.getElementById('steps-container');
        container.innerHTML = '';
        document.getElementById('step-count').textContent = steps.length;

        steps.forEach((step, index) => {
            const card = document.createElement('div');
            card.className = 'step-card';

            // Determine badge class
            let badgeClass = 'step-badge';
            if (step.type === 'click') badgeClass += ' step-type-click';
            else if (step.type === 'fill_form') badgeClass += ' step-type-fill_form';
            else if (step.type === 'navigate') badgeClass += ' step-type-navigate';

            card.innerHTML = `
                <div class="step-header">
                    <div>
                        <span class="step-index">#${index + 1}</span>
                        <span class="${badgeClass}">${step.type}</span>
                    </div>
                    <div class="text-muted small">${new Date(step.timestamp).toLocaleTimeString()}</div>
                </div>
                <div class="step-body">
                    <div class="form-group">
                        <label>Original Description</label>
                        <div class="text-muted small">${step.description}</div>
                        <div class="small"><a href="${step.url}" target="_blank" class="text-truncate d-block" style="max-width: 400px;">${step.url}</a></div>
                    </div>
                    
                    <div class="form-group">
                        <label>Target Description (Locator)</label>
                        <input type="text" class="form-control" 
                               value="${step.target && step.target.strategies && step.target.strategies[0] ? step.target.strategies[0].description : 'No target'}" readonly disabled>
                    </div>

                    <div class="form-group">
                        <label>Step Name / Intent (Editable)</label>
                        <input type="text" class="form-control step-label-input" 
                               data-index="${index}" 
                               value="${labels[index] || step.description}"
                               placeholder="e.g. Click Submit Button">
                    </div>

                    ${step.type === 'fill_form' ? `
                    <div class="form-check">
                        <input class="form-check-input variable-check" type="checkbox" id="var-${index}" data-index="${index}" ${step.is_sensitive ? 'checked' : ''}>
                        <label class="form-check-label" for="var-${index}">
                            Treat "${step.value}" as a variable?
                        </label>
                    </div>
                    ` : ''}
                </div>
            `;
            container.appendChild(card);
        });

        // Attach listeners
        document.querySelectorAll('.step-label-input').forEach(input => {
            input.addEventListener('input', (e) => {
                labels[e.target.dataset.index] = e.target.value;
            });
        });

        document.querySelectorAll('.variable-check').forEach(check => {
            check.addEventListener('change', (e) => {
                variables[e.target.dataset.index] = e.target.checked;
            });
        });
    }

    document.getElementById('save-workflow-btn').addEventListener('click', () => {
        const name = document.getElementById('workflow-name').value;
        const desc = document.getElementById('workflow-desc').value;

        if (!name) {
            alert('Please enter a workflow name');
            return;
        }

        const workflow = {
            name: name,
            description: desc,
            steps: steps.map((step, index) => {
                // Construct basic step
                const newStep = {
                    step_id: `step_${index + 1}`,
                    step_type: step.type,
                    description: labels[index] || step.description,
                    target: step.target,
                    url: step.url
                };

                // Type specific fields
                if (step.type === 'fill_form') {
                    if (variables[index] || step.is_sensitive) {
                        // Create variable name from label
                        const label = labels[index] || step.description;
                        const varName = label.toLowerCase().replace(/[^a-z0-9]/g, '_');
                        newStep.value = `{{${varName}}}`;
                        // We might want to register this variable somewhere
                    } else {
                        newStep.value = step.value;
                    }
                }
                else if (step.type === 'select') {
                    newStep.option = step.option;
                    newStep.value = step.value;
                }

                return newStep;
            })
        };

        // Send to backend
        fetch('/workflows/create_from_recording', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                recording_id: recordingId,
                workflow: workflow
            })
        })
            .then(r => r.json())
            .then(data => {
                alert('Workflow created successfully!');
                // Redirect to workflow edit or list
                window.location.href = '/workflows';
            })
            .catch(err => {
                alert('Error creating workflow: ' + err.message);
            });
    });
});
