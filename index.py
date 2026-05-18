
# API for monthly view AI summary from xyz.json

from flask import Flask, jsonify, render_template, request
from datetime import datetime, timedelta
from flask_cors import CORS
import json
import csv
import os
import subprocess
import sys
import requests
import google.auth
from google.oauth2 import service_account
from googleapiclient.discovery import build

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Define the path to the CSV file
JSON_FILE_PATH = './ticket_details.json'
AI_SUMMARY_FILE_PATH = './ticket_id_ai_summary.json'
GURU_TICKETS=[]

LINKED_TICKET_DICT_FILE = './linked_tickets_dict.json'
ERESUSTENANCE_JSON_FILE_PATH = './ere_sustenance_ticket_details.json'
ERESUSTENANCE_SREINC_JSON_FILE_PATH = './ere_sustenance_ticket_details_sreinc.json'
GOOGLE_SERVICE_ACCOUNT_FILE = './google_service_account.json'
GSHEETS_SPREADSHEET_ID = '1d3uheG-wxBEm6jS9UDGb_z95wjDn3QrbEn7iQilYvn8'
GSHEETS_EXPORT_SPREADSHEET_ID = '1Cgv7kG44zOg2GxZOVecTSFzq0Zx59hTqsqgezHTsJug'
GSHEETS_SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
GSHEETS_DEFAULT_TAB = 'ERE AI Agent Registry'
GSHEETS_TOIL_TAB = 'Toil Activity Tracker'
GSHEETS_EXPORT_TAB = 'ERE Sustenance Export'
DEV_TICKET_PREFIXES = [
    'ORS-', 'CPSSRE-', 'MAPPINGENG-', 'SRMM-', 'DPEXREQ-',
    'EWDEVESC-', 'GDPM-', 'DXRE-', 'DBATTERY-', 'SECESC-','GREL-'
]


def parse_datetime_value(value):
    if not value:
        return None

    text = str(value).strip()
    if not text:
        return None

    candidates = [text]
    if text.endswith('Z'):
        candidates.append(text[:-1] + '+00:00')

    for candidate in candidates:
        try:
            return datetime.fromisoformat(candidate)
        except ValueError:
            continue

    return None


def format_export_date_only(value):
    parsed = parse_datetime_value(value)
    if not parsed:
        return ''
    return parsed.strftime('%Y-%m-%d')


def get_product_breakdown_category(product_type):
    value = str(product_type or '').strip().lower()

    if 'api' in value and 'acceleration' in value:
        return 'API-X'
    if 'provision' in value:
        return 'Provisioning Services'
    if 'internal' in value:
        return 'ERE-Internal-Use'
    if value in {'amd', 'dd', 'od', 'ere-amd', 'ere-dd', 'ere-od'}:
        return 'Media Delivery - AMD/DD/OD'
    if value in {'ion', 'dsa', 'ere-ion', 'ere-dsa'}:
        return 'App Perf - ION/DSA'

    return 'Others'


def ensure_sheet_tab(service, spreadsheet_id, sheet_title):
    metadata = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    sheets = metadata.get('sheets', [])

    for sheet in sheets:
        props = sheet.get('properties', {})
        if props.get('title') == sheet_title:
            return

    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={
            'requests': [
                {
                    'addSheet': {
                        'properties': {
                            'title': sheet_title
                        }
                    }
                }
            ]
        }
    ).execute()


def build_unique_export_sheet_title(service, spreadsheet_id, base_title):
    metadata = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    sheets = metadata.get('sheets', [])
    existing_titles = {
        sheet.get('properties', {}).get('title', '')
        for sheet in sheets
    }

    timestamp = datetime.now().strftime('%Y-%m-%d %H-%M-%S')
    candidate = f"{base_title} {timestamp}"
    if candidate not in existing_titles:
        return candidate

    suffix = 2
    while True:
        candidate = f"{base_title} {timestamp} ({suffix})"
        if candidate not in existing_titles:
            return candidate
        suffix += 1


