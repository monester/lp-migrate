#!/usr/bin/env python

import logging
from jsonschema import validate
import yaml
import json
from launchpadlib.launchpad import Launchpad
import dataset
from collections import OrderedDict

COPY_FIELDS = [
    'milestone',
    'status',
    'importance',
    'assignee',
]

logging.addLevelName(logging.DEBUG, "\033[1;36mDEBUG\033[1;0m")
logging.addLevelName(logging.INFO, "\033[1;32mINFO\033[1;0m")
logging.addLevelName(logging.WARNING, "\033[1;33mWARNING\033[1;0m")
logging.addLevelName(logging.ERROR, "\033[1;31mERROR\033[1;0m")

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s %(levelname)-7s] %(message)s',
    datefmt='%H:%M:%S',
)

schema = json.load(open('schema.json'))


class LPBase(object):
    URI = 'https://api.launchpad.net/devel'

    def __init__(self, lp, project_name):
        self.lp = lp
        self.project = lp.projects[project_name]
        self.project_name = project_name
        self.focus = self.project.development_focus
        self.focus_name = self.project_name + "/" + self.project.development_focus.name

    @property
    def development_focus(self):
        return self.focus_name

    def target_link(self, name):
        return "%s/%s" % (self.URI, name)

    @property
    def project_link(self):
        return "%s/%s" % (self.URI, self.project_name)

    def conv_to_link(self, name, value):
        if name == 'milestone' and not value.startswith("%s/+milestone/" % self.project_link):
            value = "%s/+milestone/%s" % (self.project_link, value)
        return value


class Project(LPBase):
    def add_or_update(self, src_bt, target, params=None):
        params = params if isinstance(params, dict) else {}

        dest_bt = None
        bug_tasks = src_bt.bug.bug_tasks
        entries = bug_tasks.entries
        for bt in entries:
            if bt['target_link'] == self.project_link and target == self.focus_name and not dest_bt:
                dest_bt = bug_tasks[entries.index(bt)]
            elif bt['target_link'] == self.target_link(target):
                dest_bt = bug_tasks[entries.index(bt)]

        if not dest_bt:
            dest_bt = src_bt.bug.addTask(target=self.target_link(target))

        for field_name in COPY_FIELDS:
            if field_name in params:
                setattr(dest_bt, field_name, self.conv_to_link(field_name, params[field_name]))
            else:
                setattr(dest_bt, field_name, getattr(src_bt, field_name))

        dest_bt.lp_save()

    def entry_compare(self, entry, params):
        for name, value in params.items():
            if name == 'milestone':
                if not entry['milestone_link'] == "%s/%s/+milestone/%s" % (self.URI, self.project_name, value):
                    logging.debug("Failed on milestone_link")
                    break
            elif entry[name] != params[name]:
                logging.debug("Failed on %s", name)
                break
        else:
            return True
        return False

    def entries_to_dict(self, entries):
        res = {}
        for bt in entries:
            if not bt['self_link'].startswith(self.URI + "/" + self.project_name):
                continue
            res[bt['target_link'].lstrip(self.URI)] = bt

        # remove if status is tracked in separate series
        if self.focus_name in entries:
            del res[self.project_name]

        return res

    def apply_rules(self, bug_task_filter, series, update):
        if not isinstance(series, dict) or not isinstance(bug_task_filter, dict):
            return None

        targets = {}
        if update:
            logging.info("Update if target exists")
        else:
            logging.info("No updates if target exists")
        for name in series.keys():
            _series = self.project.getSeries(name=name)
            if _series:
                targets[name] = _series

        # search for tasks matching criteria
        tasks = BTSearch(self.lp, self.project_name, **bug_task_filter)

        for bug, bt in tasks:
            src_target = self.project_name if bt.target == self.project else "%s/%s" % (
                self.project_name, bt.target.name)
            logging.info("Apply rules to bug %s, source: %s", bug.web_link, src_target)

            entries = bug.bug_tasks.entries
            entries_dict = self.entries_to_dict(entries)

            # sort series
            sorted_series = OrderedDict()
            for key, value in series.items():
                if key != src_target:
                    sorted_series[key] = value
            sorted_series[src_target] = series[src_target if src_target in series else self.focus_name]

            # remove project bug task if tracked in series
            if self.focus_name in sorted_series and self.project_name in sorted_series:
                del sorted_series[self.project_name]

            action_log = []
            for dest_target, params in sorted_series.items():
                if dest_target in entries_dict:
                    if update and not self.entry_compare(entries_dict[dest_target], params):
                        action_log.append("UPDATE series %s bug_task" % dest_target)
                elif dest_target == self.focus_name:
                    if update and not self.entry_compare(entries_dict[self.project_name], params):
                        self.add_or_update(bt, dest_target, series[dest_target])
                        action_log.append("UPDATE project %s bug_task" % self.project_name)
                else:
                    action_log.append("ADD series %s" % dest_target)
                    self.add_or_update(bt, dest_target, series[dest_target])
            logging.info("Actions done: %s", ", ".join(action_log) if action_log else "None")


