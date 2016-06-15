#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
  The `release_migrator` script.

  It intended to reassign all bugs which are tied to current release to the
  next one.
  This action should be done manually after each release.

  Within the process previous milestone should be removed, the new one added
  instead.
  Other fields left unchanged.

  Usage:
    Script could be runned manually with options passed via command line,
    it also aware of ENV variables but with lower precedence,
    and finally, it fallback to default config, if none of options was set.

    Options available:
      -h, --help            show this help message and exit
      -d, --dry_run         dry-run mode to run the script without any actions
                            on data
      -e, --execute         mode to run the script with modifications of data
      -p PROJECTS, --projects PROJECTS
                            project names in which context script would be
                            executed
      -o OLD_MILESTONE_NAMES, --old_milestone_names OLD_MILESTONE_NAMES
                            closed milestone names from which bugs would be
                            retarget
      -n NEW_MILESTONE_NAME, --new_milestone_name NEW_MILESTONE_NAME
                            active milestone name to which bugs would be
                            retarget
      -m MAXIMUM, --maximum MAXIMUM
                            total amount of issues to be processed
      -c CONFIG_FILE, --config_file CONFIG_FILE
                            path to config file if any
      -s STATUSES, --statuses STATUSES
                            project names in which context script would be
                            executed
      -i BUGS_IMPORTANCE, --bugs_importance BUGS_IMPORTANCE
                            bugs importance to be processed
      --version             show program's version number and exit


  Examples:
    # run with ENV variables and default config path:
    $ lp_release_migrator.py

    # run with options specified and config provided:
    $ lp_release_migrator.py -e -p fuel -o 6.9 -n 8.0
        -c ./lp_release_migrator.conf

    # run with multiply options:
    $ lp_release_migrator.py -e -p fuel -p mos -o 6.9 -o 7.0 -n 8.0

    # run with only config provided:
    $ lp_release_migrator.py -e -c ./lp_release_migrator.conf
