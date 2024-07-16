from flask import url_for, send_file, redirect, render_template, flash, g, session, jsonify, Response, send_file
from app import app
from app.models import User, SmartDocument, Space, SearchSet, SearchSetItem, ExtractionQualityRecord, SmartFolder
from app.forms import LoginForm, SpaceForm
import os
import base64
from flask import request
from app.utilities.extraction_manager2 import ExtractionManager2
from app.utilities.semantic_ingest import SemanticIngest
from app.utilities.openai_interface import OpenAIInterface
from app.utilities.fillable_pdf_manager import FillablePDFManager
import uuid
import threading
import json
import csv
from itertools import chain
from copy import deepcopy
from pypdf import PdfReader
import io

#OAuth
import secrets
from oauthlib.oauth2.rfc6749.errors import TokenExpiredError
from oauthlib.oauth2.rfc6749.errors import MismatchingStateError
from flask_dance.contrib.azure import azure, make_azure_blueprint


blueprint = make_azure_blueprint(
        client_id=app.config['CLIENT_ID'],
        client_secret=app.config['CLIENT_SECRET'],
        tenant=app.config['TENANT_NAME'],  
    )

app.register_blueprint(blueprint, url_prefix="/login")

@app.errorhandler(MismatchingStateError)
def mismatching_state(e):
    return redirect(url_for("azure.login"))

@app.route('/')
def index():
	if azure.authorized:
		print("Already authorized")
		return redirect(url_for('home'))
	
	print("Not authorized")
	return render_template('landing.html')

@app.route('/login')
def login():
	if not azure.authorized:
		return redirect(url_for("azure.login"))
	else:
		return redirect(url_for('home'))
	
@app.route('/logout')
def logout():
	session.clear()
	return redirect(url_for('index'))



#######################################
######## HOME ######
#######################################

@app.route('/home')
def home():
	#if not azure.authorized:
	#	return redirect(url_for("azure.login"))
	if "user_id" not in session:
		print("No user session")
		resp = azure.get("/v1.0/me")
		user_info = resp.json()
		if "id" not in user_info:
			print("Got nothing from azure")
			session["user_id"] = "admin"
		else:
			print("Got user info from azure")
			user_id = user_info["id"]
			session["user_id"] = user_id

	user = load_user()
	section = request.args.get('section', default="Extract").strip()
	print(section)
	
	document = None

	# Get the space
	spaces = list(Space.objects())
	if len(spaces) == 0:
		space = Space(title="Default Space", uuid=uuid.uuid4().hex)
		space.save()
		spaces = list(Space.objects())

	if request.args.get('id'):
		current_space = Space.objects(uuid=request.args.get('id')).first()
	else:
		current_space = spaces[0]

	documents = []
	# Check for documents
	if request.args.get('docid'):
		doc_id = request.args.get('docid')
		document = SmartDocument.objects(uuid=doc_id).first()
		documents.append(document)
		current_space = Space.objects(uuid=document.space).first()
		semantics = SemanticIngest()
		if not semantics.check_for_collection(document):
			thread = threading.Thread(target=ingest_semantics, args=(document,))
			thread.start()

	if request.args.get('docids'):
		doc_ids = request.args.get('docids').split(",")
		for doc_id in doc_ids:
			document = SmartDocument.objects(uuid=doc_id).first()
			documents.append(document)
		
		current_space = Space.objects(uuid=document.first.space).first()
		semantics = SemanticIngest()
		if documents.count == 1:
			try:
				if not semantics.check_for_collection(documents.first):
					thread = threading.Thread(target=ingest_semantics, args=(documents.first,))
					thread.start()
			except:
				print("Error checking for collection")

	spaces.remove(current_space)
	spaces.insert(0, current_space)

	# Get the extraction and prompt sets
	global_extraction_sets = SearchSet.objects(space=current_space.uuid, is_global=True, set_type="extraction").all()
	user_extraction_sets = SearchSet.objects(user_id=user.user_id, space=current_space.uuid, is_global=False, set_type="extraction").all()
	extraction_sets = chain(global_extraction_sets, user_extraction_sets)

	# Get the prompt sets
	global_prompt_sets = SearchSet.objects(space=current_space.uuid, is_global=True, set_type="prompt").all()
	user_prompt_sets = SearchSet.objects(user_id=user.user_id, space=current_space.uuid, is_global=False,  set_type="prompt").all()
	prompt_sets = chain(global_prompt_sets, user_prompt_sets)
	
	# Get the folders
	current_folder_id = "0"
	current_folder_parent_id = "0"
	if request.args.get('folder_id'):
		current_folder_id = request.args.get('folder_id')
	folder_docs = SmartDocument.objects(user_id=user.user_id, space=current_space.uuid, folder="0").all()
	if current_folder_id != 0 and current_folder_id != "0":
		folder_docs = SmartDocument.objects(user_id=user.user_id, space=current_space.uuid, folder=current_folder_id).all()
		folder = SmartFolder.objects(uuid=current_folder_id).first()
		current_folder_parent_id = folder.parent_id
	folders = SmartFolder.objects(user_id=user.user_id, space=current_space.uuid, parent_id="0").all()
	if current_folder_id != 0:
		folders = SmartFolder.objects(user_id=user.user_id, space=current_space.uuid, parent_id=current_folder_id).all()
	

	return render_template('index.html', extraction_sets=extraction_sets, 
						prompt_sets=prompt_sets, 
						folders=folders, 
						current_folder_parent_id=current_folder_parent_id, 
						current_folder_id=current_folder_id, 
						documents=documents, 
						folder_docs=folder_docs, 
						spaces=spaces, 
						current_space_id=spaces[0].uuid, 
						section=section)

