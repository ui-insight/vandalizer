import sys
import json
import requests
from multiprocessing.pool import ThreadPool
import re

class UILLM:

    def ask_question(question, is_json=False, temperature=0.7, max_tokens=3000):
        endpoint = "http://data-potato.hpc.uidaho.edu:80/v1/chat/completions"

        data = {
            "model": "llama3:70b-instruct",
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": [
                {
                "role": "user", 
                "content": question
                }
            ]
        }

        if is_json:
            data["response_format"] = {"type": "json_object"}

        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer no-key" 
        }

        response = requests.post(endpoint, json=data, headers=headers)
        if response.status_code == 200:
            try:
                output = response.json()
                content = output["choices"][0]["message"]["content"]
                if content == None:
                    print("Failed on output: " + output)
                
                if is_json:
                    jsoncontent = json.loads(content)
                    return jsoncontent
                else:
                    return content    
            except json.JSONDecodeError:
                print("Invalid JSON format")
                print(output)
        else:
            print("SERVER ERROR")
            print(response.status_code)
            print(response.text)

    def list_models(display='pretty', verbose=True):
        endpoint = "http://data-potato.hpc.uidaho.edu:8001/api/tags"

        response = requests.get(endpoint)
        # allow users to silence the print 
        if verbose:
            print(response.text)
        data = json.loads(response.text)
        # default view is a pretty print
        if display == 'pretty':
            UILLM.display_models(data)
        # list option returns a list with only the model names
        elif display == 'list':
            return UILLM.display_models_list(data)
        
    def display_models_list(data):
        return [x.get('name') for x in data.get('models')]
        
    def display_models(data):
        models = data.get('models', [])
        if not models:
            print("No models available.")
            return

        for model in models:
            name = model.get('name', 'N/A')
            details = model.get('details', {})
            family = details.get('family', 'N/A')
            parameter_size = details.get('parameter_size', 'N/A')
            quantization_level = details.get('quantization_level', 'N/A')


            print(f"Model: {name}")
            print(f"  Details:")
            print(f"    Family: {family}")
            print(f"    Parameter Size: {parameter_size}")
            print(f"    Quantization Level: {quantization_level}")
            print("-" * 40)

    def parse_command_R(data):
        # strip leading and trailing newline characters
        data = data.strip("\n")
    
        # use a regular expression to extract the JSON part
        json_match = re.search(r'{.*}', data, re.DOTALL)
        if not json_match:
            raise ValueError(f"Unexpected response from command-r. JSON string not found in data: {data}")
    
        json_str = json_match.group(0)
        # sometimes the json that command-R provides is not properly formatted. Use regular expression to attempt to fix (i.e. missing comma).
        json_str = json_str.strip()
        json_str = re.sub(r'(?<!")(\b\w+\b)(?!")(?=\s*:)', r'"\1"', json_str)
        json_str = re.sub(r'(?<=["\]}])\s*(?=["\[{])', ',', json_str)
        try:
            # parse the JSON string into a Python dictionary
            parsed_json = json.loads(json_str)
            return parsed_json
        except json.JSONDecodeError as e:
            print(f"Invalid JSON provided by command-r. Error: {e.msg}, Content: {json_str}")
            # raise the JSONDecodeError as the ask_question_to_model() method handles this exception
            raise e

    def ask_question_to_model(question, is_json=False, model="dolphin-mixtral:8x22b", temperature=0.7):
        endpoint = "http://data-potato.hpc.uidaho.edu:8001/v1/chat/completions"

        data = {
            "model": model,
            "temperature": temperature,
            "max_tokens": 3000,
            "messages": [
                {
                "role": "user", 
                "content": question
                }
            ]
        }

        if is_json:
            if 'command-r' in model:
                data["format"] = "json"
            else:
                data["response_format"] = {"type": "json_object"}

        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer no-key" 
        }

        response = requests.post(endpoint, json=data, headers=headers)
        if response.status_code == 200:
            try:
                output = response.json()
                content = output["choices"][0]["message"]["content"]
                if content == None:
                    print("Failed on output: " + output)
                
                if is_json:
                    if 'command-r' in model:
                        jsoncontent = UILLM.parse_command_R(content)
                    else:
                        jsoncontent = json.loads(content)
                    return jsoncontent
                else:
                    return content    
            except json.JSONDecodeError:
                print("Invalid JSON format")
                print(output)
        else:
            print("SERVER ERROR")
            print(response.status_code)
            print(response.text)

    def list_embeddings():
        endpoint = "http://data-potato.hpc.uidaho.edu:8003/api/tags"

        response = requests.get(endpoint)
        print(response.text)
        data = json.loads(response.text)
        UILLM.display_models(data)

    def convert_string_to_embeddings(string, model="charaf/sfr-embedding:latest"):
        endpoint = "http://data-potato.hpc.uidaho.edu:8003/api/embeddings"

        data = {
            "model": model,
            "prompt": string
        }

        response = requests.post(endpoint, json=data, headers={})
        if response.status_code == 200:
            output = response.json()
            return output
        else:
            print("SERVER ERROR")
            print(response.status_code)
            print(response.text)

    def ask_fast_question(question, is_json=False, temperature=0.7):
        endpoint = "http://data-potato.hpc.uidaho.edu:8002/v1/chat/completions"

        data = {
            "model": "mistral:instruct",
            "temperature": temperature,
            "max_tokens": 3000,
            "messages": [
                {
                "role": "user", 
                "content": question
                }
            ]
        }

        if is_json:
            data["response_format"] = {"type": "json_object"}

        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer no-key" 
        }

        response = requests.post(endpoint, json=data, headers=headers)
        if response.status_code == 200:
            try:
                output = response.json()
                content = output["choices"][0]["message"]["content"]
                if content == None:
                    print("Failed on output: " + output)
                
                if is_json:
                    jsoncontent = json.loads(content)
                    return jsoncontent
                else:
                    return content    
            except json.JSONDecodeError:
                print("Invalid JSON format")
                print(output)
        else:
            print("SERVER ERROR")
            print(response.status_code)
            print(response.text)
    


    def ask_question_sm1(question, is_json=False, temperature=0.7):
        return UILLM.ask_question_to_server("http://calvin.nkn.uidaho.edu", "8001", "mixtral-8x7b-instruct-v0.1.Q4_K_M.gguf", question, is_json, temperature)
    
    def ask_question_sm2(question, is_json=False, temperature=0.7):
        return UILLM.ask_question_to_server("http://calvin.nkn.uidaho.edu", "8002", "mixtral-8x7b-instruct-v0.1.Q4_K_M.gguf", question, is_json, temperature)
    
    def ask_question_sm3(question, is_json=False, temperature=0.7):
        return UILLM.ask_question_to_server("http://aurora.nkn.uidaho.edu", "8001", "mixtral-8x7b-instruct-v0.1.Q4_K_M.gguf", question, is_json, temperature)
    
    def ask_question_sm4(question, is_json=False, temperature=0.7):
        return UILLM.ask_question_to_server("http://aurora.nkn.uidaho.edu", "8002", "mixtral-8x7b-instruct-v0.1.Q4_K_M.gguf", question, is_json, temperature)
    
    def ask_question_to_server(server, port, model, question, is_json=False, temperature=0.7, max_tokens=3000):
        endpoint = server + ":" + port + "/v1/chat/completions"

        data = {
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": [
                {
                "role": "user", 
                "content": question
                }
            ]
        }

        if is_json:
            data["response_format"] = {"type": "json_object"}

        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer no-key" 
        }

        response = requests.post(endpoint, json=data, headers=headers)
        if response.status_code == 200:
            try:
                output = response.json()
                content = output["choices"][0]["message"]["content"]
                if content == None:
                    print("Failed on output: " + output)
                
                if is_json:
                    jsoncontent = json.loads(content)
                    return jsoncontent
                else:
                    return content    
            except json.JSONDecodeError:
                print("Invalid JSON format")
                print(output)
        else:
            print("SERVER ERROR")
            print(response.status_code)
            print(response.text)



    
