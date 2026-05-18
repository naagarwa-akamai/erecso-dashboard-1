import requests
import json

API_URL = "https://track-api.akamai.com/jira/rest/api/2/issue"
SEARCH_API_URL = "https://track-api.akamai.com/jira/rest/api/2/search"
CERT_PATH = "certs/certs/naagarwa.pem"
KEY_PATH = "certs/certs/naagarwa.key"

SREINC_JQL = 'project = SREINC AND assignee in membersOf("dl-gpo-ops-inside-escalations") and createdDate >= startOfYear() order by key desc'


def fetch_ticket_details(ticket_id):
    """
    Fetch details for a list of tickets and return as an array of JSON objects.
    """
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
            ticket_key = ticket_data.get("key", "Unknown")
            
            customfield_16054 = ticket_data.get("fields", {}).get("customfield_16054", {})
            ticket_toil_percent = customfield_16054.get("value", "0") if isinstance(customfield_16054, dict) else "0"  # Replace with actual field ID
            
            customfield_16059 = ticket_data.get("fields", {}).get("customfield_16059", {})
            ticket_workaround = customfield_16059.get("value", "No") if isinstance(customfield_16059, dict) else "No"  # Replace with actual field ID            
            
            resolution = ticket_data.get("fields", {}).get("resolution", {})
            ticket_resolved_status = resolution.get("name", "Unresolved") if isinstance(resolution, dict) else "Unresolved"
            
            assignee = ticket_data.get("fields", {}).get("assignee", {})
            ticket_assignee = assignee.get("displayName", "Unassigned") if isinstance(assignee, dict) else "Unassigned"
            
            timetracking = ticket_data.get("fields", {}).get("timetracking", {})
            ticket_worklog = timetracking.get("timeSpent", 0) if isinstance(timetracking, dict) else 0
            
            issuetype = ticket_data.get("fields", {}).get("issuetype", {})
            ticket_issue_type = issuetype.get("name", "Unknown") if isinstance(issuetype, dict) else "Unknown"

            status = ticket_data.get("fields", {}).get("status", {})
            ticket_status = status.get("name", "Unknown") if isinstance(status, dict) else "Unknown"
            
            
            creator = ticket_data.get("fields", {}).get("creator", {})
            ticket_creator = creator.get("displayName", "Unknown") if isinstance(creator, dict) else "Unknown"

            reporter = ticket_data.get("fields", {}).get("reporter", {})
            ticket_reporter = reporter.get("displayName", "Unknown") if isinstance(reporter, dict) else "Unknown"

            customfield_13201 = ticket_data.get("fields", {}).get("customfield_13201", {})
            ticket_customer_impact = customfield_13201.get("value", "") if isinstance(customfield_13201, dict) else ""

            customfield_13812 = ticket_data.get("fields", {}).get("customfield_13812", {})
            ticket_requesting_team = customfield_13812.get("value", "Unknown") if isinstance(customfield_13812, dict) else "Unknown"

            customfield_15003 = ticket_data.get("fields", {}).get("customfield_15003", {})
            ticket_product_type = customfield_15003.get("value", "Unknown") if isinstance(customfield_15003, dict) else "Unknown"
            
            priority = ticket_data.get("fields", {}).get("priority", {})
            ticket_priority = priority.get("name", "Unknown") if isinstance(priority, dict) else "Unknown"

            customfield_15104 = ticket_data.get("fields", {}).get("customfield_15104", [])
            ticket_workcategory = customfield_15104[0].get("value", "Unknown") if isinstance(customfield_15104, list) and customfield_15104 else "Unknown"

            created = ticket_data.get("fields", {}).get("created", "Unknown")
            ticket_created = created if created else "Unknown"

            customfield_14128 = ticket_data.get("fields", {}).get("customfield_14128", {})
            ticket_request_type = customfield_14128.get("value", "Unknown") if isinstance(customfield_14128, dict) else "Unknown"

            labels = ticket_data.get("fields", {}).get("labels", [])
            ticket_labels = labels if isinstance(labels, list) else []
            
            if ticket_data.get("fields", {}).get("components", {}) == []:
                ticket_components = None
            else:
                ticket_components = ticket_data.get("fields", {}).get("components", [{"name":None}])[0].get("name",None) # TODO
            ticket_summary = ticket_data.get("fields", {}).get("summary", "No Summary")
            # Extract only the first https://akamai.aha.io/ link from the description
            # import re
            ticket_description = ticket_data.get("fields", {}).get("description", "")
            # aha_link = None
            # if isinstance(ticket_description, str):
            #     # Match until whitespace, ] or )
            #     match = re.search(r'(https://akamai\.aha\.io/[^\s\]\)]*)', ticket_description)
            #     if match:
            #         aha_link = match.group(1)
            ticket_executive_summary = ticket_data.get("fields", {}).get("customfield_10504", None)  # Replace with actual field ID
            ticket_resolution_description = ticket_data.get("fields", {}).get("customfield_12303", None)  # Replace with actual field ID
            ticket_root_cause = ticket_data.get("fields", {}).get("customfield_12644", "No Root Cause")  # Replace with actual field ID
            ticket_timespent = ticket_data.get("fields", {}).get("timespent", '0')
            ticket_service_incident = ticket_data.get("fields", {}).get("customfield_14303", None)  # Replace with actual field ID
            ticket_salesforce_case = ticket_data.get("fields", {}).get("customfield_17800", None)  # Replace with actual field ID
            ticket_resolution_date = ticket_data.get("fields", {}).get("resolutiondate", None)
            ticket_mitigation_plan = ticket_data.get("fields", {}).get("customfield_11806", None)  # Replace with actual field ID
            ticket_longterm_mitigation = ticket_data.get("fields", {}).get("customfield_14430", None)  # Replace with actual field ID
            account_name = ticket_data.get("fields", {}).get("customfield_14729", {})
            ticket_account_name = account_name.get("value", "Unknown") if isinstance(account_name, dict) else "-"
            issuelinks = ticket_data.get("fields", {}).get("issuelinks", [])
            ticket_issue_links = []

            if isinstance(issuelinks, list):
                for link in issuelinks:
                    link_type = link.get("type", {}).get("name", "Unknown")  # Type of the link (e.g., "blocks", "is blocked by")
                    outward_issue = link.get("outwardIssue", {}).get("key", None)  # Outward issue key
                    inward_issue = link.get("inwardIssue", {}).get("key", None)  # Inward issue key

                    # Add the link details to the list
                    if outward_issue:
                        ticket_issue_links.append({"type": link_type, "direction": "outward", "key": outward_issue})
                    if inward_issue:
                        ticket_issue_links.append({"type": link_type, "direction": "inward", "key": inward_issue})
            # Append the ticket details as a JSON object
            ticket_details={
                "flag":"-",
                "ticket_id": ticket_id,
                "summary": ticket_summary,
                "aha_link": None,
                "description": ticket_description,
                "components": ticket_components,
                "labels": ticket_labels,
                "request_type": ticket_request_type,
                "executive_summary": ticket_executive_summary,
                "resolution_description": ticket_resolution_description,
                "root_cause": ticket_root_cause,
                "toil_percent": ticket_toil_percent,
                "workaround": ticket_workaround,
                "resolved_status": ticket_resolved_status,
                "assignee": ticket_assignee,
                "worklog": ticket_worklog,
                "issue_type": ticket_issue_type,
                "status": ticket_status,
                "creator": ticket_creator,
                "reporter": ticket_reporter,
                "customer_impact": ticket_customer_impact,
                "requesting_team": ticket_requesting_team,
                "product_type": ticket_product_type,
                "priority": ticket_priority,
                "workcategory": ticket_workcategory,
                "created": ticket_created,
                "key": ticket_key,
                "timespent": ticket_timespent,
                "service_incident": ticket_service_incident,
                "salesforce_case": ticket_salesforce_case,
                "resolution_date": ticket_resolution_date,
                "mitigation_plan": ticket_mitigation_plan,
                "longterm_mitigation": ticket_longterm_mitigation,
                "issue_links": ticket_issue_links,
                "account_name": ticket_account_name
            }
        else:
            print(f"Failed to fetch details for ticket {ticket_id}. Status Code: {response.status_code}")
            return None

    except Exception as e:
        print(f"Error fetching details for ticket {ticket_id}: {e}")
        

    return ticket_details