def get_exportable_sustenance_tickets(selected_month=None):
    if not os.path.exists(ERESUSTENANCE_JSON_FILE_PATH):
        return []

    with open(ERESUSTENANCE_JSON_FILE_PATH, 'r', encoding='utf-8') as file:
        sustenance_tickets = json.load(file)

    month_number = None
    if selected_month not in (None, '', 'all'):
        try:
            month_number = int(selected_month)
        except (TypeError, ValueError):
            month_number = None

    exported_rows = []
    for ticket in sustenance_tickets:
        request_type = str(ticket.get('request_type', '')).lower().strip()
        if not request_type:
            continue
        if 'ere-ghost' in request_type:
            continue
        if 'new feature' in request_type:
            continue
        if 'unknown' in request_type:
            continue

        created_dt = parse_datetime_value(ticket.get('created'))
        if not created_dt:
            continue

        if month_number and created_dt.month != month_number:
            continue

        issue_links = ticket.get('issue_links', [])
        dev_ticket_keys = []
        if isinstance(issue_links, list):
            for link in issue_links:
                if not isinstance(link, dict):
                    continue
                link_key = str(link.get('key', '')).upper().strip()
                if any(link_key.startswith(prefix) for prefix in DEV_TICKET_PREFIXES):
                    dev_ticket_keys.append(link_key)

        time_spent_seconds = ticket.get('timespent')
        try:
            time_spent_seconds = int(float(str(time_spent_seconds).strip())) if str(time_spent_seconds).strip() else 0
        except (TypeError, ValueError):
            time_spent_seconds = 0

        time_spent_hours = round(time_spent_seconds / 3600, 2) if time_spent_seconds else 0
        fte_value = round(time_spent_hours / 40, 4) if time_spent_hours else 0
        incident_priority = str(ticket.get('priority', '')).strip().lower() in {'high', 'critical'}
        service_incident = ticket.get('service_incident')
        incident_flag = 'Yes' if (service_incident not in (None, '', '-', False) or incident_priority) else 'No'
        product_type = ticket.get('product_type', '')

        exported_rows.append({
            'Issue Key': ticket.get('ticket_id', ''),
            'Status': ticket.get('status', ''),
            'Priority': ticket.get('priority', ''),
            'Created Date': created_dt.strftime('%Y-%m-%d'),
            'Incident/High Priority ?': incident_flag,
            'Product Type': product_type,
            'Account Name': ticket.get('account_name') or ticket.get('account') or ticket.get('customer') or ticket.get('customer_name') or '',
            'Summary': ticket.get('summary', ''),
            'Issue summary post review': ticket.get('executive_summary') or ticket.get('resolution_description') or ticket.get('longterm_mitigation') or ticket.get('root_cause') or '',
            'Custom field (Requesting Team)': ticket.get('requesting_team', ''),
            'Request Type': ticket.get('request_type', ''),
            'Assignee': ticket.get('assignee', ''),
            'Reporter': ticket.get('reporter', ''),
            'Service Incident': service_incident if service_incident not in (None, '') else '',
            'Time Spent (sec)': str(time_spent_seconds) if time_spent_seconds else '',
            'FTE (no of hours/40)': f'{fte_value:.4f}' if fte_value else '',
            'Time spent in hours': f'{time_spent_hours:.2f}' if time_spent_hours else '',
            'Component': ticket.get('components') or ticket.get('component') or '',
            'ERECSO': ticket.get('flag', ''),
            'DEV TICKETS': ', '.join(dev_ticket_keys),
            'Product Breakdown': get_product_breakdown_category(product_type or ticket.get('request_type', ''))
        })

    return exported_rows



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

@app.route('/api/ere-sustenance-tickets', methods=['GET'])
def get_ere_sustenance_ticket_details():
    try:
        if not os.path.exists(ERESUSTENANCE_JSON_FILE_PATH):
            return jsonify({"error": "Sustenance JSON file not found"}), 404

        with open(ERESUSTENANCE_JSON_FILE_PATH, 'r', encoding='utf-8') as file:
            sustenance_ticket_details = json.load(file)

        return jsonify(sustenance_ticket_details), 200

    except Exception as e:
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500


@app.route('/api/ere-sustenance-tickets-sreinc', methods=['GET'])
def get_ere_sustenance_sreinc_ticket_details():
    try:
        if not os.path.exists(ERESUSTENANCE_SREINC_JSON_FILE_PATH):
            return jsonify({"error": "SREINC sustenance JSON file not found"}), 404

        with open(ERESUSTENANCE_SREINC_JSON_FILE_PATH, 'r', encoding='utf-8') as file:
            sreinc_ticket_details = json.load(file)

        return jsonify(sreinc_ticket_details), 200

    except Exception as e:
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

# --------------------------------------------------------------------------------------------------------

    
    
