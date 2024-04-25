from flask import url_for, send_file, redirect, render_template, flash, g, session, jsonify, Response, send_file
from app import app
from app.models import User, SmartDocument, Space, SearchSet, SearchSetItem, ExtractionQualityRecord
from app.forms import LoginForm, SpaceForm
import os
import base64
from flask import request
from app.utilities.extraction_manager2 import ExtractionManager2
from app.utilities.semantic_ingest import SemanticIngest
from app.utilities.openai_interface import OpenAIInterface
import uuid
import threading
import json
import csv

@app.route('/')
def index():
	return render_template('landing.html')

@app.route('/home')
def home():
	document = None
	spaces = list(Space.objects())
	if len(spaces) == 0:
		space = Space(title="Default Space", uuid=uuid.uuid4().hex)
		space.save()
		spaces = list(Space.objects())

	if request.args.get('id'):
		current_space = Space.objects(uuid=request.args.get('id')).first()
	else:
		current_space = spaces[0]

	if request.args.get('docid'):
		document = SmartDocument.objects(uuid=request.args.get('docid')).first()
		current_space = Space.objects(uuid=document.space).first()
		semantics = SemanticIngest()
		# try:
		# 	if not semantics.check_for_collection(document):
		# 		thread = threading.Thread(target=ingest_semantics, args=(document,))
		# 		thread.start()
		# except:
		# 	print("Error checking for collection")

	spaces.remove(current_space)
	spaces.insert(0, current_space)

	extraction_sets = SearchSet.objects(space=current_space.uuid, set_type="extraction").all()
	prompt_sets = SearchSet.objects(space=current_space.uuid, set_type="prompt").all()
	docs = SmartDocument.objects(space=current_space.uuid).all()
	return render_template('index.html', extraction_sets=extraction_sets, prompt_sets=prompt_sets, document=document, docs=docs, spaces=spaces, current_space_id=spaces[0].uuid)

@app.route('/upload', methods=['GET', 'POST'])
def upload():
	json_data = request.get_json()
	blob = json_data['contentAsBase64String']
	filename = json_data['fileName']
	space = json_data['space']
	if SmartDocument.objects(title=filename, space=space).count() > 0:
		return jsonify({"complete": True})

	imgdata = base64.b64decode(blob)
	uid = uuid.uuid4().hex.upper()
	with open(os.path.join(app.root_path, 'static', 'uploads', f"{uid}.pdf"), 'wb') as f:
		f.write(imgdata)
	
	document = SmartDocument(title=filename, path=f"{uid}.pdf", uuid=uid, space=space)
	document.save()
	
	# Create a new thread and start it
	thread = threading.Thread(target=ingest_semantics, args=(document,))
	thread.start()
	return jsonify({"complete": True, "uuid": uid})

def ingest_semantics(document):
		semantics = SemanticIngest()
		semantics.ingest(document=document)


@app.route('/api/chat', methods=['POST'])
def chat():
	data = request.get_json()
	message = data['message']
	document_uuid = data['document_uuid']
	document = SmartDocument.objects(uuid=document_uuid).first()
	print(message)
	print(document.path)
	response = OpenAIInterface().ask_question_to_document(app.root_path, document.path, message)
	print(response)
	return jsonify(response)

@app.route('/api/add_search_set', methods=['POST'])
def add_search_set():
	data = request.get_json()
	title = data['title']
	space = data['space_id']
	search_type = data['search_type']
	searchset = SearchSet(title=title, uuid=uuid.uuid4().hex, space=space, user="admin", status="active", set_type=search_type)
	searchset.save()
	return jsonify({"complete": True})

@app.route('/api/add_search_term', methods=['POST'])
def add_search_term():
	data = request.get_json()
	print(data)
	searchphrase = data['term']
	searchset_uuid = data['search_set_uuid']
	searchtype = data['searchtype']
	print(searchphrase)

	searchsetitem = SearchSetItem(searchphrase=searchphrase, searchset=searchset_uuid, searchtype=searchtype)
	searchsetitem.save()
	return jsonify({"complete": True})

