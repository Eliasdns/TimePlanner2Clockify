# Required: Python 3.9+; requests
#!/bin/python3.9
# TODO: Mudar locale/timezone para UTC
import os; os.chdir(os.path.dirname(os.path.realpath(__file__)))
import sqlite3, configparser, csv
import requests
from datetime import datetime, timedelta, timezone


class CursorSQLite:
    def __init__(self, arquivo_sqlite):
        self.conexao = sqlite3.connect(arquivo_sqlite)
        self.cursor = self.conexao.cursor()
    
    def __enter__(self):
        return self.cursor

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cursor.close()
        self.conexao.close()

def send_request(request):
    try:
        request.raise_for_status()
    except requests.exceptions.HTTPError:
        print('HTTP error occurred!')
        raise
    except Exception:
        print('Other error occurred!')
        raise
    else:
        return request

CONFIGS_FILE = 'TimePlanner2Clockify.ini'
configs = configparser.ConfigParser()
configs.read(CONFIGS_FILE)
def get_config(section, key):
    try:
        return configs[section][key]
    except KeyError as err:
        raise ValueError(f"Error! value of {err} in the '{CONFIGS_FILE}' not found.")
    except Exception:
        raise


TIMEPLANNER_DB_FILE = get_config('TimePlanner', 'db_file')
# TIMEPLANNER_EXPORT_FILE = get_config('TimePlanner', 'export_file')

BASE_ENDPOINT = get_config('Clockify', 'base_endpoint')
WORKSPACE_ID = get_config('Clockify', 'workspace_id')
USER_ID = get_config('Clockify', 'user_id')
API_KEY = get_config('Clockify', 'api_key')
headers = {
    'X-Api-Key': API_KEY,
    'Content-Type': 'application/json',
}


def setup():
    global timeplanner_cats
    global clockify_tags
    global timeplanner_cat2clockify_tags_dict

    # Set timeplanner_cats
    with CursorSQLite(TIMEPLANNER_DB_FILE) as cursor:
        cursor.execute('SELECT _id, name, archive_date_time FROM category')
        timeplanner_cats = {
            cat_id: str(cat_name)
            for cat_id, cat_name, archive in cursor.fetchall()
            if not archive
        }

    # Set clockify_tags
    clockify_tags = {
        str(tag['name']): tag['id']
        for tag in send_request(
            requests.get(f'{BASE_ENDPOINT}/workspaces/{WORKSPACE_ID}/tags', headers=headers)
        ).json()
        if not tag['archived']
    }

    # Relationship between TimePlanner category (name) -> Clockify tag (name)
    # Set timeplanner_cat2clockify_tags_dict
    with open(get_config('DEFAULT', 'TimePlanner_cat2Clockify_tags'), 'r') as csv_file:
        csv_reader = csv.reader(csv_file)
        next(csv_reader)
        timeplanner_cat2clockify_tags_dict = {
            timeplanner: clockify for timeplanner, clockify in csv_reader
        }

def timeplanner_cat2clockify_tags(cat_id):
    timeplanner_cat_name = timeplanner_cats[cat_id]
    try:
        clockify_tag_name = timeplanner_cat2clockify_tags_dict[timeplanner_cat_name]
    except KeyError:
        clockify_tag_id = None
    except Exception:
        raise
    clockify_tag_id = clockify_tags[clockify_tag_name]

    tagIds = [clockify_tag_id] if clockify_tag_id is not None else None
    return {
        "billable": False,
        "projectId": None,
        "taskId": None,
        "tagIds": tagIds,
    }

def convert_timeplanner_data(date_time):
    return datetime.fromtimestamp(float(date_time)/1000, tz=timezone.utc) + timedelta(hours=3)

def convert_timeplanner_ms(time):
    return timedelta(milliseconds=time)


def timeplanner_db2clockify(verbose=False):
    setup()

    # Set clockify_timeentries
    clockify_timeentries = [
        { "description": timeentry["description"],
          "start": timeentry["timeInterval"]["start"],
          "end": timeentry["timeInterval"]["end"],
          "billable": timeentry["billable"],
          "projectId": timeentry["projectId"],
          "taskId": timeentry["taskId"],
          "tagIds": timeentry["tagIds"],
        } for timeentry in send_request(
            requests.get(f'{BASE_ENDPOINT}/workspaces/{WORKSPACE_ID}/user/{USER_ID}/time-entries', headers=headers)
        ).json()
    ]

    # Set new_timeentries
    with CursorSQLite(TIMEPLANNER_DB_FILE) as cursor:
        cursor.execute('SELECT name, date_time, value, pid FROM logged_activity')
        new_timeentries = (
            { "description": str(name) if name is not None else '',
              "start": (convert_timeplanner_data(date_time) - convert_timeplanner_ms(value)).strftime(r"%Y-%m-%dT%H:%M:%SZ"),
              "end": convert_timeplanner_data(date_time).strftime(r"%Y-%m-%dT%H:%M:%SZ"),
            } | timeplanner_cat2clockify_tags(cat_id)
            for name, date_time, value, cat_id in cursor.fetchall()
        )

    # Send new_timeentries
    success_entries = 0
    for new_timeentry in new_timeentries:
        if new_timeentry not in clockify_timeentries:
            request = send_request(
                requests.post(f'{BASE_ENDPOINT}/workspaces/{WORKSPACE_ID}/time-entries', json=new_timeentry, headers=headers)
            )
            if verbose:
                entry_id = request.json()["id"]
                start_time = request.json()["timeInterval"]["start"]
                description = request.json()["description"]
                print(f'[+] Sent: {entry_id} ({start_time}): {description}')
            success_entries += 1

    if verbose:
        if success_entries: print()
        print(f'[*] Finished! {success_entries} time entries have been sent.')
    return success_entries


# def timeplanner_export2clockify(verbose=False):
#     with open(TIMEPLANNER_EXPORT_FILE, 'r') as csv_file:
#         pass


# DANGER-ZONE!!!
def clockify_deleteall_timeentries(verbose=False):
    clockify_timeentries = [
        { "id": timeentry["id"],
          "description": timeentry["description"],
          "start": timeentry["timeInterval"]["start"],
        }
        for timeentry in send_request(
            requests.get(f'{BASE_ENDPOINT}/workspaces/{WORKSPACE_ID}/user/{USER_ID}/time-entries', headers=headers)
        ).json()
    ]

    success_deleted = 0
    for clockify_timeentry in clockify_timeentries:
        send_request(requests.delete(f'{BASE_ENDPOINT}/workspaces/{WORKSPACE_ID}/time-entries/{clockify_timeentry["id"]}', headers=headers))
        if verbose:
            print(f'[+] Deleted: {clockify_timeentry["id"]} ({clockify_timeentry["start"]}): {clockify_timeentry["description"]}')
        success_deleted += 1

    if verbose:
        if success_deleted: print()
        print(f'[*] Finished! {success_deleted} time entries have been deleted.')
    return success_deleted


if __name__ == '__main__':
    # timeplanner_db2clockify(verbose=True)
    pass
    # timeplanner_export2clockify(verbose=True)
