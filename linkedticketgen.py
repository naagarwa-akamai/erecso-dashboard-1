import json
from datetime import datetime
import requests

API_URL = "https://track-api.akamai.com/jira/rest/api/2/issue"
CERT_PATH = "certs/certs/naagarwa.pem"
KEY_PATH = "certs/certs/naagarwa.key"

# File paths
ERECSO_JSON_FILE = "./ticket_details.json"  # Original ERECSO tickets file
LINKED_TICKETS_JSON_FILE = "linked_tickets_details.json"  # New JSON file for linked ticket details

def extract_linked_ticket_details():
    # Load ERECSO tickets
    with open(ERECSO_JSON_FILE, 'r', encoding='utf-8') as file:
        erecso_tickets = json.load(file)

    # Array to store linked ticket IDs
    linked_ticket_ids = []

    # Extract linked ticket IDs from ERECSO tickets
    for ticket in erecso_tickets:
        issue_links = ticket.get("issue_links", [])
        for link in issue_links:
            if link.get("key", "").startswith("ERE"):  # Only include tickets starting with "ERE"
                linked_ticket_ids.append(link["key"])

    # Remove duplicates
    linked_ticket_ids = list(set(linked_ticket_ids))

    # Fetch details for linked tickets
    linked_ticket_details = []
    for ticket_id in linked_ticket_ids:
        print(f"Fetching details for linked ticket: {ticket_id}")
        # Simulate fetching ticket details (replace this with actual API/database call)
        ticket_details = fetch_ticket_details(ticket_id)
        if ticket_details:
            linked_ticket_details.append(ticket_details)

    # Save linked ticket details to a new JSON file
    with open(LINKED_TICKETS_JSON_FILE, 'w', encoding='utf-8') as file:
        json.dump(linked_ticket_details, file, indent=4)

    print(f"Linked ticket details saved to {LINKED_TICKETS_JSON_FILE}")


def fetch_ticket_details(ticket_id):
    ticket_details = {}

    try:
        # Make a GET request to fetch ticket details
        response = requests.get(
            f"{API_URL}/{ticket_id}",
            cert=(CERT_PATH, KEY_PATH),
            verify=False  # Ensure SSL verification
        )
        
        if response.status_code == 200:
            ticket_data = response.json()

            # Extract relevant fields
           
            
            resolution = ticket_data.get("fields", {}).get("resolution", {})
            ticket_resolved_status = resolution.get("name", "Unresolved") if isinstance(resolution, dict) else "Unresolved"
            
            
            
            timetracking = ticket_data.get("fields", {}).get("timetracking", {})
            ticket_worklog = timetracking.get("timeSpent", 0) if isinstance(timetracking, dict) else 0
            
            issuetype = ticket_data.get("fields", {}).get("issuetype", {})
            ticket_issue_type = issuetype.get("name", "Unknown") if isinstance(issuetype, dict) else "Unknown"


            customfield_15003 = ticket_data.get("fields", {}).get("customfield_15003", {})
            ticket_product_type = customfield_15003.get("value", "Unknown") if isinstance(customfield_15003, dict) else "Unknown"

            customfield_15104 = ticket_data.get("fields", {}).get("customfield_15104", [])
            ticket_workcategory = customfield_15104[0].get("value", "Unknown") if isinstance(customfield_15104, list) and customfield_15104 else "Unknown"

            created = ticket_data.get("fields", {}).get("created", "Unknown")
            ticket_created = created if created else "Unknown"
            
            resolutiondate = ticket_data.get("fields", {}).get("resolutiondate", None)
            if resolutiondate:
                try:
                    ticket_resolution_date = datetime.strptime(resolutiondate, "%Y-%m-%dT%H:%M:%S.%f%z")
                except ValueError:
                    ticket_resolution_date = resolutiondate  # Keep original string if parsing fails

            customfield_14128 = ticket_data.get("fields", {}).get("customfield_14128", {})
            ticket_request_type = customfield_14128.get("value", "Unknown") if isinstance(customfield_14128, dict) else "Unknown"
            
            ticket_mitigation_plan = ticket_data.get("fields", {}).get("customfield_11806", None)  # Replace with actual field ID
            ticket_longterm_mitigation = ticket_data.get("fields", {}).get("customfield_14430", None)  # Replace with actual field ID
            ticket_executive_summary = ticket_data.get("fields", {}).get("customfield_10504", None)  # Replace with actual field ID
            ticket_resolution_description = ticket_data.get("fields", {}).get("customfield_12303", None)  # Replace with actual field ID
            ticket_root_cause = ticket_data.get("fields", {}).get("customfield_12644", "No Root Cause")  # Replace with actual field ID

            
            if ticket_data.get("fields", {}).get("components", {}) == []:
                ticket_components = None
            else:
                ticket_components = ticket_data.get("fields", {}).get("components", [{"name":None}])[0].get("name",None) # TODO
            ticket_summary = ticket_data.get("fields", {}).get("summary", "No Summary")
            # # ticket_description = ticket_data.get("fields", {}).get("description", "No Description")
            
            ticket_timespent = ticket_data.get("fields", {}).get("timespent", '0')
            
           
            # Append the ticket details as a JSON object
            ticket_details={
                "ticket_id": ticket_id,
                "summary": ticket_summary,
                "components": ticket_components,
                "request_type": ticket_request_type,
                "resolved_status": ticket_resolved_status,
                "worklog": ticket_worklog,
                "issue_type": ticket_issue_type,
                "created": ticket_created,
                "timespent": ticket_timespent,
                "product_type": ticket_product_type,
                "workcategory": ticket_workcategory,
                "mitigation_plan": ticket_mitigation_plan,
                "longterm_mitigation": ticket_longterm_mitigation,
                "executive_summary": ticket_executive_summary,
                "resolution_description": ticket_resolution_description,
                "root_cause": ticket_root_cause,
                "resolution_date": ticket_resolution_date if isinstance(ticket_resolution_date, str) else ticket_resolution_date.isoformat()  # Convert datetime to ISO format string
            }
        else:
            print(f"Failed to fetch details for ticket {ticket_id}. Status Code: {response.status_code}")
            return None

    except Exception as e:
        print(f"Error fetching details for ticket {ticket_id}: {e}")
        

    return ticket_details


# Run the extraction process
if __name__ == "__main__":
    extract_linked_ticket_details()