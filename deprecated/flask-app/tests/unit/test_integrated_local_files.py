
import unittest
from unittest.mock import MagicMock, patch
import sys
import types
import json

class MockForm(object):
    def __init__(self, data=None):
        self.data = data or {}
        
    def get(self, k, default=None):
        return self.data.get(k, default)
        
    def getlist(self, k):
        val = self.data.get(k)
        if isinstance(val, list):
            return val
        if val:
            return [val]
        return []


def test_run_integrated_local_files():
    # 1. Mock dependencies in sys.modules
    flask_mock = MagicMock()
    # IMPORTANT: Blueprint.route must be a pass-through decorator
    # When @tasks.route(...) is called, it returns a decorator.
    # That decorator is called with the function. It must return the function.
    def route_decorator(*args, **kwargs):
        def wrapper(f):
            return f
        return wrapper
    
    # Also tasks.route might be called as @tasks.route("/path") -> returns wrapper
    # Flask Blueprints: bp.route("/path")(func)
    mock_blueprint_instance = MagicMock()
    mock_blueprint_instance.route.side_effect = route_decorator
    
    flask_mock.Blueprint.return_value = mock_blueprint_instance
    
    # Configure request mock
    request_mock = MagicMock()
    flask_mock.request = request_mock
    
    sys.modules['flask'] = flask_mock
    
    # Other mocks
    sys.modules['app'] = MagicMock()
    sys.modules['app.models'] = MagicMock()
    sys.modules['app.utilities'] = MagicMock()
    sys.modules['app.utilities.extraction_tasks'] = MagicMock()
    sys.modules['app.utilities.security'] = MagicMock()
    sys.modules['app.utilities.document_helpers'] = MagicMock()
    sys.modules['app.utilities.analytics_helper'] = MagicMock()
    sys.modules['app.utilities.chat_manager'] = MagicMock()
    sys.modules['app.utilities.config'] = MagicMock()
    sys.modules['app.utilities.extraction_manager_nontyped'] = MagicMock()
    sys.modules['app.utilities.library_helpers'] = MagicMock()
    sys.modules['app.utilities.edit_history'] = MagicMock()
    sys.modules['app.utilities.verification_helpers'] = MagicMock()
    sys.modules['app.utilities.extraction_metrics'] = MagicMock()
    sys.modules['app.utilities.document_readers'] = MagicMock()
    sys.modules['app.oauth'] = MagicMock()
    sys.modules['flask.typing'] = MagicMock()
    sys.modules['flask_login'] = MagicMock()
    
    sys.modules['pypdf'] = MagicMock()
    sys.modules['pypandoc'] = MagicMock()
    sys.modules['devtools'] = MagicMock()
    sys.modules['markupsafe'] = MagicMock()
    sys.modules['werkzeug'] = MagicMock()
    # secure_filename is used
    sys.modules['werkzeug.utils'] = MagicMock()
    sys.modules['werkzeug.utils'].secure_filename = lambda x: x
    
    # Mock uuid module to ensure imports get the mock
    mock_uuid_module = MagicMock()
    mock_uuid_module.uuid4.return_value.hex.upper.return_value = "FILE_UUID_123"
    sys.modules['uuid'] = mock_uuid_module

    routes = types.ModuleType('routes')
    
    # Load source
    with open('app/blueprints/tasks/routes.py', 'r') as f:
        source = f.read()
        
    # Execute module
    try:
        exec(source, routes.__dict__)
    except Exception as e:
        print(f"Failed to load routes: {e}")
        return

    # Setup mocks AFTER exec to override/configure specific things if needed
    # But routes.request should point to our flask_mock.request because it was imported
    routes.request = request_mock 
    routes.jsonify = lambda x: (x, 200)
    
    # Configure the request mock content
    # ... (rest of configuration will be done in test cases)

    # Mock Models - check if imported from app.models or defined?
    # routes.py imports User, SearchSet, SmartDocument from app.models
    # So we should configure sys.modules['app.models']
    
    app_models_mock = sys.modules['app.models']
    app_models_mock.User = MagicMock()
    app_models_mock.SearchSet = MagicMock()
    app_models_mock.SmartDocument = MagicMock()
    app_models_mock.ActivityType = MagicMock()
    
    # Map them to routes for convenience in assertions, though they are same objects if imported
    routes.User = app_models_mock.User
    routes.SearchSet = app_models_mock.SearchSet
    routes.SmartDocument = app_models_mock.SmartDocument
    routes.ActivityType = app_models_mock.ActivityType
    
    # Mock Utilities
    # routes.py imports perform_extraction_task from app.utilities.extraction_tasks
    routes.perform_extraction_task = MagicMock()
    # But wait, if it imported it, we should mock the source module
    # or overwrite it in routes after exec. Overwriting in routes works.
    
    routes.activity_start = MagicMock()
    # secure_filename was mocked via werkzeug.utils

    # We need to ensure extract_text_from_doc is mocked
    # It is imported INSIDE the function: from app.utilities.document_readers import extract_text_from_doc
    # so we must mock the module sys.modules['app.utilities.document_readers']
    doc_readers_mock = sys.modules['app.utilities.document_readers']
    doc_readers_mock.extract_text_from_doc = MagicMock(return_value="sample text")
    
    # Also routes.extract_text_from_doc might not exist in global scope if imported inside function
    # So we don't need to set routes.extract_text_from_doc
    
    # ... existing test data setup ...
    routes.uuid = MagicMock()

    # --- Test Data Setup ---
    mock_search_set = MagicMock()
    mock_search_set.uuid = "extraction_uuid_1"
    mock_search_set.extraction_config = {"mode": "test"}
    mock_item = MagicMock()
    mock_item.searchtype = "extraction"
    mock_item.searchphrase = "Test Field"
    mock_search_set.items.return_value = [mock_item]
    
    routes.SearchSet.objects.return_value.first.return_value = mock_search_set
    
    mock_user = MagicMock()
    mock_user.id = "user_123"
    mock_user.user_id = "user_123" 
    routes.User.objects.return_value.first.return_value = mock_user
    
    
    # --- Test Case 1: Provide existing document_uuids (No file upload) ---
    print("\n--- Test Case 1: Existing document_uuids ---")
    
    # Mock form using custom class to support get/getlist logic accurately
    # Logic: getlist("document_uuids") called. If fail/empty, get("document_uuids") called.
    
    # Scenario: getlist returns empty, get returns "doc_1, doc_2"
    class Case1Form(MockForm):
        def getlist(self, k):
            if k == "document_uuids": return [] # Simulate passed as string in simple key
            return []
        def get(self, k, default=None):
             print(f"Case1Form.get called with {k}")
             if k == "document_uuids": return "doc_1, doc_2"
             if k == "search_set_uuid": return "extraction_uuid_1"
             return default
             
    # --- Test Case 1: Provide existing document_uuids (No file upload) ---
    print("\n--- Test Case 1: Existing document_uuids ---")
    
    # Check routes contents
    print(f"Check: routes.request in dict: {'request' in routes.__dict__}")
    print(f"Check: routes.User in dict: {'User' in routes.__dict__}")
    
    # Configure the flask mock in sys.modules directly
    flask_mock = sys.modules['flask']
    # Create the request mock
    request_mock = MagicMock()
    flask_mock.request = request_mock
    
    # Also reuse this mock for routes.request just in case
    routes.request = request_mock
    
    # Configure the request mock
    request_mock.form = Case1Form()
    request_mock.files.getlist.return_value = [] # No files
    
    # Use MagicMock for headers to spy on calls
    header_dict = {"x-api-key": "user_123"}
    headers_mock = MagicMock()
    headers_mock.get.side_effect = header_dict.get
    request_mock.headers = headers_mock
    
    # Mock SmartDocument query
    mock_doc1 = MagicMock()
    mock_doc1.uuid = "doc_1"
    mock_doc2 = MagicMock()
    mock_doc2.uuid = "doc_2"
    
    routes.SmartDocument.objects.return_value = [mock_doc1, mock_doc2]
    
    print("Calling run_extraction_integrated...")
    routes.run_extraction_integrated()
    
    print(f"DEBUG Checkpoints:")
    print(f"  request.headers.get called: {headers_mock.get.called}")
    if headers_mock.get.called:
        print(f"    args: {headers_mock.get.call_args}")
    print(f"  User.objects called: {routes.User.objects.called}")
    print(f"  SearchSet.objects called: {routes.SearchSet.objects.called}")
    if routes.SearchSet.objects.called:
        print(f"    SearchSet query: {routes.SearchSet.objects.call_args}")
    print(f"  request.files.getlist called: {request_mock.files.getlist.called}")
    
    # Verify SmartDocument query
    if routes.SmartDocument.objects.called:
        call_kwargs = routes.SmartDocument.objects.call_args.kwargs
        print(f"SmartDocument query kwargs: {call_kwargs}")
        if 'uuid__in' in call_kwargs and set(call_kwargs['uuid__in']) == {'doc_1', 'doc_2'}:
            print("SUCCESS: SmartDocument queried with correct UUIDs (parsed from string).")
        else:
            print(f"FAILURE: SmartDocument query incorrect: {call_kwargs.get('uuid__in')}")
    else:
        print("FAILURE: SmartDocument.objects was NOT called.")

    # Verify perform_extraction_task call
    if routes.perform_extraction_task.apply_async.called:
        args_list = routes.perform_extraction_task.apply_async.call_args[1]['args']
        doc_uuids_passed = args_list[2]
        print(f"Document UUIDs passed to task: {doc_uuids_passed}")
        
        if set(doc_uuids_passed) == {'doc_1', 'doc_2'}:
             print("SUCCESS: Correct document UUIDs passed to extraction task.")
        else:
             print("FAILURE: Incorrect document UUIDs passed.")
    else:
        print("FAILURE: perform_extraction_task not called.")


    # --- Test Case 2: Provide BOTH file upload and existing document ---
    print("\n--- Test Case 2: Upload + Existing ---")
    
    # Scenario: getlist("document_uuids") returns ["doc_3"] directly (e.g. standard form list)
    class Case2Form(MockForm):
        def getlist(self, k):
            if k == "document_uuids": return ["doc_3"]
            return []
        def get(self, k, default=None):
             if k == "search_set_uuid": return "extraction_uuid_1"
             return default
    
    routes.request.form = Case2Form()
    
    mock_file = MagicMock()
    mock_file.filename = "new_file.pdf"
    routes.request.files.getlist.return_value = [mock_file]
    
    mock_uuid_module.uuid4.return_value.hex.upper.return_value = "NEW_FILE_UUID"
    
    mock_doc3 = MagicMock()
    mock_doc3.uuid = "doc_3"
    routes.SmartDocument.objects.return_value = [mock_doc3]
    
    routes.run_extraction_integrated()
    
    if routes.perform_extraction_task.apply_async.called:
        args_list = routes.perform_extraction_task.apply_async.call_args[1]['args']
        doc_uuids_passed = args_list[2]
        print(f"Document UUIDs passed to task: {doc_uuids_passed}")
        
        if "doc_3" in doc_uuids_passed and "NEW_FILE_UUID" in doc_uuids_passed:
             print("SUCCESS: Both existing and new file UUIDs passed.")
        else:
             print("FAILURE: Missing expected UUIDs.")
             
if __name__ == "__main__":
    test_run_integrated_local_files()