class BTSearch(LPBase):
    def __init__(self, lp, project_name, **bug_task_filter):
        super(BTSearch, self).__init__(lp, project_name)

        self.bug_task_filter = bug_task_filter

        db = dataset.connect('sqlite:///%s.db' % project_name)
        where_cause = []
        for name, cond in bug_task_filter.items():
            if isinstance(cond, list):
                where_cause.append("%s IN (%s)" % (name, ', '.join(["\"%s\"" % str(i) for i in cond])))
            else:
                where_cause.append(
                    "%s = %s" % (name, cond if isinstance(cond, int) else '"%s"' % cond.replace('"', '\\"'))
                )

        # where_cause.append("bug_id = 1568812")

        self.sql = ("SELECT * FROM bug_tasks" + (
            " WHERE %s" % " AND ".join(where_cause) if where_cause else ""
        ))

        res = db.query(self.sql)
        bug_list = {}
        skip_list = []
        for row in res:
            bug_id = row['bug_id']

            # skip if bug is in duplicates
            if bug_id in skip_list:
                continue

            if bug_id in bug_list:
                # check if it is development_focus
                if row['target'] == project_name and bug_list[bug_id]['target'] == self.development_focus:
                    # it is project for active focus
                    pass
                elif row['target'] == self.development_focus and bug_list[bug_id]['target'] == project_name:
                    # it is a bug_task with series same as dev_focus
                    bug_list[bug_id] = row
                else:
                    logging.warning("Skipping, bug https://bugs.launchpad.net/bugs/%s "
                                    "has multiple matching of filter", bug_id)
                    del bug_list[bug_id]
                    skip_list.append(bug_id)
            else:
                bug_list[bug_id] = row
        self.res = iter(bug_list.keys())

    def __iter__(self):
        return self

    def link_to_name(self, name, value):
        if not value:
            return value
        if name == 'target':
            value = value.lstrip("%s/" % self.URI)
        elif name == 'milestone':
            value = value.lstrip("%s/%s/+milestone/" % (self.URI, self.project_name))
        elif name == 'assignee':
            value = value.lstrip("%s/~" % self.URI)
        return value

    def next(self):
        while True:
            bug_id = next(self.res)
            bug_tasks = json.loads(self.lp._browser.get('%s/bugs/%s/bug_tasks' % (self.URI, bug_id)))
            entries = bug_tasks['entries']
            results = []

            # making cache
            cache = {}
            for bt in entries:
                if not bt['self_link'].startswith(self.URI + "/" + self.project_name):
                    continue
                if bt['bug_target_name'] == self.project_name:
                    target = bt['bug_target_name']
                else:
                    target = self.project_name + "/" + bt['bug_target_name']
                cache[target] = bt

            if self.development_focus in cache:
                # status is tracked in separate series, delete project bug_task
                del cache[self.project_name]

            for target, bt in cache.items():
                bt_id = entries.index(bt)
                for key, value in self.bug_task_filter.items():
                    if key + '_link' in bt:
                        bt[key] = self.link_to_name(key, bt[key + '_link'])
                    elif key not in bt:
                        logging.error("Invalid key %s", key)
                        raise StopIteration
                    test = "Bug#BT: %s#%s Assert %s == %s: %%s" % (bug_id, bt_id, bt[key], value)
                    if isinstance(value, list) and bt[key] in value or bt[key] == value:
                        logging.debug(test, "\033[1;32mSuccess\033[1;0m")
                        continue
                    logging.debug(test, "\033[1;31mFailed\033[1;0m")
                    break
                else:
                    # everything is matching in entry, saving result
                    bug = self.lp.bugs[bug_id]
                    results.append((bug, bug.bug_tasks[bt_id]))
            if len(results) == 1:
                return results[0]
            elif len(results) > 1:
                logging.warning("Skipping, bug https://bugs.launchpad.net/bugs/%s has multiple matching of filter",
                                bug_id)


def main():
    lp = Launchpad.login_with(
        application_name='lp_release_migrator',
        service_root='production',
        credentials_file='lp_release_migrator/lp_release_migrator_credentials.conf',
        version='devel'
    )

    with open('config.yaml') as f:
        config = yaml.load(f.read())
    validate(config, schema)

    for task in config['tasks']:
        for target in task['series'].keys():
            if not target.startswith(task['project']):
                task['series'][task['project'] + "/" + target] = task['series'].pop(target)

    for task in config['tasks']:
        project = Project(lp, task['project'])
        logging.info("~~ Project %s, task %s ~~", task['project'], task['description'])
        project.apply_rules(task['filter'], task['series'], task['update_existing'])


if __name__ == '__main__':
    main()
