# Required: Python 3.9+; requests
#!/bin/python3.9
# TODO: Testar Antigo horario de verão?
import os; os.chdir(os.path.dirname(os.path.realpath(__file__)))
import sqlite3, configparser, csv, json
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

# def send_request(request):
#     try:
#         request.raise_for_status()
#     except requests.exceptions.HTTPError:
#         print('HTTP error occurred!')
#         raise
#     except Exception:
#         print('Other error occurred!')
#         raise
#     else:
#         return request


CONFIGS_FILE = 'TimePlanner2Clockify.ini'
configs = configparser.ConfigParser()
configs.read(CONFIGS_FILE)

try:
    TIMEPLANNER_DB_FILE = configs['TimePlanner']['db_file']
    # TIMEPLANNER_EXPORT_FILE = configs['Timeplanner']['export_file']
except KeyError as err:
    raise ValueError(f"Error! value of {err} of the '{CONFIGS_FILE}' is required.")
except Exception:
    raise
with CursorSQLite(TIMEPLANNER_DB_FILE) as _cursor:
    _cursor.execute('SELECT _id, name, archive_date_time FROM category')
    timeplanner_cats = {
        cat_id: str(cat_name)
        for cat_id, cat_name, archive in _cursor.fetchall()
        if not archive
    }

try:
    BASE_ENDPOINT = configs['Clockify']['base_endpoint']
    WORKSPACE_ID = configs['Clockify']['workspace_id']
    USER_ID = configs['Clockify']['user_id']
    API_KEY = configs['Clockify']['api_key']
except KeyError as err:
    raise ValueError(f"Error! value of {err} in the '{CONFIGS_FILE}' is required.")
except Exception:
    raise
headers = {
    'X-Api-Key': API_KEY,
    'Content-Type': 'application/json',
}
try:
    _request = requests.get(f'{BASE_ENDPOINT}/workspaces/{WORKSPACE_ID}/tags', headers=headers)
    _request.raise_for_status()
    clockify_tags = {
        str(tag['name']): tag['id']
        for tag in _request.json()
        if not tag['archived']
    }
except requests.exceptions.HTTPError:
    print('HTTP error occurred!')
    raise
except Exception:
    print('Other error occurred!')
    raise
try:
    _request = requests.get(f'{BASE_ENDPOINT}/workspaces/{WORKSPACE_ID}/user/{USER_ID}/time-entries', headers=headers)
    _request.raise_for_status()
    clockify_timeentries = [
        { "description": timeentry["description"],
          "start": timeentry["timeInterval"]["start"],
          "end": timeentry["timeInterval"]["end"],
          "billable": timeentry["billable"],
          "projectId": timeentry["projectId"],
          "taskId": timeentry["taskId"],
          "tagIds": timeentry["tagIds"],
        } for timeentry in _request.json()
    ]
except requests.exceptions.HTTPError:
    print('HTTP error occurred!')
    raise
except Exception:
    print('Other error occurred!')
    raise

# Relationship between TimePlanner category (name) -> Clockify tag (name)
try:
    _csv = configs['DEFAULT']['TimePlanner_cat2Clockify_tags']
except KeyError as err:
    raise ValueError(f"Error! value of {err} in the '{CONFIGS_FILE}' is required.")
except Exception:
    raise
with open(_csv, 'r') as _csv_file:
    _csv_reader = csv.reader(_csv_file)
    next(_csv_reader)
    timeplanner_cat2clockify_tags_dict = {
        timeplanner: clockify for timeplanner, clockify in _csv_reader
    }


def timeplanner_cat2clockify_tags(cat_id):
    try:
        timeplanner_cat_name = timeplanner_cats[cat_id]
        clockify_tag_name = timeplanner_cat2clockify_tags_dict[timeplanner_cat_name]
        clockify_tag_id = clockify_tags[clockify_tag_name]
    except KeyError:
        clockify_tag_id = None
    except Exception:
        raise

    tagIds = [clockify_tag_id] if clockify_tag_id is not None else None
    return {
        "billable": False,
        "projectId": None,
        "taskId": None,
        # "tagIds": None,
        "tagIds": tagIds,
    }

def convert_timeplanner_data(date_time):
    return datetime.fromtimestamp(float(date_time)/1000, tz=timezone.utc) + timedelta(hours=3)

def convert_timeplanner_ms(time):
    return timedelta(milliseconds=time)


def timeplanner_db2clockify(verbose=False):
    with CursorSQLite(TIMEPLANNER_DB_FILE) as cursor:
        cursor.execute('SELECT name, date_time, value, pid FROM logged_activity')
        timeentries = (
            { "description": str(name) if name is not None else '',
              "start": (convert_timeplanner_data(date_time) - convert_timeplanner_ms(value)).strftime(r"%Y-%m-%dT%H:%M:%SZ"),
              "end": convert_timeplanner_data(date_time).strftime(r"%Y-%m-%dT%H:%M:%SZ"),
            } | timeplanner_cat2clockify_tags(cat_id)
            for name, date_time, value, cat_id in cursor.fetchall()
        )

    success_entries = 0
    for timeentry in timeentries:
        if timeentry not in clockify_timeentries:
            try:
                _request = requests.post(
                    f'{BASE_ENDPOINT}/workspaces/{WORKSPACE_ID}/time-entries',
                    json=timeentry,
                    headers=headers
                )
                _request.raise_for_status()
            except requests.exceptions.HTTPError:
                print('HTTP error occurred!')
                raise
            except Exception:
                print('Other error occurred!')
                raise
            else:
                if verbose:
                    _id = _request.json()["id"]
                    _start_time = _request.json()["timeInterval"]["start"]
                    _description = _request.json()["description"]
                    print(f'[+] Success! Sent: {_id} ({_start_time}): {_description}')
                success_entries += 1
    if verbose:
        if success_entries: print()
        print(f'[*] Finished! {success_entries} time entries have been sent.')
    return success_entries


# def timeplanner_export2clockify(verbose=False):
#     with open(TIMEPLANNER_EXPORT_FILE, 'r') as _csv_file:
#         pass


# DANGER-ZONE!!!
def clockify_deleteall_timeentries(verbose=False):
    try:
        _request = requests.get(f'{BASE_ENDPOINT}/workspaces/{WORKSPACE_ID}/user/{USER_ID}/time-entries', headers=headers)
        _request.raise_for_status()
        timeentries_ids = [
            timeentry["id"] for timeentry in _request.json()
        ]
    except requests.exceptions.HTTPError:
        print('HTTP error occurred!')
        raise
    except Exception:
        print('Other error occurred!')
        raise
    
    success_deleted = 0
    for timeentry_id in timeentries_ids:
        try:
            _request = requests.delete(f"{BASE_ENDPOINT}/workspaces/{WORKSPACE_ID}/time-entries/{timeentry_id}", headers=headers)
            _request.raise_for_status()
        except requests.exceptions.HTTPError:
            print('HTTP error occurred!')
            raise
        except Exception:
            print('Other error occurred!')
            raise
        else:
            if verbose: print(f'[+] Success! Deleted: {timeentry_id}.')
            success_deleted += 1
    
    return success_deleted
# DANGER-ZONE!!!
# clockify_deleteall_timeentries(verbose=True)

if __name__ == '__main__':
    timeplanner_db2clockify(verbose=True)
    # timeplanner_export2clockify(verbose=True)