"""

import argparse

from lp_client import LpClient


# pylint: disable=E1101
class LpReleaseMigrator(LpClient):
    """Class representing interface for data manipulation on Launchpad."""
    SCRIPT_NAME = 'lp_release_migrator'
    CREDENTIALS_FILE = '/etc/custom_scripts/{}_credentials.conf'.format(SCRIPT_NAME)
    DEFAULT_CONFIG_FILE = '/etc/custom_scripts/{}.conf'.format(SCRIPT_NAME)
    ENV_VAR_PREFIX = 'LP_RELEASE'

    BUG_STATUSES = ('New', 'Confirmed', 'Triaged', 'In Progress', 'Incomplete')
    BASE_URL = 'https://api.launchpad.net/devel/'
    # https://api.staging.launchpad.net/devel/

    def __init__(self, debug, *options):
        """LpReleaseMigrator constuctor."""
        super(LpReleaseMigrator, self).__init__(debug, *options)

    @staticmethod
    def required_options():
        """Return a list of string names of options required for execution."""
        return [
            'projects',
            'old_milestone_names',
            'new_milestone_name',
            'statuses',
            'bugs_importance',
            'maximum'
        ]

    def get_old_milestone_names(self):
        """Return old milestone names from which migration should occur."""
        return self.old_milestone_names

    def get_new_milestone_name(self):
        """Return new milestone name to which the bugs would be migrated."""
        return self.new_milestone_name

    def get_statuses(self):
        """Return new milestone name to which the bugs would be migrated."""
        return self.statuses

    def get_importance(self):
        """Return a list of bugs priorites limiting bugs to be migrated."""
        return self.bugs_importance

    def process_project(self, project_name):
        """Process release migration for one project."""
        self.logging.debug('Retrieving project %s..', project_name)

        try:
            project = self.get_lp_client().projects[project_name]
        except KeyError:
            self.logging.error(
                "Project %s wasn't found. Skipped..",
                project_name
            )
        else:
            if project:
                self.logging.debug(
                    'Retrieving active milestone %s..',
                    self.get_new_milestone_name()
                )

                new_milestone = project.getMilestone(
                    name=self.get_new_milestone_name()
                )
                self.get_stats()[project.name] = {}

                for old_milestone_name in self.get_old_milestone_names():
                    if self.is_limit_achived():
                        break

                    self.process_milestone_on_project(
                        project, old_milestone_name, new_milestone
                    )

            else:
                self.logging.debug(
                    "Project %s wasn't found. Skipped..",
                    project_name
                )

    def process_milestone_on_project(self,
                                     project,
                                     old_milestone_name,
                                     new_milestone):
        """Process selected milestone migration."""
        self.logging.debug(
            'Retrieving closed milestone %s..',
            old_milestone_name
        )
        old_milestone = project.getMilestone(name=old_milestone_name)

        if old_milestone:
            self.logging.debug(
                'Retrieving bugs for closed milestone %s..',
                old_milestone.name
            )

            old_bugs = old_milestone.searchTasks(
                status=self.statuses,
                importance=self.bugs_importance
            )

            bugs_num = len(old_bugs)
            self.logging.debug('Got %s bugs..', bugs_num)

            self.get_stats()[project.name][old_milestone_name] = {
                'total': bugs_num,
                'migrated': 0
            }

            for bug in old_bugs:
                if self.is_limit_achived():
                    break
                self.logging.debug("Bug #%s %s [%s]",
                                   bug.bug.id,
                                   bug.bug.title[0:80] + ('' if len(bug.bug.title) < 80 else '...'),
                                   bug.web_link)
                if self.is_targeted_for_maintenance(bug):
                    self.process_mtn_bug(
                        bug, project.name, old_milestone_name, new_milestone
                    )
                else:
                    self.process_not_mtn_bug(
                        bug, project.name, old_milestone_name, new_milestone
                    )
                self.logging.debug("")
        else:
            self.logging.debug(
                "Closed milestone %s wasn't found. Skipped..",
                old_milestone_name
            )

    def is_targeted_for_maintenance(self, bug):
        """Check if the bug targeted to maintenance milestone."""
        tasks = bug.related_tasks

        return any(
            '-mu' in self.bug_milestone_name(task) for task in tasks
        )

    def add_target_to_bug(self, bug, project_name, new_milestone):
        """Add new target for bug with copied attributes."""
        ms_name = self.get_new_milestone_name()

        tasks = bug.related_tasks
        # check if already targeted
        if any(self.bug_milestone_name(task) == ms_name for task in tasks):
            return False

        print(ms_name, [self.bug_milestone_name(task) for task in tasks])
        old_status = bug.status
        old_importance = bug.importance
        old_assignee = bug.assignee
        self.logging.debug("Add milestone %s, status %s, importance %s, assignee %s",
                           new_milestone.name, old_status, old_importance,
                           old_assignee.name if old_assignee else 'Unassigned')
        if self.is_debug():
            return False
        try:
            target = bug.bug.addTask(target=new_milestone.series_target)

            target.milestone = new_milestone
            target.status = old_status
            target.importance = old_importance
            target.assignee = old_assignee

            target.lp_save()
        except Exception as exc:  # pylint: disable=W0703
            self.logging.error(
                "Can't save target milestone '%s' for bug #%s : %s",
                self.get_new_milestone_name(),
                bug.bug.id,
                exc
            )
            # self.logging.exception(exc)
            raise
            return True
        return False


    def get_updates_milestone_for(self, milestone_name, project_name):
        """Get updates milestone object by milestone name."""
        updates_milestone_name = milestone_name + '-updates'

        project = self.get_lp_client().projects[project_name]
        milestone = project.getMilestone(name=updates_milestone_name)

        if not milestone:
            self.logging.error(
                "Can't find the milestone '%s' on project '%s'.",
                updates_milestone_name,
                project_name
            )

            return None

        return milestone

    def process_mtn_bug(self,
                        bug,
                        project_name,
                        old_milestone_name,
                        new_milestone):
        """Process selected bug that is targeted for maintenance.

        Target it for new milestone, and retarget it for 'updates' series."""
        updates_milestone = self.get_updates_milestone_for(
            old_milestone_name,
            project_name
        )

        if not updates_milestone:
            return None

        errors = self.add_target_to_bug(bug, project_name, new_milestone)

        self.logging.debug("Set milestone %s", updates_milestone.name, )
        if not self.is_debug() and not errors:
            bug.milestone = updates_milestone

            try:
                bug.lp_save()
            except Exception as exc:  # pylint: disable=W0703
                errors = True
                self.logging.error(
                    "Can't target bug for maintenance '%s' for bug #%s : %s",
                    old_milestone_name + '-updates',
                    bug.bug.id,
                    exc
                )
                self.logging.exception(exc)

        if not errors:
            self.get_stats()[project_name][old_milestone_name]['migrated'] += 1
            self.increase_proccessed_issues()
        else:
            self.logging.error("Can't reassign the bug #%s.", bug.bug.id)

    def process_not_mtn_bug(self,
                            bug,
                            project_name,
                            old_milestone_name,
                            new_milestone):
        """Process selected bug that isn't targeted for maintenance.

        Target it for new milestone, and set "Won't fix" for the old one."""
        errors = self.add_target_to_bug(bug, project_name, new_milestone)

        new_status = "Won't Fix"
        self.logging.debug("Update bug #%s status to '%s' for milestone: %s",
                           bug.bug.id, new_status, old_milestone_name)
        if not self.is_debug() and not errors:
            bug.status = new_status
            try:
                bug.lp_save()
            except Exception as exc:  # pylint: disable=W0703
                errors = True
                self.logging.error(
                    "Can't update bug #%s status to '%s' for milestone: %s",
                    bug.bug.id,
                    new_status,
                    old_milestone_name
                )
                self.logging.exception(exc)

        if not errors:
            self.get_stats()[project_name][old_milestone_name]['migrated'] += 1
            self.increase_proccessed_issues()
        else:
            self.logging.error("Can't reassign the bug #%s.", bug.bug.id)


def comma_list(string):
    return [i.strip() for i in string.split(',')]


def main(cli_args, debug):
    """Main script execute method."""
    lp_client = LpReleaseMigrator(debug, cli_args)
    lp_client.process()


# pylint: disable=C0103
if __name__ == '__main__':

    argument_parser = argparse.ArgumentParser(
        description="""
            %(prog)s is the script to retarget Launchpad bugs between releases
        """
    )

    argument_parser.add_argument(
        '-d', '--dry_run',
        action='store_true',
        help='dry-run mode to run the script without any actions on data'
    )

    argument_parser.add_argument(
        '-e', '--execute',
        action='store_true',
        help='mode to run the script with modifications of data'
    )

    argument_parser.add_argument(
        '-p', '--projects',
        action='store',
        type=comma_list,
        help='project names in which context script would be executed'
    )

    argument_parser.add_argument(
        '-o', '--old_milestone_names',
        action='store',
        type=comma_list,
        help='closed milestone names from which bugs would be retarget'
    )

    argument_parser.add_argument(
        '-n', '--new_milestone_name',
        action='store',
        help='active milestone name to which bugs would be retarget'
    )

    argument_parser.add_argument(
        '-m', '--maximum',
        action='store',
        type=int,
        help='total amount of issues to be processed'
    )

    argument_parser.add_argument(
        '-c', '--config_file',
        action='store',
        help='path to config file if any'
    )

    argument_parser.add_argument(
        '-s', '--statuses',
        action='store',
        type=comma_list,
        help='project names in which context script would be executed'
    )

    argument_parser.add_argument(
        '-i', '--bugs_importance',
        action='store',
        type=comma_list,
        help='bugs importance to be processed'
    )

    argument_parser.add_argument(
        '--version',
        action='version',
        version='%(prog)s 0.0.2'
    )

    arguments = argument_parser.parse_args()

    if arguments.dry_run:
        main(arguments, debug=True)
    elif arguments.execute:
        main(arguments, debug=False)
    else:
        argument_parser.print_help()