def fetch_tickets_from_jql(jql_query):
    """Fetch issue keys from Jira search API for a given JQL."""
    ticket_ids = []
    start_at = 0
    max_results = 100

    while True:
        try:
            response = requests.get(
                SEARCH_API_URL,
                params={
                    "jql": jql_query,
                    "startAt": start_at,
                    "maxResults": max_results,
                    "fields": "key"
                },
                cert=(CERT_PATH, KEY_PATH),
                verify=False
            )

            if response.status_code != 200:
                print(f"Failed to fetch JQL results. Status Code: {response.status_code}")
                break

            data = response.json()
            issues = data.get("issues", [])

            if not issues:
                break

            ticket_ids.extend([issue.get("key") for issue in issues if issue.get("key")])

            total = data.get("total", 0)
            start_at += len(issues)
            if start_at >= total:
                break

        except Exception as e:
            print(f"Error fetching JQL results: {e}")
            break

    return ticket_ids


def fetch_and_store_sreinc_service_incidents(output_file="./ere_sustenance_ticket_details_sreinc.json"):
    """Fetch SREINC tickets from JQL, enrich details, and store them in JSON."""
    ticket_ids = fetch_tickets_from_jql(SREINC_JQL)
    ticket_details = []

    for ticket_id in ticket_ids:
        print(f"Fetching details for ticket: {ticket_id}")
        ticket_data = fetch_ticket_details(ticket_id)
        if ticket_data:
            ticket_details.append(ticket_data)

    with open(output_file, "w", encoding="utf-8") as file:
        json.dump(ticket_details, file, indent=4)

    print(f"SREINC ticket details saved to {output_file}")
    return ticket_details


if __name__ == "__main__":
    fetch_and_store_sreinc_service_incidents()

    ticket_number = 3110
    ticket_details = []

    while ticket_number <= 3400:  # Adjust the range as needed
        ticket_id = f"ERE-{ticket_number}"
        print(f"Fetching details for ticket: {ticket_id}")

        # Fetch ticket details
        
        ticket_data = fetch_ticket_details(ticket_id)

        if ticket_data:
            # Only include tickets with request type "ERE-DELIVERY-PORTAL"
            ticket_details.append(ticket_data)
        else:
            # Stop the loop if the ticket does not exist (e.g., 404 error)
            print(f"Stopping at ticket: {ticket_id}")
        

    # Increment the ticket number
        ticket_number += 1

    # Save the details to a JSON file
    output_file = "./ere_sustenance_ticket_details.json"
    with open(output_file, "w", encoding="utf-8") as file:
        json.dump(ticket_details, file, indent=4)

    print(f"Ticket details saved to {output_file}")