@app.route('/upload_fillable_pdf', methods=['POST'])
def upload_fillable_pdf():
	if 'file' not in request.files:
		return jsonify({'error': 'No file part'}), 400

	file = request.files['file']
	if file.filename == '':
		return jsonify({'error': 'No selected file'}), 400
	
	search_set_uuid = request.form.get('search_set_uuid')
	print(search_set_uuid)
	searchset = SearchSet.objects(uuid=search_set_uuid).first()
	for item in searchset.items():
		item.delete()

	# Read the PDF file
	file_stream = io.BytesIO(file.read())
	pdf_reader = PdfReader(file_stream)
	fields = pdf_reader.get_fields()

	# Write to the filesystem
	file.save(os.path.join(app.root_path, 'static', 'uploads', file.filename))
	searchset.fillable_pdf_url = file.filename
	searchset.save()

	# Extract field names and options
	field_options = {}
	for field_name, field_data in fields.items():
		if '/Opt' in field_data:
			field_options[field_name] = field_data['/Opt']
		else:
			field_options[field_name] = 'No options'
	
	fillable_manager = FillablePDFManager()
	output = fillable_manager.build_set_from_items(field_options)
	#output = json.loads(output)
	bindings = output['fields']
	print(output)

	for item in bindings:
		key = list(item.keys())[0]
		value = item[key]
		item = SearchSetItem(searchphrase=value, searchset=search_set_uuid, searchtype="extraction", pdf_binding=key)
		item.save()

	return jsonify("Success"), 200


@app.route('/upload', methods=['GET', 'POST'])
def upload():
	user = load_user()
	if user is None:
		return redirect(url_for('login'))

	json_data = request.get_json()
	blob = json_data['contentAsBase64String']
	filename = json_data['fileName']
	space = json_data['space']
	folder = json_data['folder']

		
	print("Folder is")
	print(folder)
	if folder is None or folder == "":
		folder = "0"

	if SmartDocument.objects(title=filename, space=space, user_id=user.user_id, folder=folder).count() > 0:
		return jsonify({"complete": True})



	imgdata = base64.b64decode(blob)
	uid = uuid.uuid4().hex.upper()
	with open(os.path.join(app.root_path, 'static', 'uploads', f"{uid}.pdf"), 'wb') as f:
		f.write(imgdata)
	
	document = SmartDocument(title=filename, path=f"{uid}.pdf", uuid=uid, user_id=user.user_id, space=space, folder=folder)
	document.save()
	
	# Create a new thread and start it
	thread = threading.Thread(target=ingest_semantics, args=(document,))
	thread.start()
	return jsonify({"complete": True, "uuid": uid, "folder_id": folder})

