#!/usr/bin/env python

import logging
from jsonschema import validate
import yaml
import json
from launchpadlib.launchpad import Launchpad


from time import sleep

COPY_FIELDS = [
    'milestone',
    'status',
    'importance',
    'assignee',
]

logging.basicConfig(
    level=logging.DEBUG,
    format='[%(asctime)s] %(message)s',
    datefmt='%m-%d %H:%M',
)

# schema = json.load(open('schema.json'))
# class Bug(object):
#     def __init__(self, lp_bug):
#         self.lp_bug = lp_bug
#         for bug_task in lp_bug.bug_tasks:
#             self.bug_task{bug_task}


class Project(object):
    def __init__(self, lp, name):
        self.lp = lp
        self.project = lp.projects[name]
        self.project_name = name
        self.focus = self.project.development_focus 
        self.focus_name = self.project.development_focus.name

    def copy_bug_task(self,
                      bug_task,
                      new_bug_task=None,
                      update_old=None,
                      update_new=None,
                      target=None):
        """Copy bug task to new bug_task with new focus
        :param bug_task: source bug_task where to get value
        :param new_bug_task: if bug_task already exists it should be passed here
        :param update_old: after copy params on old object would be changed to the specified values
        :param update_new: after copy params on new object would be changed to the specified values
        :param target: target series for bug_task, used only if creating new. Default to development_focus
        :type bug_task: Lauchpad BugTask
        :type new_bug_task: Lauchpad BugTask
        :type update_old: dict, None
        :type update_new: dict, None
        :type target: Launcpad Series
        :return: None
        :rtype: None
        """
        print repr(new_bug_task)
        # return None
        if not target:
            target = self.focus
        if update_old is None:
            update_old = {} 
        if update_new is None:
            update_new = {} 

        new_task = new_bug_task if new_bug_task else bug_task.bug.addTask(target=target)
        # copy
        for name in ['milestone', 'status', 'importance', 'assignee']:
            setattr(new_task, name, getattr(bug_task, name))

        for name, value in update_old.items():
            setattr(bug_task, name, value)

        for name, value in update_new.items():
            setattr(new_task, name, value)

        new_task.lp_save()

        if update_old:
            bug_task.lp_save()

        return new_task

    def add_or_update(self, src_bt, target, params=None):
        new_bt = None
        params = params if isinstance(params, dict) else {}

        if target == self.focus:
            for i in src_bt.bug.bug_tasks:
                # usually it is firsl element
                if i.target == project:
                    new_bt = i
                    break
        if not new_bt:
            new_bt = src_bt.bug.addTask(target=target)

        for field_name in COPY_FIELDS:
            if params.has_key(field_name):
                setattr(new_bt, field_name, params[field_name])
            else:
                setattr(new_bt, field_name, getattr(src_bt, field_name))

        new_bt.lp_save()


    def move_to_ms(self, bugs, old_ms_name, new_ms_name):
        old_ms = self.project.getMilestone(name=old_ms_name)
        old_target = old_ms.series_target
        new_ms = self.project.getMilestone(name=new_ms_name)
        new_target = new_ms.series_target

        # Name is required because object can't be used as a key because same objects are different
        # if recieved via different requests
        # TODO: make local classes of target, milestone, bug, project with normal __hash__ function
        old_target_name = old_ms.series_target.name
        new_target_name = new_ms.series_target.name

        # we should work across all bugs, not only bug_tasks
        # because we need to check if already targeted for old_ms and old target
        # and check if old_ms is targeted to new target
        # unique_bugs = {bt.bug.id:bt.bug for bt in tasks}.values()

        for bug in bugs:  # [i for i in bugs][0:5]:
            print bug.web_link
            if 'wait-for-stable' in bug.tags:
                print "Skipping task with tag: 'wait-for-stable'"
                continue
            # sleep(5)
            bt_targets = {
                bt.target.name: {
                    'bt': bt,
                    'ms': bt.milestone,
                    'ms_name': (bt.milestone.name if bt.milestone else None),
                }
                for bt in bug.bug_tasks 
            }
            for k, v in bt_targets.items():
                print "%s: %s" % (k, v['ms_name'])


            # print {k:(v['ms_name'], repr(v['bt']), repr(v['ms'])) for k,v in bt_targets.items()}
            # 1. check if new target exists in bug_tasks and if yes check if it is already targeted to new MS
            #    it means that bug is tracking in separate bug task via 'Target to series' function
            # 2. Check if new target is current development focus and check if it is already targeted to new MS
            #    it means that bug is tracking in bug itself
            if bt_targets.has_key(new_target_name) and bt_targets[new_target_name]['ms'] == new_ms or \
                new_target == self.focus and bt_targets[self.project_name]['ms'] == new_ms:
                print "Bug #{} already moved [{}]".format(bug.id, bug.web_link)
                if self.focus == old_target and bt_targets.has_key(old_target_name) and \
                        bt_targets[old_target_name]['bt'].status == "Won't Fix":
                    print "FIX the \"Won't Fix bug\" for project bug_task"
                    bt_targets[self.project_name]['bt'].status = "Won't Fix"
                    bt_targets[self.project_name]['bt'].lp_save()
                continue

            if bt_targets.has_key(old_target_name) and bt_targets[old_target_name]['ms'] == old_ms:
                print "Have an old target with old milestone in separate series"
                self.copy_bug_task(
                    bug_task=bt_targets[old_target_name]['bt'],
                    new_bug_task=bt_targets[new_target_name]['bt'] if bt_targets.has_key(new_target_name) else None,
                    update_old={'status': "Won't Fix"},
                    update_new={'milestone': new_ms},
                    target=new_target,
                )
                if bt_targets[self.project_name]['ms'] == old_ms and self.focus == old_target:
                    bt_targets[self.project_name]['bt'].status = "Won't Fix"
                    bt_targets[self.project_name]['bt'].lp_save()
                # add bug_task with target = newton
                # copy all values
                # target to 10.0
                # set bug_task.status = Won't fix
            elif self.focus == old_target and bt_targets.has_key(old_target_name) and bt_targets[old_target_name]['ms'] == old_ms:
                print "Have an old milestone with old target in development focus separate series"
                # ^^^^^ COVERED ABOVE IN FIST IF ^^^^^^
            elif self.focus == old_target and bt_targets[self.project_name]['ms'] == old_ms:
                # add bug_task with target = newton
                # copy all values to newton
                # add bug_task with target = mitaka
                # copy all values to mitaka
                # set mitaka.status = Won't fix
                # set newton.milestone = 10.0
                self.copy_bug_task(
                    bug_task=bt_targets[self.project_name]['bt'],
                    new_bug_task=bt_targets[new_target_name]['bt'] if bt_targets.has_key(new_target_name) else None,
                    update_old={},
                    update_new={'milestone': new_ms},
                    target=new_target,
                )
                self.copy_bug_task(
                    bug_task=bt_targets[self.project_name]['bt'],
                    new_bug_task=None,
                    update_old={'status': "Won't Fix"},
                    update_new={'status': "Won't Fix"},
                    target=old_target,
                )
                print "Have an old milestone with old target in development focus in Bug"
            elif self.focus == new_target and bt_targets.has_key(new_target_name) and  bt_targets[new_target_name]['ms'] == old_ms:
                # add bug_task with target = mitaka
                # copy all values to mitaka
                # set mitaka.status = Won't fix
                # set bug_task newton.milestone = 10.0
                print "Have an old milestone with new target in development focus separate series"
                self.copy_bug_task(
                    bt_targets[new_target_name]['bt'],
                    None,
                    {'milestone': new_ms},
                    {'status': "Won't Fix"},
                    target=old_target,
                )
            elif self.focus == new_target and bt_targets[self.project_name]['ms'] == old_ms:
                print "Have an old milestone with new target in development focus in Bug"
                source_bt = self.copy_bug_task(
                    bt_targets[self.project_name]['bt'],
                    bt_targets[old_target_name]['bt'] if bt_targets.has_key(old_target_name) else None,
                    target=old_target
                )
                self.copy_bug_task(
                    source_bt, 
                    bt_targets[new_target_name]['bt'] if bt_targets.has_key(new_target_name) else None,
                    {'status': "Won't Fix"},
                    {'milestone': new_ms},
                    target=new_target,
                )
                # add bug_task with target = mitaka
                # copy all values to mitaka
                # set mitaka.status = Won't fix
                # set bug_task newton.milestone = 10.0
            else:
                print "It does not have an old milestone anywhere, maybe in wrong series"

            # for bug_task in bug.bug_tasks:
            #     # new target with old MS => should add old_target and retarget to new_ms
            #     if bug_task.target == self.project \
            #         and self.focus == new_ms \
            #         and bug_task.milestone == old_ms:

            #         # self.copy_target_bug_task(target, bug, bug_task)
            #         bug_task.milestone == new_ms


            # if already targeted to new, skip
            # if any( == new_ms for bt in task.related_tasks):
            #     print("Already exists in Bug")
            #     continue
            # if task.target != self.project:
            #     print repr(task.milestone)
            #     raise Exception(repr(task))

            # for bt in bug.bug_tasks:
            #     # print repr(bt)
            #     if bt.target == self.project and bt.milestone == old_ms:
            #         print "Move {} from {} to {}".format(bt.bug.web_link, bt.milestone.name, new_ms.name)

            #         # new_task = bt.bug.addTask(target=old_target)
            #         # new_task.milestone = bt.milestone
            #         # new_task.status = "Won't Fix"
            #         # new_task.importance = bt.importance
            #         # new_task.assignee = bt.assignee
            #         # new_task.lp_save()
            #         # task.milestone = new_ms
            #         # task.lp_save()
            #         break
            #     # elif task.target == self.project:
            #     #     print "Found target on project with other MS"
            # else:
            #     raise Exception("Old milestone not found in bug, not updated")

    def apply_rules(self, bug_task_filter, series):
        if not isinstance(series, dict) or not isinstance(bug_task_filter, dict):
            return None

        # if bug_task_filter.has_key('milestone'):
        #     bug_task_filter['milestone'] = self.project.getMilestone(name=bug_task_filter['milestone'])

        targets = {}
        for name in series.keys():
            _series = project.project.getSeries(name=name)
            if _series:
                targets[name] = _series

        # tasks = project.project.searchTasks(**bug_task_filter)
        tasks = BTSearch(self.lp, self.project_name, **bug_task_filter)

        for task in tasks:
            print "working on task %s" % task
            pass
            # get source bug_task
            # update others
            # update source if needed


        # make a right order:
        # - add new series if needed
        # - update current series
        for name, params in series.items():
            pass


