from flask import url_for, redirect, render_template, flash, g, session, jsonify, Response, send_file
from app import app, llm
from app.models import User, SmartDocument
from app.forms import LoginForm
import os
import json
import datetime
import base64
from flask import request
import zipfile
from app.utilities.contract_review_manager import ContractReviewManager
import uuid

@app.route('/')
def index():
	docs = SmartDocument.objects().all()
	return render_template('index.html', docs=docs)

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
	if SmartDocument.objects(title=filename).count() > 0:
		return jsonify({"complete": True})

	imgdata = base64.b64decode(blob)
	uid = uuid.uuid4().hex[:6].upper()
	with open(os.path.join(app.root_path, 'static', 'uploads', f"{uid}.pdf"), 'wb') as f:
		f.write(imgdata)
	
	SmartDocument(title=filename, path=f"{uid}.pdf", uuid=uid).save()
	llm.load_pdf(pdf_path=f"{uid}.pdf")
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
	contract_review_manager = ContractReviewManager(llm)
	sections = contract_review_manager.fetch_sections(document.title)
	return jsonify(sections)

@app.route('/api/compliance', methods=['POST'])
def review_compliance():
	data = request.get_json()
	uuid = data['uuid']
	section = data['section']
	document = SmartDocument.objects(uuid=uuid).first()
	contract_review_manager = ContractReviewManager(llm)
	compliance_issues = contract_review_manager.get_compliance(document.title, section)
	print(compliance_issues)
	return jsonify(compliance_issues)

@app.route('/api/ask', methods=['POST'])
def ask():
	data = request.get_json()
	question = data['question']
	print(question)
	answer = llm.ask_document(question)
	return jsonify({'answer': answer})
	pass