@app.route('/read_pdf', methods=['POST'])
def read_pdf():
	# user = load_user()
	# if user is None:
	# 	return redirect(url_for('login'))

	json_data = request.get_json()
	blob = json_data['contentAsBase64String']
	filename = json_data['fileName']

	imgdata = base64.b64decode(blob)
	uid = uuid.uuid4().hex.upper()
	with open(os.path.join(app.root_path, 'static', 'temp', f"{uid}.pdf"), 'wb') as f:
		f.write(imgdata)
	
	pdf = PdfReader(os.path.join(app.root_path, "static", 'temp', f"{uid}.pdf"))
	number_of_pages = len(pdf.pages)
	full_text = ""
	for i in range(number_of_pages):
		full_text = full_text + pdf.pages[i].extract_text() + " "

	print(full_text)
	return jsonify({"full_text": full_text})

def ingest_semantics(document):
		semantics = SemanticIngest()
		semantics.ingest(document=document)


@app.route('/api/chat', methods=['POST'])
def chat():
	data = request.get_json()
	message = data['message']
	document_uuids = data['document_uuids']
	documents = []
	print(document_uuids)
	for doc_uuid in document_uuids:
		document = SmartDocument.objects(uuid=doc_uuid).first()
		if document != None:
			documents.append(document)

	
	response = OpenAIInterface().ask_question_to_documents(app.root_path, documents, message)
	print(response)
	return jsonify(response)

@app.route('/api/add_search_set', methods=['POST'])
def add_search_set():
	user = load_user()
	if user is None:
		return redirect(url_for('login'))
	
	data = request.get_json()
	title = data['title']
	space = data['space_id']
	search_type = data['search_type']
	searchset = SearchSet(title=title, uuid=uuid.uuid4().hex, space=space, user_id=user.user_id, status="active", set_type=search_type)
	if user.is_admin:
		searchset.is_global = True
	searchset.save()
	return jsonify({"complete": True})

@app.route('/api/add_search_term', methods=['POST'])
def add_search_term():
	data = request.get_json()
	print(data)
	searchphrase = data['term']
	searchset_uuid = data['search_set_uuid']
	searchset = SearchSet.objects(uuid=searchset_uuid).first()
	searchtype = data['searchtype']

	attachments = data['attachments'] if 'attachments' in data else None
	print(searchphrase)
	print(attachments)


	if searchset.is_global:
		user = load_user()
		if not user.is_admin:
			return jsonify({"complete": False, "error": "You do not have permission to add to this search set."})

	searchsetitem = SearchSetItem(searchphrase=searchphrase, searchset=searchset_uuid, searchtype=searchtype)
	if attachments:
		searchsetitem.text_blocks = attachments
	
	searchsetitem.save()

	print(searchsetitem)
	template = render_template('toolpanel/search_set_item.html', search_set=searchset, item=searchsetitem)
	response = {
				'complete': True,
				'template': template,
			}
	return jsonify(response)

@app.route('/api/search_results', methods=['POST'])
def grab_template():
	data = request.get_json()
	searchset_uuid = data['search_set_uuid']
	document_uuids = data['document_uuids']
	
	edit_mode = data['edit_mode']
	documents = []
	for doc_uuid in document_uuids:
		document = SmartDocument.objects(uuid=doc_uuid).first()
		documents.append(document)

	search_set = SearchSet.objects(uuid=searchset_uuid).first()


	print("Document count: " + str(len(documents)))

	if search_set.set_type == "extraction":	
		if edit_mode:
			template = render_template('toolpanel/extractions/edit_search_results.html', 
							search_set=search_set,
							documents=documents
							)
			
			response = {
				'template': template,
			}
			
			return jsonify(response)
		else:
			template = render_template('toolpanel/extractions/search_results.html', 
							search_set=search_set,
							documents=documents
							)
			response = {
				'template': template,
			}

			return jsonify(response)
	else:
		if edit_mode:
			template = render_template('toolpanel/prompts/edit_prompt_results.html', 
								search_set=search_set,
								documents=documents
								)
			response = {
					'template': template,
				}
			return jsonify(response)
		else:
			template = render_template('toolpanel/prompts/prompt_results.html', 
								search_set=search_set,
								documents=documents
								)
			response = {
					'template': template,
				}
			return jsonify(response)