import dataset

class BTSearch(object):
    def __init__(self, lp, project_name, **kwargs):
        self.lp = lp
        development_focus = "%s/%s" % (project_name, lp.projects[project_name].development_focus.name)

        db = dataset.connect('sqlite:///%s.db' % project_name)
        where_cause = []
        where_args = []
        for name, cond in kwargs.items():
            if isinstance(cond, list):
                if name == "statuses":
                    name = "status"
                where_cause.append("%s IN (%s)" % (name, ', '.join(["\"%s\"" % str(i) for i in cond])))
                where_args.extend(cond)
            else:
                where_cause.append("%s = %s" % (name, cond if isinstance(cond, int) else '"%s"' % cond.replace('"', '\\"')))
                where_args.append(cond)
        self.sql = ("SELECT * FROM bug_tasks" + (
           " WHERE %s" % " AND ".join(where_cause) if where_cause else ""
        ))
        print self.sql
        res = db.query(self.sql)
        bug_list = {}
        skip_list = []
        for row in res:
            bug_id = row['bug_id']
            if bug_id in skip_list:
                continue
            if bug_list.has_key(bug_id):
                # check if it is development_focus
                if row['target'] == project_name and bug_list[bug_id]['target'] == development_focus:
                    # it is project for active focus
                    pass
                elif row['target'] == development_focus and bug_list[bug_id]['target'] == project_name:
                    # it is a bug_task with series same as dev_focus
                    bug_list[bug_id] = row
                else:
                    print "Skipping bug %s because it has multiple matching of filter" % bug_id
                    del bug_list[bug_id]
                    skip_list.append(bug_id)
            else:
                bug_list[bug_id] = row
        self.res = iter(bug_list.keys())


    def __iter__(self):
        return self

    def next(self):
        while True:
            bug_id = next(self.res)
            return lp.bugs[bug_id]
            # json.loads(lp._browser.get('https://api.launchpad.net/devel/bugs/%s/bug_tasks' % bug_id))
            # return row

if __name__ == '__main__':
    lp = Launchpad.login_with(
        application_name='lp_release_migrator',
        service_root='production',
        credentials_file='lp_release_migrator/lp_release_migrator_credentials.conf',
        version='devel'
    )

    with open('config.yaml') as f:
        config = yaml.load(f.read())

    # projects = config['projects']
    projects = ['fuel']
    # projects = ['mos']

    for project_name in projects:
        project = Project(lp, project_name)
        # tasks = project.project.searchTasks(
        #     status=['New', 'Confirmed', 'Triaged', 'In Progress', 'Incomplete'],
        #     importance=['Medium', 'Low', 'Wishlist'],
        #     milestone=project.project.getMilestone(name='9.0'),
        # )
        # search_result = BTSearch(
        #     lp=lp,
        #     project_name=project_name,
        #     status=['New', 'Confirmed', 'Triaged', 'In Progress', 'Incomplete'],
        #     importance=['Medium', 'Low', 'Wishlist'],
        #     milestone='9.0',
        # )
        # tasks = lp.bugs['1284120'].bug_tasks
        # project.move_to_ms(search_result, '9.0', '10.0')
        for task in config['tasks']:
            project.apply_rules(task['filter'], task['series'])
