
# API for monthly view AI summary from xyz.json

from flask import Flask, jsonify, render_template, request
from datetime import datetime, timedelta
from flask_cors import CORS
import json
import csv
import os
import re
import math
from collections import Counter
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
EXCLUDED_ERE_REQUEST_TYPES = {
    'ere-delivery-portal',
    'ere-msl-portal(temp)'
}
DEV_TICKET_PREFIXES = [
    'ORS-', 'CPSSRE-', 'MAPPINGENG-', 'SRMM-', 'DPEXREQ-',
    'EWDEVESC-', 'GDPM-', 'DXRE-', 'DBATTERY-', 'SECESC-','GREL-'
]

_TOKEN_PATTERN = re.compile(r'[a-z0-9]+')
_STOP_WORDS = {
    'the', 'and', 'for', 'with', 'from', 'that', 'this', 'have', 'has', 'had', 'are', 'was', 'were',
    'will', 'into', 'than', 'then', 'when', 'where', 'while', 'what', 'which', 'who', 'why', 'how',
    'not', 'can', 'could', 'should', 'would', 'about', 'after', 'before', 'during', 'under', 'over',
    'between', 'through', 'into', 'onto', 'also', 'only', 'very', 'more', 'less', 'there', 'their',
    'ticket', 'tickets', 'issue', 'issues', 'ere', 'erecso'
}


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


def get_ticket_key_sort_value(ticket_key):
    key_text = str(ticket_key or '').strip().upper()
    project_key, separator, key_suffix = key_text.partition('-')

    if separator and key_suffix.isdigit():
        return (project_key, int(key_suffix), key_text)

    return (project_key, float('inf'), key_text)


def tokenize_text(value):
    text = str(value or '').lower()
    tokens = _TOKEN_PATTERN.findall(text)
    return {token for token in tokens if len(token) > 2 and token not in _STOP_WORDS}


def tokenize_text_list(value):
    text = str(value or '').lower()
    tokens = _TOKEN_PATTERN.findall(text)
    return [token for token in tokens if len(token) > 2 and token not in _STOP_WORDS]


def build_bigrams(tokens):
    if len(tokens) < 2:
        return set()
    return {f"{tokens[i]} {tokens[i + 1]}" for i in range(len(tokens) - 1)}


def build_ticket_text(ticket):
    parts = [
        ticket.get('summary', ''),
        ticket.get('description', ''),
        ticket.get('root_cause', ''),
        ticket.get('resolution_description', ''),
        ticket.get('request_type', ''),
        ticket.get('product_type', ''),
        ticket.get('components', ''),
        ticket.get('account_name', ''),
        ticket.get('customer_name', ''),
        ticket.get('customer', '')
    ]
    return ' '.join(str(part) for part in parts if part)