@app.route('/api/semantic_search', methods=['POST'])
def semantic_search():
	data = request.get_json()
	search_term = data['search_term']
	document_uuids = data['document_uuids']
	
	documents = []
	for doc_uuid in document_uuids:
		document = SmartDocument.objects(uuid=doc_uuid).first()
		documents.append(document)

	semantics = SemanticIngest()
	results = semantics.search(search_term, documents.first)
	print(results)

	response = {
			'results': results,
		}
	return jsonify(response)

@app.route('/api/begin_search', methods=['POST'])
def begin_search():
	data = request.get_json()
	searchset_uuid = data['search_set_uuid']
	document_uuids = data['document_uuids']

	documents = []
	document_paths = []
	for doc_uuid in document_uuids:
		document = SmartDocument.objects(uuid=doc_uuid).first()
		documents.append(document)
		document_paths.append(document.path)

	
	print("Fetch loading template:" + searchset_uuid)

	search_set = SearchSet.objects(uuid=searchset_uuid).first()
	keys = []
	items = search_set.items()
	for item in items:
		if item.searchtype == "extraction":
			keys.append(item.searchphrase)

	if len(keys) > 0:
		em = ExtractionManager2()
		em.root_path = app.root_path
		results = em.extract(keys, document_paths)
		print(results)
		template = render_template('toolpanel/extractions/search_results.html', 
							search_set=search_set,
							results=results,
							documents=documents
							)
		response = {
				'template': template,
			}
		return jsonify(response)
	else:
		template = render_template('toolpanel/extractions/search_results.html', 
							search_set=search_set,
							documents=documents
							)
		response = {
				'template': template,
			}
		return jsonify(response)


@app.route('/api/begin_prompt_search', methods=['POST'])
def begin_prompt_search():
	data = request.get_json()
	searchset_uuid = data['search_set_uuid']
	document_path = data['document']

	search_set = SearchSet.objects(uuid=searchset_uuid).first()
	keys = []
	items = search_set.items()

	if len(items) > 0:
		llm = OpenAIInterface()
		llm.load_document(app.root_path, document_path)
		results = {}
		for item in items:
			results[item.searchphrase] = llm.ask_question_to_loaded_document(item)
		print(results)
		template = render_template('toolpanel/prompts/prompt_results.html', 
							search_set=search_set,
							results=results
							)
		response = {
				'template': template,
			}
		return jsonify(response)
	else:
		template = render_template('toolpanel/prompts/prompt_results.html', 
							search_set=search_set
							)
		response = {
				'template': template,
			}
		return jsonify(response)

@app.route('/rename_document', methods=['POST'])
def rename_document():
	data = request.get_json()
	document_uuid = data['uuid']
	new_title = data['newName']

	document = SmartDocument.objects(uuid=document_uuid).first()
	document.title = new_title
	document.save()
	return jsonify({"complete": True})

@app.route('/rename_folder', methods=['POST'])
def rename_folder():
	data = request.get_json()
	document_uuid = data['uuid']
	new_title = data['newName']

	print(document_uuid)
	print(new_title)

	document = SmartFolder.objects(uuid=document_uuid).first()
	document.title = new_title
	document.save()
	return jsonify({"complete": True})

@app.route('/delete_document', methods=['GET'])
def delete_documents():
	document_uuid = request.args.get('docid')
	document = SmartDocument.objects(uuid=document_uuid).first()
	document.delete()
	semantics = SemanticIngest()
	semantics.delete(document)
	return redirect('/home')

@app.route('/delete_search_set', methods=['GET'])
def delete_search_set():
	search_set_uuid = request.args.get('uuid')
	print(search_set_uuid)
	search_set = SearchSet.objects(id=search_set_uuid).first()
	search_set.delete()
	return redirect('/')

@app.route('/api/rename_search_set', methods=['POST'])
def rename_search_set():
	data = request.get_json()
	search_set_uuid = data['search_set_uuid']
	new_title = data['new_title']
	print(search_set_uuid)
	search_set = SearchSet.objects(uuid=search_set_uuid).first()
	search_set.title = new_title
	search_set.save()

	return jsonify({"complete": True})

