
import unittest
from unittest.mock import MagicMock
import sys
import types
import os

def test_settings_persistence():
    # Create a dummy module for routes
    routes = types.ModuleType('routes')
    
    # Setup global mocks in the routes module namespace
    routes.Blueprint = MagicMock()
    routes.abort = MagicMock()
    routes.current_app = MagicMock()
    routes.jsonify = lambda x: (x, 200) # Simple mock
    routes.make_response = MagicMock()
    routes.redirect = MagicMock()
    routes.render_template = MagicMock()
    routes.request = MagicMock()
    routes.send_file = MagicMock()
    routes.url_for = MagicMock()
    routes.ResponseReturnValue = MagicMock()
    routes.current_user = MagicMock()
    routes.login_required = lambda f: f
    routes.escape = MagicMock()
    routes.PdfReader = MagicMock()
    routes.PdfWriter = MagicMock()
    routes.secure_filename = MagicMock()
    routes.validate_json_request = MagicMock()
    routes.save_excel_to_html = MagicMock()
    routes.activity_finish = MagicMock()
    routes.activity_start = MagicMock()
    routes.ChatManager = MagicMock()
    routes.get_user_model_name = MagicMock()
    routes.reconcile_user_model_config = MagicMock()
    routes.resolve_model_name = MagicMock()
    routes.ExtractionManagerNonTyped = MagicMock()
    routes.ingest_extraction_recommendation_task = MagicMock()
    routes.normalize_results = MagicMock()
    routes.perform_extraction_task = MagicMock()
    routes._get_or_create_personal_library = MagicMock()
    routes.add_object_to_library = MagicMock()
    routes.build_changes = MagicMock()
    routes.history_for = MagicMock()
    routes.log_edit_history = MagicMock()
    routes.user_can_modify_verified = MagicMock()
    routes.app = MagicMock()
    routes.debug = MagicMock()
    routes.deepcopy = MagicMock(side_effect=lambda x: x) # Mock deepcopy to return same
    routes.pypandoc = MagicMock()
    
    # Mock Models
    routes.ActivityType = MagicMock()
    routes.SearchSet = MagicMock()
    routes.SearchSetItem = MagicMock()
    routes.SmartDocument = MagicMock()
    routes.User = MagicMock()
    
    # helper for _can_edit_search_set
    routes.user_can_modify_verified.return_value = True

    # Read source
    with open('app/blueprints/tasks/routes.py', 'r') as f:
        source = f.read()
    
    # Execute source in the routes module dict
    # We need to handle relative imports if any.
    # The file has: from app.utilities.security import validate_json_request ...
    # These will fail if sys.modules doesn't have them.
    
    sys.modules['app.utilities.security'] = MagicMock()
    sys.modules['app.models'] = MagicMock()
    sys.modules['app.utilities.document_helpers'] = MagicMock()
    sys.modules['app.utilities.analytics_helper'] = MagicMock()
    sys.modules['app.utilities.chat_manager'] = MagicMock()
    sys.modules['app.utilities.config'] = MagicMock()
    sys.modules['app.utilities.extraction_manager_nontyped'] = MagicMock()
    sys.modules['app.utilities.extraction_tasks'] = MagicMock()
    sys.modules['app.utilities.library_helpers'] = MagicMock()
    sys.modules['app.utilities.edit_history'] = MagicMock()
    sys.modules['app.utilities.verification_helpers'] = MagicMock()
    sys.modules['pypandoc'] = MagicMock()
    sys.modules['pypdf'] = MagicMock()
    sys.modules['devtools'] = MagicMock()
    sys.modules['flask.typing'] = MagicMock()
    sys.modules['markupsafe'] = MagicMock()
    sys.modules['werkzeug'] = MagicMock()
    sys.modules['werkzeug.utils'] = MagicMock()
    
    # Execute
    exec(source, routes.__dict__)
    
    # Now interact with the loaded functions
    
    # Setup Mock SearchSet
    mock_search_set = MagicMock()
    mock_search_set.uuid = "test_uuid"
    mock_search_set.extraction_config = {}
    
    def save_side_effect():
        pass
    mock_search_set.save.side_effect = save_side_effect
    
    routes.SearchSet.objects.return_value.first.return_value = mock_search_set
    
    # Mock request payload
    test_config = {"mode": "one_pass", "one_pass": {"thinking": True}}
    routes.request.get_json.return_value = {
        "extraction_uuid": "test_uuid",
        "config": test_config
    }
    
    # Ensure _can_edit_search_set returns True
    # The function _can_edit_search_set uses user_can_modify_verified which we mocked
    
    print("Calling update_extraction_config...")
    response = routes.update_extraction_config()
    
    # Assertions
    print(f"Extraction config on object: {mock_search_set.extraction_config}")
    
    if mock_search_set.extraction_config == test_config:
        print("SUCCESS: Config persisted in backend logic.")
    else:
        print(f"FAILURE: Config mismatch. Expected {test_config}, got {mock_search_set.extraction_config}")

if __name__ == "__main__":
    test_settings_persistence()
