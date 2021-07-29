# TimePlanner2Clockify

TimePlanner2Clockify.py is a python script to convert logged activities of [Time Planner](https://play.google.com/store/apps/details?id=com.albul.timeplanner) app in [Clockify](https://clockify.me/) time entries.

> This script has been tested with version 3.13.0_3 (Massive Star) of Time Planner, in july of 2021.

## Requirements

- Python 3.9: ```sudo apt install python3.9 python3-pip```
- requests: ```pip install requests```

## Config files

### Syntax of 'TimePlanner2Clockify.ini'

``` ini
[DEFAULT]
TimePlanner_cat2Clockify_tags = TimePlanner_cat2Clockify_tags.csv

[TimePlanner]
db_file = time_planner_backup.db
# export_file = time_planner_logged_activities.csv

[Clockify]
api_key = <your API key>
base_endpoint = https://api.clockify.me/api/v1
workspace_id = <your workspace id>
user_id = <your user id>
```

### Syntax of 'TimePlanner_cat2Clockify_tags.csv'

``` csv
TimePlanner,Clockify
<TimePlanner category name 1>,<Clockify tag name 1>
<TimePlanner category name 2>,<Clockify tag name 2>
<TimePlanner category name 3>,<Clockify tag name 3>
...
```

This configuration file establishes the relationships between the Time Planner categories and the Clockify tags, if there is a proper match, the clockify time entry will be registered with the proper tag.

> This file is optional, and Time Planner category names that do not match with clockify tag names will be ignored.

## Input files

### The 'time_planner_backup.db'

This is the backup file of Time Planner.