@app.route('/api/clone_search_set', methods=['POST'])
def clone_search_set():
	data = request.get_json()
	search_set_uuid = data['search_set_uuid']
	print(search_set_uuid)
	search_set = SearchSet.objects(uuid=search_set_uuid).first()
	new_search_set = deepcopy(search_set)
	new_search_set.id = None
	new_search_set.uuid = uuid.uuid4().hex
	new_search_set.is_global = False
	new_search_set.title = "Copy of " + new_search_set.title
	new_search_set.save()

	# Clone the search set items
	for item in search_set.items():
		new_item = deepcopy(item)
		new_item.id = None
		new_item.searchset = new_search_set.uuid
		new_item.save()

	return jsonify({"complete": True})

@app.route('/api/delete_search_set_item', methods=['POST'])
def delete_search_set_item():
	data = request.get_json()
	print("Deleting search set item")
	search_set_item_uuid = data['uuid']
	print(search_set_item_uuid)
	search_set = SearchSetItem.objects(id=search_set_item_uuid).first()
	search_set.delete()
	return jsonify({"complete": True})


##################
# Spaces         #
##################
@app.route('/spaces/new', methods=['GET','POST'])
def new_space():
	if request.method == 'POST':
		title = request.form['title']
		space = Space(title=title, uuid=uuid.uuid4().hex)
		space.save()
		return redirect('/home?id=' + space.uuid)
	return render_template('spaces/new.html')

@app.route('/submit_rating', methods=['POST'])
def submit_rating():
	data = request.get_json()
	print(data)
	pdf_title = data['pdf_title']
	rating = data['rating']
	comment = data['comment']
	result_json = data['result_json']
	result_json_str = json.dumps(result_json)
	record = ExtractionQualityRecord(pdf_title=pdf_title, star_rating=rating, comment=comment, result_json=result_json_str)
	record.save()
	return jsonify({"complete": True})


@app.route('/export_extraction', methods=['GET'])
def export_extraction():
	result_json = request.args.to_dict()
	#result_json = data['result_json']
	
	# Convert the dictionary to a list of rows
	rows = []
	for key, value in result_json.items():
		rows.append([key, value])
	
	# Define the file path for the CSV file
	csv_file_path = os.path.join(app.root_path, 'static', 'export.csv')
	
	print(rows)
	# Write the rows to the CSV file
	with open(csv_file_path, 'w', newline='') as f:
		writer = csv.writer(f)
		writer.writerows(rows)
	
	# Return the path to the CSV file
	return send_file('static/export.csv', 
                     mimetype='text/csv',
                     as_attachment=True)


@app.route('/build_admin')
def build_admin():
	user = User(user_id="admin", is_admin=True)
	user.save()
	session["user_id"] = "admin"

def load_user():
	if "user_id" in session:
		user = User.objects(user_id=session["user_id"]).first()
		if user:
			print("User found")
			return user
		else:
			user = User(user_id=session["user_id"], is_admin=False)
			user.save()
			print("Built new user" + user.user_id)
			return user
	return None





@app.route('/files/delete_folder', methods=['POST'])
def delete_folder():
    folder_id = request.GET.get('folder_id')
    SmartFolder.objects.filter(id=folder_id).delete()
    return redirect('file_browser')


@app.route('/files/move_item', methods=['POST'])
def move_item():
    item_type = request.POST.get('item_type')
    item_id = request.POST.get('item_id')
    target_folder_id = request.POST.get('target_folder_id')
    
    if item_type == 'folder':
        SmartFolder.objects.filter(id=item_id).update(parent_id=target_folder_id)
    elif item_type == 'document':
        SmartDocument.objects.filter(uuid=item_id).update(folder_id=target_folder_id)
    
    return redirect('file_browser')


####### File Browser #######
@app.route('/files/create_folder', methods=['GET', 'POST'])
def create_folder():
	parent_id = request.form['parent_id']
	name = request.form['name']
	space_id = request.form['space_id']
	SmartFolder.objects.create(title=name, parent_id=parent_id, space=space_id, user_id=session["user_id"], uuid=uuid.uuid4().hex)
	return redirect('/home')