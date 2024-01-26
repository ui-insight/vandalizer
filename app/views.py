from flask import url_for, redirect, render_template, flash, g, session, jsonify, Response, send_file
from app import app, llm
from app.models import User, SmartDocument, Space, SearchSet, SearchSetItem
from app.forms import LoginForm, SpaceForm
import os
import base64
from flask import request
from app.utilities.extraction_manager2 import ExtractionManager2
from app.utilities.semantic_ingest import SemanticIngest
import uuid

@app.route('/')
def index():
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

	spaces.remove(current_space)
	spaces.insert(0, current_space)

	searchsets = SearchSet.objects(space=current_space.uuid).all()
	docs = SmartDocument.objects(space=current_space.uuid).all()
	return render_template('index.html', searchsets=searchsets, document=document, docs=docs, spaces=spaces, current_space_id=spaces[0].uuid)

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
	semantics = SemanticIngest()
	semantics.ingest(document=document)
	return jsonify({"complete": True, "uuid": uid})



@app.route('/api/add_search_set', methods=['POST'])
def add_search_set():
	data = request.get_json()
	title = data['title']
	space = data['space_id']
	searchset = SearchSet(title=title, uuid=uuid.uuid4().hex, space=space, user="admin", status="active")
	searchset.save()
	return jsonify({"complete": True})

@app.route('/api/add_search_term', methods=['POST'])
def add_search_term():
	data = request.get_json()
	searchphrase = data['term']
	searchset_uuid = data['search_set_uuid']
	searchtype = data['searchtype']
	searchsetitem = SearchSetItem(searchphrase=searchphrase, searchset=searchset_uuid, searchtype=searchtype)
	searchsetitem.save()
	return jsonify({"complete": True})

@app.route('/api/search_results', methods=['POST'])
def grab_template():
	data = request.get_json()
	searchset_uuid = data['search_set_uuid']
	document_uuid = data['document_uuid']
	
	document = SmartDocument.objects(uuid=document_uuid).first()
	print(document)
	search_set = SearchSet.objects(uuid=searchset_uuid).first()
	template = render_template('search_results.html', 
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


@app.route('/api/delete', methods=['POST'])
def delete_documents():
	data = request.get_json()
	document_path = data['document']

	return "Success"


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
