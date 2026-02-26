
import unittest
from unittest.mock import MagicMock, patch
import sys
import types

def test_run_integrated_config_override():
    # 1. Mock dependencies BEFORE importing the module under test
    #    We need to mock everything that app.blueprints.tasks.routes imports or uses.
    
    # Create the module structure in sys.modules so imports work
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
    sys.modules['flask'] = MagicMock()
    sys.modules['flask.typing'] = MagicMock()
    sys.modules['flask_login'] = MagicMock()
    
    sys.modules['pypdf'] = MagicMock()
    sys.modules['pypandoc'] = MagicMock()
    sys.modules['devtools'] = MagicMock()
    sys.modules['markupsafe'] = MagicMock()
    sys.modules['werkzeug'] = MagicMock()
    sys.modules['werkzeug.utils'] = MagicMock()
    
    # 2. Import the module under test (it will use the mocks)
    #    We might need to patch specifically within the module if it does "from x import y"
    
    # Let's try to load the file content and exec it in a controlled environment 
    # similar to the previous test, which seems more robust for this codebase's structure
    
    routes = types.ModuleType('routes')
    
    # Setup mocks
    routes.Blueprint = MagicMock()
    routes.request = MagicMock()
    routes.jsonify = lambda x: (x, 200)
    routes.current_user = MagicMock()
    routes.current_app = MagicMock()
    
    # Mock Models
    routes.User = MagicMock()
    routes.SearchSet = MagicMock()
    routes.SmartDocument = MagicMock()
    routes.ActivityType = MagicMock()
    
    # Mock Utilities
    routes.perform_extraction_task = MagicMock()
    routes.activity_start = MagicMock()
    routes.secure_filename = lambda x: x
    routes.secure_filename = lambda x: x
    routes.uuid = MagicMock()
    routes.uuid.uuid4.return_value.hex.upper.return_value = "FILE_UUID_123"
    routes.extract_text_from_doc = MagicMock(return_value="sample text")
    
    with open('app/blueprints/tasks/routes.py', 'r') as f:
        source = f.read()
    
    # Inject debug prints
    # Note: run_extraction_integrated is top-level, so body is indented by 4 spaces
    source = source.replace('def run_extraction_integrated() -> ResponseReturnValue:', 
                           'def run_extraction_integrated() -> ResponseReturnValue:\n    print("DEBUG: Entered function")')
                           
    source = source.replace('perform_extraction_task.apply_async(', 
                           'print("DEBUG: Calling apply_async")\n    perform_extraction_task.apply_async(')

    # Execute
    try:
        exec(source, routes.__dict__)
    except Exception as e:
        print(f"Failed to load routes: {e}")
        return

    # 3. Setup Test Data
    mock_search_set = MagicMock()
    mock_search_set.uuid = "test_uuid"
    mock_search_set.extraction_config = {"mode": "one_pass", "test_key": "test_value"}
    mock_search_set.items.return_value = [] # No items for simplified test, or add dummy items
    
    # Make sure we have extraction keys
    mock_item = MagicMock()
    mock_item.searchtype = "extraction"
    mock_item.searchphrase = "Test Field"
    mock_search_set.items.return_value = [mock_item]

    routes.SearchSet.objects.return_value.first.return_value = mock_search_set
    
    # Mock User
    mock_user = MagicMock()
    mock_user.id = "user_123"
    routes.User.objects.return_value.first.return_value = mock_user
    
    # Mock Request
    routes.request.headers = {"x-api-key": "user_123"}
    routes.request.form = {"search_set_uuid": "test_uuid"}
    
    # Mock File
    mock_file = MagicMock()
    mock_file.filename = "test.pdf"
    routes.request.files.getlist.return_value = [mock_file]
    
    # Mock os.path
    routes.os.path.exists.return_value = True
    routes.os.makedirs = MagicMock()

    # 4. Run the function
    print("Running run_extraction_integrated...")
    try:
        routes.run_extraction_integrated()
    except Exception as e:
        print(f"Error running function: {e}")
        # import traceback
        # traceback.print_exc()


    # 5. Verify perform_extraction_task call
    print("\nChecking perform_extraction_task arguments...")
    if routes.perform_extraction_task.apply_async.called:
        args, kwargs = routes.perform_extraction_task.apply_async.call_args
        
        # apply_async(args=[...])
        call_args_list = kwargs.get('args') or args[0]
        
        # The signature of perform_extraction_task is:
        # (activity_id, searchset_uuid, document_uuids, keys, root_path, fillable_pdf_url, extraction_config_override)
        # Note: extraction_config_override is the LAST argument (7th, index 6) if passed positionally, 
        # OR it might be passed as a kwarg if the signature allows, but apply_async usually takes args=[...]
        
        print(f"Call args: {call_args_list}")
        
        if len(call_args_list) >= 7:
            passed_config = call_args_list[6]
            print(f"Passed config: {passed_config}")
            if passed_config == mock_search_set.extraction_config:
                print("SUCCESS: Extraction config was passed correctly.")
            else:
                print(f"FAILURE: Extraction config mismatch. Expected {mock_search_set.extraction_config}, got {passed_config}")
        else:
            print("FAILURE: Extraction config argument meant to be at index 6 is MISSING.")
            print(f"Number of args passed: {len(call_args_list)}")
            
    else:
        print("FAILURE: perform_extraction_task.apply_async was NOT called.")

if __name__ == "__main__":
    test_run_integrated_config_override()