# --------------------------------------------------------------------------------------------------------

  
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
@app.route('/api/gsheet-initiatives', methods=['GET'])
def get_gsheet_initiatives():
    try:
        sheet_range = request.args.get('range')
        sheet_gid = request.args.get('gid')
        creds = service_account.Credentials.from_service_account_file(
            GOOGLE_SERVICE_ACCOUNT_FILE,
            scopes=GSHEETS_SCOPES
        )
        service = build('sheets', 'v4', credentials=creds)

        # If range is not explicitly provided, resolve sheet title by gid first,
        # then fall back to the first available tab.
        if not sheet_range and not sheet_gid:
            sheet_range = f"'{GSHEETS_DEFAULT_TAB}'"

        if not sheet_range:
            metadata = service.spreadsheets().get(
                spreadsheetId=GSHEETS_SPREADSHEET_ID
            ).execute()
            sheets = metadata.get('sheets', [])

            if not sheets:
                return jsonify({"error": "No sheets found in spreadsheet"}), 404

            resolved_title = None
            if sheet_gid:
                for sheet in sheets:
                    props = sheet.get('properties', {})
                    if str(props.get('sheetId')) == str(sheet_gid):
                        resolved_title = props.get('title')
                        break

            if not resolved_title:
                resolved_title = sheets[0].get('properties', {}).get('title')

            if not resolved_title:
                return jsonify({"error": "Unable to resolve sheet title"}), 400

            sheet_range = f"'{resolved_title}'"

        result = service.spreadsheets().values().get(
            spreadsheetId=GSHEETS_SPREADSHEET_ID,
            range=sheet_range
        ).execute()
        rows = result.get('values', [])
        if not rows:
            return jsonify([]), 200
        headers = rows[0]
        data = [dict(zip(headers, row)) for row in rows[1:]]
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/gsheet-toil-activity', methods=['GET'])
def get_gsheet_toil_activity():
    try:
        sheet_range = request.args.get('range', f"'{GSHEETS_TOIL_TAB}'")
        creds = service_account.Credentials.from_service_account_file(
            GOOGLE_SERVICE_ACCOUNT_FILE,
            scopes=GSHEETS_SCOPES
        )
        service = build('sheets', 'v4', credentials=creds)

        result = service.spreadsheets().values().get(
            spreadsheetId=GSHEETS_SPREADSHEET_ID,
            range=sheet_range
        ).execute()
        rows = result.get('values', [])
        if not rows:
            return jsonify([]), 200

        headers = rows[0]
        data = [dict(zip(headers, row)) for row in rows[1:]]
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/export-ere-sustenance-table', methods=['POST'])
def export_ere_sustenance_table():
    try:
        payload = request.get_json(silent=True) or {}
        selected_month = payload.get('selectedMonth')

        rows = get_exportable_sustenance_tickets(selected_month)
        if not rows:
            return jsonify({"error": "No sustenance tickets available to export"}), 400

        creds = service_account.Credentials.from_service_account_file(
            GOOGLE_SERVICE_ACCOUNT_FILE,
            scopes=GSHEETS_SCOPES
        )
        service = build('sheets', 'v4', credentials=creds)

        sheet_title = build_unique_export_sheet_title(service, GSHEETS_EXPORT_SPREADSHEET_ID, GSHEETS_EXPORT_TAB)

        created_sheet = service.spreadsheets().batchUpdate(
            spreadsheetId=GSHEETS_EXPORT_SPREADSHEET_ID,
            body={
                'requests': [
                    {
                        'addSheet': {
                            'properties': {
                                'title': sheet_title
                            }
                        }
                    }
                ]
            }
        ).execute()

        new_sheet_props = created_sheet.get('replies', [{}])[0].get('addSheet', {}).get('properties', {})
        new_sheet_gid = new_sheet_props.get('sheetId')

        headers = list(rows[0].keys())
        values = [headers] + [[row.get(header, '') for header in headers] for row in rows]

        service.spreadsheets().values().update(
            spreadsheetId=GSHEETS_EXPORT_SPREADSHEET_ID,
            range=f"'{sheet_title}'!A1",
            valueInputOption='RAW',
            body={'values': values}
        ).execute()

        return jsonify({
            'message': 'Exported sustenance table successfully',
            'rows_exported': len(rows),
            'sheet_title': sheet_title,
            'sheet_url': f"https://docs.google.com/spreadsheets/d/{GSHEETS_EXPORT_SPREADSHEET_ID}/edit#gid={new_sheet_gid}"
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/refresh-monthly-data', methods=['POST'])
def refresh_monthly_data():
    script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'monthlyticketdatastore.py')

    if not os.path.exists(script_path):
        return jsonify({"error": "monthlyticketdatastore.py not found"}), 404

    try:
        result = subprocess.run(
            [sys.executable, script_path],
            cwd=os.path.dirname(script_path),
            capture_output=True,
            text=True,
            timeout=600
        )
    except subprocess.TimeoutExpired:
        return jsonify({"error": "Data refresh timed out after 10 minutes"}), 504
    except Exception as e:
        return jsonify({"error": f"Failed to start refresh: {str(e)}"}), 500

    if result.returncode != 0:
        return jsonify({
            "error": "Data refresh failed",
            "details": (result.stderr or result.stdout or '').strip()
        }), 500

    return jsonify({
        "message": "Data refreshed successfully",
        "output": (result.stdout or '').strip()
    }), 200

@app.route('/')
def index():
    return render_template('/index.html')

@app.route('/ere-sustenance')
def ere_sustenance():
    return render_template('ere_sustenance.html')

if __name__ == "__main__":
    app.run(host="0.0.0.0" ,port=2100,debug=True)