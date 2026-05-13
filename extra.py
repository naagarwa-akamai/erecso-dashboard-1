import json

with open('ticket_details_with_ai.json', 'r', encoding='utf-8') as f:
    tickets = json.load(f)

minimal = [
    {"ticket_id": t["ticket_id"], "ai_summary": t.get("ai_summary", "")} for t in tickets
]

with open('ticket_id_ai_summary.json', 'w', encoding='utf-8') as f:
    json.dump(minimal, f, indent=2)