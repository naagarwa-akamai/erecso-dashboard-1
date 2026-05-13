
# API for monthly view AI summary from xyz.json

from flask import Flask, jsonify, render_template, request
from datetime import datetime
from flask_cors import CORS
import json
import csv
import os
import requests

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Define the path to the CSV file
JSON_FILE_PATH = './ticket_details.json'
AI_SUMMARY_FILE_PATH = './ticket_id_ai_summary.json'
GURU_TICKETS=[]

LINKED_TICKET_DICT_FILE = './linked_tickets_dict.json'



@app.route('/api/monthly-ai-summary/<ticket_id>', methods=['GET'])
def get_monthly_ai_summary(ticket_id):
    xyz_path = './xyz.json'
    selected_month = request.args.get('month', None)
    if not os.path.exists(xyz_path):
        return jsonify({'error': 'xyz.json not found'}), 404
    try:
        with open(xyz_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        # Filter by both ticket_id and month (as string for consistency)
        for entry in data:
            if entry.get('ticket_id') == ticket_id and (selected_month is None or str(entry.get('month')) == str(selected_month)):
                return jsonify({
                    'outcome': entry.get('outcome', '-'),
                    'progressive_work': entry.get('progressive_work', '-'),
                    'patterns_trends': entry.get('patterns_trends', '-')
                })
        return jsonify({'outcome': '-', 'progressive_work': '-', 'patterns_trends': '-'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/linked-tickets', methods=['GET'])
def get_linked_tickets():
    """
    API endpoint to fetch the linked ticket dictionary.
    """
    if not os.path.exists(LINKED_TICKET_DICT_FILE):
        return jsonify({"error": f"The file {LINKED_TICKET_DICT_FILE} does not exist."}), 404

    try:
        # Load the JSON file
        with open(LINKED_TICKET_DICT_FILE, 'r', encoding='utf-8') as file:
            linked_ticket_dict = json.load(file)
        return jsonify(linked_ticket_dict), 200
    except json.JSONDecodeError:
        return jsonify({"error": f"Failed to decode JSON from {LINKED_TICKET_DICT_FILE}."}), 500
# --------------------------------------------------------------------------------------------------------
@app.route('/api/tickets', methods=['GET'])
def get_ticket_details():
    try:
        # Check if the JSON file exists
        if not os.path.exists(JSON_FILE_PATH):
            return jsonify({"error": "JSON file not found"}), 404

        # Read the JSON file
        with open(JSON_FILE_PATH, 'r') as file:
            ticket_details = json.load(file)

        # Merge AI summaries
        ai_summaries = {}
        if os.path.exists(AI_SUMMARY_FILE_PATH):
            with open(AI_SUMMARY_FILE_PATH, 'r', encoding='utf-8') as f:
                for entry in json.load(f):
                    ai_summaries[entry['ticket_id']] = entry.get('ai_summary', "")
        for ticket in ticket_details:
            tid = ticket.get('ticket_id')
            if tid in ai_summaries:
                ticket['ai_summary'] = ai_summaries[tid]

        # Return the JSON data as a response
        return jsonify(ticket_details), 200

    except Exception as e:
        # Handle any errors that occur
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500



# --------------------------------------------------------------------------------------------------------

@app.route('/api/update-ticket', methods=['POST'])
def update_ticket_details():
    try:
        # Get the updated data from the request
        updated_data = request.get_json()

        # Save the updated data to the JSON file
        # with open(JSON_FILE_PATH, 'w', encoding='utf-8') as file:
        #     json.dump(updated_data, file, indent=4)

        return jsonify({"message": "Ticket details updated successfully!"}), 200

    except Exception as e:
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500
# --------------------------------------------------------------------------------------------------------

    
    
# --------------------------------------------------------------------------------------------------------

  
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
@app.route('/')
def index():
    return render_template('/index.html')

@app.route('/ere-sustenance')
def ere_sustenance():
    return render_template('ere_sustenance.html')

if __name__ == "__main__":
    app.run(host="0.0.0.0" ,port=2000,debug=True)