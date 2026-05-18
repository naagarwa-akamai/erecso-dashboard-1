import json
import requests
import time

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3"  # Change to your preferred model if needed
PROMPT_TEMPLATE = (
    "You are an expert incident management analyst. Analyze the ERECSO ticket details and linked ERE tickets below. "
    "Generate a comprehensive yet concise summary that a manager can quickly understand.\n\n"
    "INSTRUCTIONS:\n"
    "1. Extract the CORE ISSUE: What is the main problem or incident described?\n"
    "2. IMPACT ASSESSMENT: What was the customer/system impact? (e.g., service degradation, data loss, availability)\n"
    "3. ROOT CAUSE: What caused this issue? (from linked ticket details if available)\n"
    "4. RESOLUTION STATUS: Was it resolved? How? What was the workaround or fix?\n"
    "5. PREVENTION: What long-term or short-term actions are being taken to prevent recurrence?\n"
    "6. LINKED TICKETS: Identify the 2-3 most critical linked ERE tickets and explain their relationship to the main issue.\n\n"
    "REQUIRED OUTPUT FORMAT (3-4 sentences, ~150-200 words max):\n"
    "- Start with: '[INCIDENT TYPE] - [Brief 1-line description]'\n"
    "- Include: Impact, root cause (if known), resolution status, and key linked ticket types\n"
    "- End with: Prevention actions or recommended follow-ups\n"
    "- Use clear language avoiding jargon where possible\n\n"
    "ERECSO Ticket Detail :\n{erecso_description}\n\n"
    "Linked Ticket Details (PRIORITIZEDby relevance):\n{text}\n\n"
    "COMPREHENSIVE SUMMARY:")

ticket_details_path = "ticket_details.json"
linked_tickets_dict_path = "linked_tickets_dict.json"

with open(ticket_details_path, "r", encoding="utf-8") as f:
    erecso_tickets = json.load(f)

with open(linked_tickets_dict_path, "r", encoding="utf-8") as f:
    linked_tickets_dict = json.load(f)

def get_linked_ere_tickets(ticket):
    return [link["key"] for link in ticket.get("issue_links", []) if link["key"].startswith("ERE")]

def extract_erecso_ticket_details(ticket):
    """
    Extract comprehensive details from the main ERECSO ticket.
    """
    details = []
    ticket_id = ticket.get("ticket_id", "Unknown")
    details.append(f"Ticket ID: {ticket_id}")
    
    summary = ticket.get("summary", "")
    if summary:
        details.append(f"Summary: {summary}")
    
    issue_type = ticket.get("issue_type", "")
    if issue_type:
        details.append(f"Type: {issue_type}")
    
    status = ticket.get("status", "")
    if status:
        details.append(f"Status: {status}")
    
    priority = ticket.get("priority", "")
    if priority:
        details.append(f"Priority: {priority}")
    
    customer_impact = ticket.get("customer_impact", "")
    if customer_impact:
        details.append(f"Customer Impact: {customer_impact}")
    
    requesting_team = ticket.get("requesting_team", "")
    if requesting_team:
        details.append(f"Requesting Team: {requesting_team}")
    
    product_type = ticket.get("product_type", "")
    if product_type:
        details.append(f"Product: {product_type}")
    
    components = ticket.get("components", "")
    if components:
        details.append(f"Components: {components}")
    
    root_cause = ticket.get("root_cause", "")
    if root_cause:
        details.append(f"Root Cause: {root_cause}")
    
    resolution_description = ticket.get("resolution_description", "")
    if resolution_description:
        details.append(f"Resolution: {resolution_description}")
    
    workaround = ticket.get("workaround", "")
    if workaround:
        details.append(f"Workaround: {workaround}")
    
    longterm_mitigation = ticket.get("longterm_mitigation", "")
    if longterm_mitigation:
        details.append(f"Long-term Mitigation: {longterm_mitigation}")
    
    mitigation_plan = ticket.get("mitigation_plan", "")
    if mitigation_plan:
        details.append(f"Mitigation Plan: {mitigation_plan}")
    
    executive_summary = ticket.get("executive_summary", "")
    if executive_summary:
        details.append(f"Executive Summary: {executive_summary}")
    
    description = ticket.get("description", "")
    if description and len(description) > 500:
        details.append(f"Description (excerpt): {description[:500]}...")
    elif description:
        details.append(f"Description: {description}")
    
    labels = ticket.get("labels", [])
    if labels:
        labels_str = ", ".join(labels) if isinstance(labels, list) else str(labels)
        details.append(f"Labels/Tags: {labels_str}")
    
    return "\n".join(details)

def collect_text_for_summary(ticket, linked_tickets_dict, max_linked=3):
    texts = []
    count = 0
    for ere_key in get_linked_ere_tickets(ticket):
        ere = linked_tickets_dict.get(ere_key)
        if ere:
            summary = ere.get("summary", "")
            executive_summary = ere.get("executive_summary", "")
            root_cause = ere.get("root_cause", "")
            mitigation_plan = ere.get("mitigation_plan", "")
            ticket_type = ere.get("issue_type", "")
            ticket_info = []
            if summary:
                ticket_info.append(f"Summary: {summary}")
            if executive_summary:
                ticket_info.append(f"Executive Summary: {executive_summary}")
            if root_cause:
                ticket_info.append(f"Root Cause: {root_cause}")
            if mitigation_plan:
                ticket_info.append(f"Mitigation Plan: {mitigation_plan}")
            if ticket_type:
                ticket_info.append(f"Type: {ticket_type}")
            if ticket_info:
                texts.append("; ".join(ticket_info))
                count += 1
            if count >= max_linked:
                break
    return "\n".join(texts)

def generate_ai_summary(erecso_description, text):
    prompt = PROMPT_TEMPLATE.format(erecso_description=erecso_description, text=text)
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False
    }
    for _ in range(3):
        try:
            response = requests.post(OLLAMA_URL, json=payload, timeout=60)
            print(f"Ollama response status: {response.text}")
            if response.status_code == 200:
                result = response.json()
                return result.get("response", "")
            else:
                print(f"Ollama error: {response.status_code} {response.text}")
        except Exception as e:
            print(f"Ollama request failed: {e}")
        time.sleep(2)
    return "[AI summary unavailable]"

def main():
    minimal = []
    for ticket in erecso_tickets:
        erecso_details = extract_erecso_ticket_details(ticket)
        linked_text = collect_text_for_summary(ticket, linked_tickets_dict)
        if erecso_details.strip() or linked_text.strip():
            print(f"Generating AI summary for {ticket.get('ticket_id')}")
            ai_summary = generate_ai_summary(erecso_details, linked_text)
        else:
            ai_summary = "[No ticket details or linked ticket details found]"
        minimal.append({
            "ticket_id": ticket.get("ticket_id"),
            "ai_summary": ai_summary
        })
    with open("ticket_id_ai_summary.json", "w", encoding="utf-8") as f:
        json.dump(minimal, f, indent=2)
    print("Minimal AI summaries saved to ticket_id_ai_summary.json")

if __name__ == "__main__":
    main()
