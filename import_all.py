import dataset
import json
import sys
from launchpadlib.launchpad import Launchpad

lp = Launchpad.login_with(
    application_name='lp_release_migrator',
    service_root='production',
    credentials_file='lp_release_migrator/lp_release_migrator_credentials.conf',
    version='devel'
)

for project_name in ['mos', 'fuel']:  #, 'mos']:
    db = dataset.connect('sqlite:///%s.db' % project_name)
    project = lp.projects[project_name]
    tasks = project.searchTasks(status=[
        "New",
        "Incomplete",
        "Opinion",
        "Invalid",
        "Won't Fix",
        "Expired",
        "Confirmed",
        "Triaged",
        "In Progress",
        "Fix Committed",
        "Fix Released",
    ])

    bugs = db['bugs']
    bug_tasks = db['bug_tasks']

    bug_tasks.create_index([
        'project',
        'bug_id',
        'target',
        'milestone',
        'status',
        'importance',
        'assignee',
    ])

    counter = 0
    ids = [int(bt.self_link.lstrip('https://api.launchpad.net/devel/%s/+bug/' % project_name)) for bt in tasks]
    for bug_id in ids:
        counter += 1
        sys.stdout.write("%s / %s\r" % (counter, len(ids)))
        res = json.loads(lp._browser.get('https://api.launchpad.net/devel/bugs/%s/bug_tasks' % bug_id))
        bugs.upsert({'id':bug_id}, ['id'])
        for entry in res['entries']:
            data = {
                'project': project_name,
                'bug_id':bug_id,
                'target':entry['target_link'].lstrip('https://api.launchpad.net/devel/') if entry['target_link'] else None,
                'milestone':entry['milestone_link'].lstrip('https://api.launchpad.net/devel/%s/+milestone/' % project_name) if entry['milestone_link'] else None,
                'status':entry['status'],
                'importance':entry['importance'],
                'assignee':entry['assignee_link'].lstrip('https://api.launchpad.net/devel/') if entry['assignee_link'] else None,
            }
            print data
            try:
                row = bug_tasks.find_one(bug_id=data['bug_id'], target=data['target'])
            except:
                print "ERROR"
            if row:
                data['id'] = row['id']
                bug_tasks.update(data, ['id'])
            else:
                bug_tasks.insert(data)