def clean_summary_text(value):
    text = str(value or '').strip()
    if not text:
        return ''

    # Remove simple Jira/markdown artifacts and collapse whitespace.
    text = re.sub(r'\[[^\]]+\|https?://[^\]]+\]', '', text)
    text = re.sub(r'https?://\S+', '', text)
    text = text.replace('{code}', ' ').replace('{noformat}', ' ')
    text = re.sub(r'!([^!]+)!', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip(' -:;,.')


def shorten_text(text, max_chars=320):
    normalized = clean_summary_text(text)
    if len(normalized) <= max_chars:
        return normalized

    truncated = normalized[:max_chars].rsplit(' ', 1)[0].strip()
    return f"{truncated}..." if truncated else normalized[:max_chars]


def is_ticket_resolved(ticket):
    status_text = str(ticket.get('status', '') or '').strip().lower()
    resolved_status_text = str(ticket.get('resolved_status', '') or '').strip().lower()
    resolution_date = str(ticket.get('resolution_date', '') or '').strip()

    resolved_terms = {'resolved', 'closed', 'complete', 'completed', 'fixed', 'done'}
    if status_text in resolved_terms:
        return True
    if resolved_status_text in resolved_terms:
        return True
    return bool(resolution_date)


def build_short_ai_summary(ticket):
    resolved = is_ticket_resolved(ticket)

    summary = clean_summary_text(ticket.get('summary'))
    description = clean_summary_text(ticket.get('description'))
    executive_summary = clean_summary_text(ticket.get('executive_summary'))
    root_cause = clean_summary_text(ticket.get('root_cause'))
    resolution_description = clean_summary_text(ticket.get('resolution_description'))
    mitigation_plan = clean_summary_text(ticket.get('mitigation_plan'))
    longterm_mitigation = clean_summary_text(ticket.get('longterm_mitigation'))

    if resolved:
        parts = []
        if executive_summary:
            parts.append(f"Summary: {executive_summary}")
        elif summary:
            parts.append(f"Summary: {summary}")

        if root_cause:
            parts.append(f"Root cause: {root_cause}")

        resolution_text = resolution_description or description
        if resolution_text:
            parts.append(f"Resolution: {resolution_text}")

        mitigation_text = mitigation_plan or longterm_mitigation
        if mitigation_text:
            parts.append(f"Mitigation: {mitigation_text}")

        if not parts and summary:
            parts.append(f"Summary: {summary}")

        return shorten_text(' | '.join(parts), max_chars=420)

    # Non-resolved: rely on summary + description only.
    non_resolved_parts = []
    if summary:
        non_resolved_parts.append(f"Summary: {summary}")
    if description:
        non_resolved_parts.append(f"Context: {description}")

    if not non_resolved_parts:
        return '-'

    return shorten_text(' | '.join(non_resolved_parts), max_chars=320)


def build_idf_index(tickets):
    doc_count = 0
    token_doc_freq = Counter()

    for ticket in tickets:
        token_set = tokenize_text(build_ticket_text(ticket))
        if not token_set:
            continue
        doc_count += 1
        token_doc_freq.update(token_set)

    if doc_count == 0:
        return {}

    idf_index = {}
    for token, freq in token_doc_freq.items():
        # Smoothed IDF
        idf_index[token] = math.log((doc_count + 1) / (freq + 1)) + 1.0

    return idf_index


def score_ticket_similarity(ere_ticket, erecso_candidate, idf_index=None):
    ere_text = build_ticket_text(ere_ticket)
    erecso_text = build_ticket_text(erecso_candidate)

    ere_tokens = tokenize_text(ere_text)
    erecso_tokens = tokenize_text(erecso_text)

    if not ere_tokens or not erecso_tokens:
        return 0.0

    overlap = ere_tokens.intersection(erecso_tokens)

    # IDF-weighted overlap gives more importance to rarer, discriminative terms.
    if idf_index:
        overlap_weight = sum(idf_index.get(token, 1.0) for token in overlap)
        total_weight = sum(idf_index.get(token, 1.0) for token in ere_tokens)
        token_overlap_score = (overlap_weight / total_weight) if total_weight else 0.0
    else:
        token_overlap_score = len(overlap) / max(len(ere_tokens), 1)

    ere_bigrams = build_bigrams(tokenize_text_list(ere_text))
    erecso_bigrams = build_bigrams(tokenize_text_list(erecso_text))
    bigram_overlap_score = 0.0
    if ere_bigrams and erecso_bigrams:
        bigram_overlap = ere_bigrams.intersection(erecso_bigrams)
        bigram_overlap_score = len(bigram_overlap) / max(len(ere_bigrams), 1)

    ere_component = str(ere_ticket.get('components', '') or '').strip().lower()
    erecso_component = str(erecso_candidate.get('components', '') or '').strip().lower()
    component_bonus = 0.15 if ere_component and ere_component == erecso_component else 0.0

    ere_product = str(ere_ticket.get('product_type', '') or '').strip().lower()
    erecso_product = str(erecso_candidate.get('product_type', '') or '').strip().lower()
    product_bonus = 0.10 if ere_product and ere_product == erecso_product else 0.0

    ere_req_type = str(ere_ticket.get('request_type', '') or '').strip().lower()
    erecso_req_type = str(erecso_candidate.get('request_type', '') or '').strip().lower()
    request_type_bonus = 0.10 if ere_req_type and ere_req_type == erecso_req_type else 0.0

    ere_account = normalize_feature_value(
        ere_ticket.get('account_name') or ere_ticket.get('account') or ere_ticket.get('customer') or ere_ticket.get('customer_name')
    )
    erecso_account = normalize_feature_value(
        erecso_candidate.get('account_name') or erecso_candidate.get('account') or erecso_candidate.get('customer') or erecso_candidate.get('customer_name')
    )
    account_bonus = 0.12 if ere_account and ere_account == erecso_account else 0.0

    recency_bonus = 0.0
    ere_created = parse_datetime_value(ere_ticket.get('created'))
    erecso_created = parse_datetime_value(erecso_candidate.get('created'))
    if ere_created and erecso_created:
        day_diff = abs((ere_created.date() - erecso_created.date()).days)
        if day_diff <= 14:
            recency_bonus = 0.08
        elif day_diff <= 45:
            recency_bonus = 0.04

    lexical_score = (0.78 * token_overlap_score) + (0.22 * bigram_overlap_score)

    score = min(
        1.0,
        lexical_score + component_bonus + product_bonus + request_type_bonus + account_bonus + recency_bonus
    )
    return round(score, 4)


def build_candidate_shortlist(ere_ticket, erecso_candidates, history_index=None, max_candidates=60):
    ere_req_type = normalize_feature_value(ere_ticket.get('request_type'))
    ere_product = normalize_feature_value(ere_ticket.get('product_type'))
    ere_component = normalize_feature_value(ere_ticket.get('components') or ere_ticket.get('component'))
    ere_tokens = tokenize_text(build_ticket_text(ere_ticket))

    scored = []
    for candidate in erecso_candidates:
        cid = str(candidate.get('ticket_id', '') or '').strip().upper()
        c_req_type = normalize_feature_value(candidate.get('request_type'))
        c_product = normalize_feature_value(candidate.get('product_type'))
        c_component = normalize_feature_value(candidate.get('components') or candidate.get('component'))
        c_tokens = tokenize_text(build_ticket_text(candidate))

        coarse = 0.0
        if ere_req_type and ere_req_type == c_req_type:
            coarse += 2.0
        if ere_product and ere_product == c_product:
            coarse += 1.2
        if ere_component and ere_component == c_component:
            coarse += 1.2

        if ere_tokens and c_tokens:
            overlap = ere_tokens.intersection(c_tokens)
            coarse += min(1.0, len(overlap) / 8.0)

        profile = (history_index or {}).get(cid, {})
        coarse += min(1.0, profile.get('linked_count', 0) / 10.0)

        scored.append((coarse, candidate))

    scored.sort(key=lambda item: item[0], reverse=True)
    shortlisted = [candidate for _, candidate in scored[:max_candidates]]

    if not shortlisted:
        return erecso_candidates
    return shortlisted


def extract_linked_erecso_keys(ticket):
    issue_links = ticket.get('issue_links', [])
    if not isinstance(issue_links, list):
        return []

    linked_keys = []
    for link in issue_links:
        if not isinstance(link, dict):
            continue
        link_key = str(link.get('key', '') or '').strip().upper()
        if link_key.startswith('ERECSO-'):
            linked_keys.append(link_key)

    return linked_keys


def normalize_feature_value(value):
    return str(value or '').strip().lower()


def build_erecso_history_index(ere_tickets, erecso_candidates):
    candidate_ids = {
        str(candidate.get('ticket_id', '') or '').strip().upper()
        for candidate in erecso_candidates
    }

    history_index = {
        candidate_id: {
            'linked_count': 0,
            'token_counter': Counter(),
            'request_type_counter': Counter(),
            'product_type_counter': Counter(),
            'component_counter': Counter(),
            'account_counter': Counter()
        }
        for candidate_id in candidate_ids
    }

    for ere_ticket in ere_tickets:
        ticket_id = str(ere_ticket.get('ticket_id', '') or '').strip().upper()
        if not ticket_id.startswith('ERE-'):
            continue

        linked_erecso_keys = [
            key for key in extract_linked_erecso_keys(ere_ticket)
            if key in history_index
        ]
        if not linked_erecso_keys:
            continue

        ticket_tokens = tokenize_text(build_ticket_text(ere_ticket))
        request_type = normalize_feature_value(ere_ticket.get('request_type'))
        product_type = normalize_feature_value(ere_ticket.get('product_type'))
        component = normalize_feature_value(ere_ticket.get('components') or ere_ticket.get('component'))
        account = normalize_feature_value(
            ere_ticket.get('account_name') or ere_ticket.get('account') or ere_ticket.get('customer') or ere_ticket.get('customer_name')
        )

        for linked_key in linked_erecso_keys:
            profile = history_index[linked_key]
            profile['linked_count'] += 1
            profile['token_counter'].update(ticket_tokens)

            if request_type:
                profile['request_type_counter'][request_type] += 1
            if product_type:
                profile['product_type_counter'][product_type] += 1
            if component:
                profile['component_counter'][component] += 1
            if account:
                profile['account_counter'][account] += 1

    max_linked_count = max(
        (profile['linked_count'] for profile in history_index.values()),
        default=0
    )

    return history_index, max_linked_count


def score_with_history_profile(ere_ticket, history_profile, max_linked_count):
    if not history_profile or history_profile.get('linked_count', 0) == 0:
        return 0.0

    ticket_tokens = tokenize_text(build_ticket_text(ere_ticket))
    token_counter = history_profile.get('token_counter', Counter())
    total_token_weight = sum(token_counter.values())
    token_match_weight = sum(token_counter.get(token, 0) for token in ticket_tokens)
    token_score = (token_match_weight / total_token_weight) if total_token_weight else 0.0

    request_type = normalize_feature_value(ere_ticket.get('request_type'))
    product_type = normalize_feature_value(ere_ticket.get('product_type'))
    component = normalize_feature_value(ere_ticket.get('components') or ere_ticket.get('component'))
    account = normalize_feature_value(
        ere_ticket.get('account_name') or ere_ticket.get('account') or ere_ticket.get('customer') or ere_ticket.get('customer_name')
    )

    request_type_score = 0.12 if request_type and request_type in history_profile.get('request_type_counter', {}) else 0.0
    product_type_score = 0.10 if product_type and product_type in history_profile.get('product_type_counter', {}) else 0.0
    component_score = 0.10 if component and component in history_profile.get('component_counter', {}) else 0.0
    account_score = 0.08 if account and account in history_profile.get('account_counter', {}) else 0.0

    prior_score = 0.0
    if max_linked_count > 0:
        prior_score = 0.10 * (history_profile.get('linked_count', 0) / max_linked_count)

    return min(1.0, token_score + request_type_score + product_type_score + component_score + account_score + prior_score)


def get_match_confidence(score):
    if score >= 0.50:
        return 'High'
    if score >= 0.30:
        return 'Medium'
    return 'Low'


def predict_related_erecso_tickets(ere_ticket, erecso_candidates, history_index=None, max_linked_count=0, top_k=3, idf_index=None):
    ranked_matches = []

    candidate_pool = build_candidate_shortlist(
        ere_ticket,
        erecso_candidates,
        history_index=history_index,
        max_candidates=60
    )

    for candidate in candidate_pool:
        candidate_id = str(candidate.get('ticket_id', '') or '').strip().upper()
        semantic_score = score_ticket_similarity(ere_ticket, candidate, idf_index=idf_index)
        history_profile = (history_index or {}).get(candidate_id)
        history_score = score_with_history_profile(ere_ticket, history_profile, max_linked_count)

        # Hybrid score: blend semantic similarity with historical ERE->ERECSO link patterns
        score = (0.52 * semantic_score) + (0.48 * history_score)
        score = round(score, 4)

        ranked_matches.append({
            'ticket_id': candidate.get('ticket_id', ''),
            'score': score,
            'confidence': get_match_confidence(score)
        })

    ranked_matches.sort(
        key=lambda item: (-item.get('score', 0), get_ticket_key_sort_value(item.get('ticket_id')))
    )
    return ranked_matches[:max(int(top_k or 0), 0)]


def predict_related_erecso_ticket(ere_ticket, erecso_candidates, history_index=None, max_linked_count=0, idf_index=None):
    top_matches = predict_related_erecso_tickets(
        ere_ticket,
        erecso_candidates,
        history_index=history_index,
        max_linked_count=max_linked_count,
        top_k=1,
        idf_index=idf_index
    )
    return top_matches[0] if top_matches else None


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
        updates = request.get_json(silent=True)
        if not isinstance(updates, list):
            return jsonify({"error": "Expected a list of ticket updates"}), 400

        if not os.path.exists(JSON_FILE_PATH):
            return jsonify({"error": "JSON file not found"}), 404

        with open(JSON_FILE_PATH, 'r', encoding='utf-8') as file:
            ticket_details = json.load(file)

        flag_updates = {}
        for item in updates:
            if not isinstance(item, dict):
                continue
            ticket_id = str(item.get('ticket_id', '')).strip()
            if not ticket_id:
                continue
            flag_updates[ticket_id] = item.get('flag', '-')

        updated_count = 0
        for ticket in ticket_details:
            ticket_id = str(ticket.get('ticket_id', '')).strip()
            if ticket_id in flag_updates:
                ticket['flag'] = flag_updates[ticket_id]
                updated_count += 1

        with open(JSON_FILE_PATH, 'w', encoding='utf-8') as file:
            json.dump(ticket_details, file, indent=4, ensure_ascii=False)

        return jsonify({
            "message": "Ticket details updated successfully!",
            "updated_count": updated_count
        }), 200

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


@app.route('/api/ere-escalation-tickets', methods=['GET'])
def get_ere_escalation_tickets():
    try:
        if not os.path.exists(ERESUSTENANCE_JSON_FILE_PATH):
            return jsonify({"error": "Sustenance JSON file not found"}), 404
        if not os.path.exists(JSON_FILE_PATH):
            return jsonify({"error": "ERECSO JSON file not found"}), 404

        from_date_text = str(request.args.get('from_date', '') or '').strip()
        to_date_text = str(request.args.get('to_date', '') or '').strip()

        from_date = None
        to_date = None

        if from_date_text:
            try:
                from_date = datetime.strptime(from_date_text, '%Y-%m-%d').date()
            except ValueError:
                return jsonify({"error": "Invalid from_date. Use YYYY-MM-DD format."}), 400

        if to_date_text:
            try:
                to_date = datetime.strptime(to_date_text, '%Y-%m-%d').date()
            except ValueError:
                return jsonify({"error": "Invalid to_date. Use YYYY-MM-DD format."}), 400

        if from_date and to_date and from_date > to_date:
            return jsonify({"error": "from_date cannot be greater than to_date."}), 400

        with open(ERESUSTENANCE_JSON_FILE_PATH, 'r', encoding='utf-8') as file:
            sustenance_ticket_details = json.load(file)

        with open(JSON_FILE_PATH, 'r', encoding='utf-8') as file:
            erecso_ticket_details = json.load(file)

        erecso_candidates = [
            candidate for candidate in erecso_ticket_details
            if str(candidate.get('ticket_id', '') or '').strip().upper().startswith('ERECSO-')
        ]
        history_index, max_linked_count = build_erecso_history_index(sustenance_ticket_details, erecso_candidates)
        idf_index = build_idf_index(sustenance_ticket_details + erecso_candidates)

        filtered_tickets = []
        for ticket in sustenance_ticket_details:
            ticket_id = str(ticket.get('ticket_id', '') or '').strip().upper()
            if not ticket_id.startswith('ERE-'):
                continue

            request_type = str(ticket.get('request_type', '') or '').strip().lower()
            if request_type in EXCLUDED_ERE_REQUEST_TYPES:
                continue

            created_dt = parse_datetime_value(ticket.get('created'))
            if not created_dt:
                continue

            created_date = created_dt.date()
            if from_date and created_date < from_date:
                continue
            if to_date and created_date > to_date:
                continue

            linked_erecso_key = ''
            linked_erecso_keys = extract_linked_erecso_keys(ticket)
            if linked_erecso_keys:
                linked_erecso_key = linked_erecso_keys[0]

            predicted_erecso = None
            predicted_erecso_candidates = []
            if not linked_erecso_key:
                predicted_erecso_candidates = predict_related_erecso_tickets(
                    ticket,
                    erecso_candidates,
                    history_index=history_index,
                    max_linked_count=max_linked_count,
                    top_k=3,
                    idf_index=idf_index
                )
                predicted_erecso = predicted_erecso_candidates[0] if predicted_erecso_candidates else None

            matched_ticket_key = linked_erecso_key or (predicted_erecso or {}).get('ticket_id', '')
            matched_ticket_key = str(matched_ticket_key or '').strip().upper()
            matched_ticket_url = f"https://track.akamai.com/jira/browse/{matched_ticket_key}" if matched_ticket_key else ''
            match_type = 'linked' if linked_erecso_key else ('predicted' if matched_ticket_key else 'none')
            match_confidence = 'Linked' if linked_erecso_key else (predicted_erecso or {}).get('confidence', '')
            match_score = (predicted_erecso or {}).get('score') if not linked_erecso_key else None

            filtered_tickets.append({
                'ticket_id': ticket.get('ticket_id', ''),
                'created': created_dt.strftime('%Y-%m-%d'),
                'status': ticket.get('status', ''),
                'request_type': ticket.get('request_type', ''),
                'summary': ticket.get('summary', ''),
                'ai_summary': build_short_ai_summary(ticket),
                'assignee': ticket.get('assignee', ''),
                'issue_url': f"https://track.akamai.com/jira/browse/{ticket.get('ticket_id', '')}",
                'matched_erecso_ticket_id': matched_ticket_key,
                'matched_erecso_ticket_url': matched_ticket_url,
                'matched_erecso_match_type': match_type,
                'matched_erecso_confidence': match_confidence,
                'matched_erecso_score': match_score,
                'matched_erecso_candidates': predicted_erecso_candidates
            })

        filtered_tickets.sort(key=lambda item: get_ticket_key_sort_value(item.get('ticket_id')))
        return jsonify(filtered_tickets), 200

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
            timeout=6000
        )
    except subprocess.TimeoutExpired:
        return jsonify({"error": "Data refresh timed out after 100 minutes"}), 504
    except Exception as e:
        return jsonify({"error": f"Failed to start refresh: {str(e)}"}), 500

    if result.returncode != 0:
        return jsonify({
            "error": "Data refresh failed",
            "details": (result.stderr or result.stdout or '').strip()
        }), 500

    return jsonify({
        "message": "Data refreshed successfully",
        "refreshed_at": datetime.now().isoformat(timespec='seconds'),
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