import json
import requests
import time

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3"  # Change to your preferred model if needed
PROMPT_TEMPLATE = (
    "Using the description of the main ERECSO ticket and the details of its linked ERE tickets, "
    "write a 2-line introduction or summary for this ERECSO ticket. "
    "The summary should explain what this ERECSO ticket is about, what type of tickets are linked to it, "
    "and provide a brief summary of 2-3 of the most relevant linked tickets.\n\n"
    "ERECSO Description: {erecso_description}\n"
    "Linked Ticket Details:\n{text}\n\nSummary:")

ticket_details_path = "ticket_details.json"
linked_tickets_dict_path = "linked_tickets_dict.json"

with open(ticket_details_path, "r", encoding="utf-8") as f:
    erecso_tickets = json.load(f)

with open(linked_tickets_dict_path, "r", encoding="utf-8") as f:
    linked_tickets_dict = json.load(f)

def get_linked_ere_tickets(ticket):
    return [link["key"] for link in ticket.get("issue_links", []) if link["key"].startswith("ERE")]

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
        erecso_description = ticket.get("executive_summary") or ticket.get("summary") or ""
        text = collect_text_for_summary(ticket, linked_tickets_dict)
        if erecso_description.strip() or text.strip():
            print(f"Generating AI summary for {ticket.get('ticket_id')}")
            ai_summary = generate_ai_summary(erecso_description, text)
        else:
            ai_summary = "[No ERECSO description or linked ticket details found]"
        minimal.append({
            "ticket_id": ticket.get("ticket_id"),
            "ai_summary": ai_summary
        })
    with open("ticket_id_ai_summary.json", "w", encoding="utf-8") as f:
        json.dump(minimal, f, indent=2)
    print("Minimal AI summaries saved to ticket_id_ai_summary.json")

if __name__ == "__main__":
    main()
