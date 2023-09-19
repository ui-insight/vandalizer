from flask import url_for, redirect, render_template, flash, g, session, jsonify, Response, send_file
from app import app, llm
from app.models import User, SmartDocument, Space
from app.forms import LoginForm, SpaceForm
import os
import json
import datetime
import base64
from flask import request
import zipfile
from app.utilities.contract_review_manager import ContractReviewManager
from app.utilities.contract_review_manager_chained import ContractReviewManagerChained
from app.utilities.proofreading_manager import ProofreadingManager
from app.utilities.extraction_manager import ExtractionManager
import uuid

@app.route('/')
def index():
	spaces = list(Space.objects())
	if len(spaces) == 0:
		space = Space(title="Default Space", uuid=uuid.uuid4().hex)
		space.save()
		spaces = list(Space.objects())

	if request.args.get('id'):
		current_space = Space.objects(uuid=request.args.get('id')).first()
	else:
		current_space = spaces[0]

	spaces.remove(current_space)
	spaces.insert(0, current_space)

	docs = SmartDocument.objects(space=current_space.uuid).all()
	return render_template('index.html', docs=docs, spaces=spaces, current_space_id=spaces[0].uuid)

@app.route('/stats')
def stats():
	llm.stats()
	return "Success"

@app.route('/reset')
def reset():
	llm.delete_db()
	return "Success"

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
	llm.load_pdf(document=document)
	return jsonify({"complete": True, "uuid": uid})



@app.route('/review/<uuid>', methods=['GET'])
def review(uuid):
	document = SmartDocument.objects(uuid=uuid).first()
	#llm.load_documents()
	contract_review_manager = ContractReviewManager(llm)
	compliance_issues = []#contract_review_manager.scan()
	#print(compliance_issues)
	#compliance_issues = []
	return render_template('review/review.html', document=document, compliance_issues=compliance_issues)

@app.route('/api/sections', methods=['POST'])
def request_sections():
	data = request.get_json()
	uuid = data['uuid']
	document = SmartDocument.objects(uuid=uuid).first()
	contract_review_manager = ContractReviewManagerChained()
	contract_review_manager.root_path = app.root_path
	splits = contract_review_manager.prepare_splits(document.path)
	splits = splits.split(',')
	print(splits)
	return jsonify(splits)

@app.route('/api/compliance', methods=['POST'])
def review_compliance():
	data = request.get_json()
	uuid = data['uuid']
	#section = data['section']

	document = SmartDocument.objects(uuid=uuid).first()
	contract_review_manager = ContractReviewManagerChained()
	contract_review_manager.root_path = app.root_path
	compliance_issues = contract_review_manager.get_compliance(document.path)
	return jsonify(compliance_issues)

@app.route('/api/extract', methods=['POST'])
def extract():
	data = request.get_json()
	document = data['document']
	question = data['question']

	#document = SmartDocument.objects(uuid=uuid).first()
	extraction_manager = ExtractionManager()
	extraction_manager.root_path = app.root_path
	extraction = extraction_manager.extract(document, question)
	return jsonify(extraction)

@app.route('/api/proofread_spelling', methods=['POST'])
def proofread_spelling():
	data = request.get_json()
	document_path = data['document']
	proofread_manager = ProofreadingManager(llm)
	spelling_issues = proofread_manager.get_spelling_corrections(document_path)
	print(spelling_issues)
	return jsonify(spelling_issues)

@app.route('/api/proofread_grammar', methods=['POST'])
def proofread_grammar():
	data = request.get_json()
	document_path = data['document']
	proofread_manager = ProofreadingManager(llm)
	spelling_issues = proofread_manager.get_grammar_corrections(document_path)
	print(spelling_issues)
	return jsonify(spelling_issues)

@app.route('/api/proofread_suggestions', methods=['POST'])
def proofread_suggestions():
	data = request.get_json()
	document_path = data['document']
	proofread_manager = ProofreadingManager(llm)
	spelling_issues = proofread_manager.get_suggestions(document_path)
	print(spelling_issues)
	return jsonify(spelling_issues)

@app.route('/api/scan_document', methods=['POST'])
def scan_document():
	data = request.get_json()
	document_path = data['document']
	question = data['question']
	proofread_manager = ProofreadingManager(llm)
	spelling_issues = proofread_manager.scan_document(document_path, question)
	print(spelling_issues)
	return jsonify(spelling_issues)

@app.route('/api/ask', methods=['POST'])
def ask():
	data = request.get_json()
	question = data['question']
	space = data['space']
	print(question)
	answer = llm.ask_all_documents(space, question)
	return jsonify({'answer': answer})
	pass

@app.route('/api/ask_document', methods=['POST'])
def ask_document():
	data = request.get_json()
	question = data['question']
	title = data['document']
	
	model_name = 'gpt-3.5-turbo-16k'
	print(title)
	document = SmartDocument.objects(title=title).first()
	print(question)
	print(document.path)
	answer = llm.ask_single_document(question, document.path, model_name=model_name)

	return jsonify({'answer': answer})
	pass

@app.route('/api/delete', methods=['POST'])
def delete_documents():
	data = request.get_json()
	document_path = data['document']

	return "Success"

@app.route('/api/test', methods=['GET'])
def test_db():
	#llm.delete_db()
	llm.test_documents()
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

@app.route('/download', methods=['GET'])
def download():
	document_path = request.args.get('document')
	return send_file(os.path.join(app.root_path, 'static', 'uploads', document_path), as_attachment=True)