@app.route('/api/search_results', methods=['POST'])
def grab_template():
	data = request.get_json()
	searchset_uuid = data['search_set_uuid']
	document_uuid = data['document_uuid']
	print("Fetch loading template")
	document = SmartDocument.objects(uuid=document_uuid).first()
	print(document)
	search_set = SearchSet.objects(uuid=searchset_uuid).first()

	if search_set.set_type == "extraction":	
		template = render_template('search_results.html', 
							search_set=search_set,
							document=document
							)
		response = {
				'template': template,
			}
		return jsonify(response)
	else:
		template = render_template('prompt_results.html', 
							search_set=search_set,
							document=document
							)
		response = {
				'template': template,
			}
		return jsonify(response)

@app.route('/api/semantic_search', methods=['POST'])
def semantic_search():
	data = request.get_json()
	search_term = data['search_term']
	document_uuid = data['document_uuid']
	
	document = SmartDocument.objects(uuid=document_uuid).first()
	semantics = SemanticIngest()
	results = semantics.search(search_term, document)
	print(results)

	response = {
			'results': results,
		}
	return jsonify(response)

@app.route('/api/begin_search', methods=['POST'])
def begin_search():
	data = request.get_json()
	searchset_uuid = data['search_set_uuid']
	document_path = data['document']

	search_set = SearchSet.objects(uuid=searchset_uuid).first()
	keys = []
	items = search_set.items()
	for item in items:
		if item.searchtype == "extraction":
			keys.append(item.searchphrase)

	if len(keys) > 0:
		em = ExtractionManager2()
		em.root_path = app.root_path
		results = em.extract(keys, document_path)
		print(results)
		template = render_template('search_results.html', 
							search_set=search_set,
							results=results
							)
		response = {
				'template': template,
			}
		return jsonify(response)
	else:
		template = render_template('search_results.html', 
							search_set=search_set
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
	for item in items:
		if item.searchtype == "prompt":
			keys.append(item.searchphrase)

	if len(keys) > 0:
		llm = OpenAIInterface()
		llm.load_document(app.root_path, document_path)
		results = {}
		for key in keys:
			results[key] = llm.ask_question_to_loaded_document(key)
		print(results)
		template = render_template('prompt_results.html', 
							search_set=search_set,
							results=results
							)
		response = {
				'template': template,
			}
		return jsonify(response)
	else:
		template = render_template('prompt_results.html', 
							search_set=search_set
							)
		response = {
				'template': template,
			}
		return jsonify(response)

@app.route('/delete_document', methods=['GET'])
def delete_documents():
	document_uuid = request.args.get('docid')
	document = SmartDocument.objects(uuid=document_uuid).first()
	document.delete()
	semantics = SemanticIngest()
	semantics.delete(document)
	return redirect('/')

@app.route('/delete_search_set', methods=['GET'])
def delete_search_set():
	search_set_uuid = request.args.get('uuid')
	print(search_set_uuid)
	search_set = SearchSet.objects(id=search_set_uuid).first()
	search_set.delete()
	return redirect('/')

@app.route('/delete_search_set_item', methods=['GET'])
def delete_search_set_item():
	search_set_uuid = request.args.get('uuid')
	print(search_set_uuid)
	search_set = SearchSetItem.objects(id=search_set_uuid).first()
	search_set.delete()
	return redirect('/')


##################
# Spaces         #
##################
@app.route('/spaces/new', methods=['GET','POST'])
def new_space():
	if request.method == 'POST':
		title = request.form['title']
		space = Space(title=title, uuid=uuid.uuid4().hex)
		space.save()
		return redirect('/?id=' + space.uuid)
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
	csv_file_path = os.path.join(app.root_path, 'static', 'extraction.csv')
	
	# Write the rows to the CSV file
	with open(csv_file_path, 'w', newline='') as f:
		writer = csv.writer(f)
		writer.writerows(rows)
	
	# Return the path to the CSV file
	return send_file('static/extraction.csv', 
                     mimetype='text/csv',
                     as_attachment=True)