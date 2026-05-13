import json

# File paths
LINKED_TICKETS_JSON_FILE = "linked_tickets_details.json"
LINKED_TICKETS_DICT_FILE = "linked_tickets_dict.json"

def convert_to_dict():
    # Load the JSON file
    with open(LINKED_TICKETS_JSON_FILE, 'r', encoding='utf-8') as file:
        linked_tickets = json.load(file)

    # Convert the list to a dictionary
    linked_tickets_dict = {ticket["ticket_id"]: ticket for ticket in linked_tickets}

    # Save the dictionary to a new JSON file
    with open(LINKED_TICKETS_DICT_FILE, 'w', encoding='utf-8') as file:
        json.dump(linked_tickets_dict, file, indent=4)

    print(f"Linked tickets dictionary saved to {LINKED_TICKETS_DICT_FILE}")

# Run the conversion
if __name__ == "__main__":
    convert_to_dict()