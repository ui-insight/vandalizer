
import unittest
from unittest.mock import MagicMock
import sys
import types
import os

# Helper to create mock module/package
def mock_module(name, pkg=False):
    m = types.ModuleType(name)
    if pkg:
        m.__path__ = []
    return m

def setup_mocks():
    # Clear existing if necessary, though we assume fresh run or overwrite
    
    # Mock 'app' package
    app = mock_module('app', pkg=True)
    sys.modules['app'] = app
    
    # app.models
    app_models = mock_module('app.models')
    app_models.ActivityType = MagicMock()
    app_models.SearchSet = MagicMock()
    app_models.SearchSetItem = MagicMock()
    app_models.SmartDocument = MagicMock()
    app_models.User = MagicMock()
    sys.modules['app.models'] = app_models
    
    # app.utilities package
    app_utilities = mock_module('app.utilities', pkg=True)
    sys.modules['app.utilities'] = app_utilities
    
    # app.utilities submodules
    sys.modules['app.utilities.security'] = MagicMock()
    sys.modules['app.utilities.document_helpers'] = MagicMock()
    sys.modules['app.utilities.analytics_helper'] = MagicMock()
    sys.modules['app.utilities.chat_manager'] = MagicMock()
    sys.modules['app.utilities.config'] = MagicMock()
    sys.modules['app.utilities.extraction_manager_nontyped'] = MagicMock()
    sys.modules['app.utilities.extraction_tasks'] = MagicMock()
    sys.modules['app.utilities.library_helpers'] = MagicMock()
    sys.modules['app.utilities.edit_history'] = MagicMock()
    sys.modules['app.utilities.verification_helpers'] = MagicMock()
    
    # flask package
    flask = mock_module('flask', pkg=True)
    
    # Setup Blueprint to support route decorator pass-through
    tasks_bp_mock = MagicMock()
    def route_decorator(*args, **kwargs):
        def wrapper(f):
            return f
        return wrapper
    tasks_bp_mock.route.side_effect = route_decorator
    
    flask.Blueprint = MagicMock(return_value=tasks_bp_mock)
    
    flask.abort = MagicMock()
    flask.current_app = MagicMock()
    flask.jsonify = lambda x: (x, 200) # Simple mock for debugging
    flask.make_response = MagicMock()
    flask.redirect = MagicMock()
    flask.render_template = MagicMock()
    flask.request = MagicMock()
    flask.send_file = MagicMock()
    flask.url_for = MagicMock()
    sys.modules['flask'] = flask
    
    # flask.typing
    flask_typing = mock_module('flask.typing')
    flask_typing.ResponseReturnValue = MagicMock()
    sys.modules['flask.typing'] = flask_typing
    
    # flask_login
    sys.modules['flask_login'] = MagicMock()
    
    # markupsafe
    sys.modules['markupsafe'] = MagicMock()
    
    # werkzeug and werkzeug.utils
    werkzeug = mock_module('werkzeug', pkg=True)
    sys.modules['werkzeug'] = werkzeug
    sys.modules['werkzeug.utils'] = MagicMock()
    
    # pypandoc, pypdf, devtools
    sys.modules['pypandoc'] = MagicMock()
    sys.modules['pypdf'] = MagicMock()
    sys.modules['devtools'] = MagicMock()

def test_settings_persistence():
    setup_mocks()
    
    # Create the routes module explicitly
    routes = types.ModuleType('routes')
    
    # Need to mock globals that might be missing if imports fail, 
    # but we hope importing works now.
    
    # Read and exec
    with open('app/blueprints/tasks/routes.py', 'r') as f:
        source = f.read()
    
    try:
        exec(source, routes.__dict__)
    except Exception as e:
        print(f"Exec failed: {e}")
        # Print imported modules to debug
        # print(sys.modules.keys())
        raise e

    # Setup Test Data
    mock_search_set = MagicMock()
    mock_search_set.uuid = "test_uuid"
    mock_search_set.extraction_config = {}
    
    def save_side_effect():
        pass
    mock_search_set.save.side_effect = save_side_effect
    
    routes.SearchSet.objects.return_value.first.return_value = mock_search_set
    
    test_config = {"mode": "one_pass", "one_pass": {"thinking": True}}
    routes.request.get_json.return_value = {
        "extraction_uuid": "test_uuid",
        "config": test_config
    }
    
    # Mock permission check
    # Check if _can_edit_search_set exists or if we need to mock user_can_modify_verified
    routes.user_can_modify_verified = MagicMock(return_value=True) # Ensure this is used
    
    # We also need to mock `_active_user_or_none` or `current_user` behavior if logic uses it.
    routes._active_user_or_none = MagicMock()

    print("Calling update_extraction_config...")
    try:
        # We need to bypass login_required decorator if it wasn't mocked properly.
        # But we mocked flask_login, so login_required is a MagicMock. 
        # A MagicMock called as a decorator returns a MagicMock.
        # So update_extraction_config is a MagicMock.
        # This is BAD. We need to unwrap it or mock the decorator to return the function.
        
        # Fixing the decorator mock:
        # Rerun exec with a patched flask_login?
        pass     
    except Exception as e:
        print(f"Call failed: {e}")
        raise e

    # Better approach for decorators:
    # We can inspect the routes dict.
    # If update_extraction_config is a MagicMock, we can't test the code.
    # We need to set sys.modules['flask_login'].login_required = lambda f: f
    
    sys.modules['flask_login'].login_required = lambda f: f
    
    # Re-exec to apply decorator fix
    exec(source, routes.__dict__)
    
    # Re-setup data hooks on the re-executed module
    routes.SearchSet.objects.return_value.first.return_value = mock_search_set
    routes.request.get_json.return_value = {
        "extraction_uuid": "test_uuid",
        "config": test_config
    }
    routes.user_can_modify_verified = MagicMock(return_value=True)

    response = routes.update_extraction_config()
    print(f"Update response: {response}")
    
    print(f"Extraction config on object: {mock_search_set.extraction_config}")
    
    if mock_search_set.extraction_config == test_config:
        print("SUCCESS: Config persisted in backend logic.")
    else:
        print(f"FAILURE: Config mismatch. Expected {test_config}, got {mock_search_set.extraction_config}")

if __name__ == "__main__":
    test_settings_persistence()
