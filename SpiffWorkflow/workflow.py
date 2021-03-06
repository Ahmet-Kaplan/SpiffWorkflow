# -*- coding: utf-8 -*-
from __future__ import division, absolute_import
from __future__ import print_function
from builtins import next
from builtins import object
# Copyright (C) 2007 Samuel Abels
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
# 02110-1301  USA
import logging
from . import specs
from .task import Task
from .util.compat import mutex
from .util.event import Event
from .exceptions import WorkflowException

LOG = logging.getLogger(__name__)


def same_ending_length(node):
    """
    return the length of the endings of each child that match each other
    """
    # go get a modified list of just the ids in each child.
    endings = [[leaf['id'] for leaf in branch['children']] for branch in node]
    # the longest identical ending will be equal to the lenght of the
    # shortest list
    shortest_list = min([len(x) for x in endings])
    # walk through the list and determine if they are all the same
    # for each. If they are not the same, then we back off the snip point
    snip_point = shortest_list
    for x in reversed(range(shortest_list)):
        current_pos = -(x+1)
        if not all([idlist[current_pos]] for idlist in endings):
            snip_point = -current_pos
    return snip_point

def snip_same_ending(node,length):
    """
    shorten each child task list to be only it's unique children,
    return a list of the same endings so we can tack it on the
    parent tree.
    """
    retlist = node[0]['children'][-length:]
    for branch in node:
        new_children = []
        for child in branch['children']:
            if not child in retlist:
                new_children.append(child)
        branch['children'] = new_children
    return retlist

def flatten(list,output=[],level=0):
    """
    Traverse the tree and return a list
    """
    for x in list:
        x['indent'] = level
        x['child_count'] = len(x['children'])
        output.append(x)
        if len(x['children']) >0:
            flatten(x['children'],output,level+1)
        del x['children']
    return output


def follow_tree(tree,output=[],found=set(),level=0):
    from SpiffWorkflow.bpmn.specs.UnstructuredJoin import UnstructuredJoin
    from SpiffWorkflow.bpmn.specs.MultiInstanceTask import MultiInstanceTask


    outputs = list(tree.outgoing_sequence_flows.keys())
    if len(outputs)==0:
        # This has no children, so we append it and terminate the recursion
        if tree.description is not None and \
                tree.description != '' and \
                tree.id not in [x['id'] for x in output]:
            output.append({'id': tree.id,
                           'name': tree.name,
                           'description': tree.description,
                           'backtracks': None,
                           'children': [],
                           'level': level})
        found.add(tree.id)
        return output

    if isinstance(tree,MultiInstanceTask) and\
            not tree.isSequential:
        # NB: Not technically correct but expedient
        for task in tree.inputs[1].outputs:
            linkkey = list(task.outgoing_sequence_flows.keys())[0]
            link = task.outgoing_sequence_flows[linkkey]

            # consider to check and see if this one is already
            # in the list - we may have a problem if we are nesting
            # parallel gateways.
            if task.description is not None and \
                task.description != '':
                output.append({'id': task.id,
                               'name': task.name,
                               'description': task.description,
                               'is_decision': False,
                               'children':[],
                               'backtracks':None,
                               'level': level})
            if task.id not in found:
                found.add(task.id)
                output = follow_tree(link.target_task_spec, output, found, level + 1)

        return output


    if len(outputs) == 1:
        # there are no branching points here, so our job is simple
        # add to the tree and descend into the tree some more
        link = tree.outgoing_sequence_flows[outputs[0]]
        if tree.description is not None and \
                tree.description != '' and \
                tree.id not in [x['id'] for x in output]:
            output.append({'id': tree.id,
                           'name': tree.name,
                           'description': tree.description,
                           'backtracks': None,
                           'children':[],
                           'level': level })
        if tree.id not in found:
            found.add(tree.id)
            output = follow_tree(link.target_task_spec, output, found, level+1)
        return output

    if isinstance(tree,UnstructuredJoin):
        # here we have a parallel gateway, so we want to
        # add myself to the tree - subsequent calls will
        # not add if it is already in the list

        for key in outputs:
            link = tree.outgoing_sequence_flows[key]

            # consider to check and see if this one is already
            # in the list - we may have a problem if we are nesting
            # parallel gateways.
            if tree.description is not None and \
                tree.description != '':
                output.append({'id': tree.id,
                               'name': tree.name,
                               'description': tree.description,
                               'is_decision': False,
                               'children':[],
                               'backtracks':None,
                               'level': level})
            if tree.id not in found:
                found.add(tree.id)
            # For parallel tasks, Check all the children, not just the first one.
            output = follow_tree(link.target_task_spec, output, found, level + 1)

        return output
    # if we are here, then we assume that we have a decision point and process
    # accordingly - this may be incorrect and we may want to add some other
    # cases -
    taskchildren = []
    for key in outputs:
        link = tree.outgoing_sequence_flows[key]
        if link.name is not None:
            mychildren = []
            if link.target_task_spec.id not in found:
                follow_tree(link.target_task_spec, mychildren, found, level + 2)
                backtracklink = None
            else:
                backtracklink = (link.target_task_spec.id,link.target_task_spec.description)
            mychildren.sort(key=lambda x: x['level'])
            taskchildren.append({'id':link.id,
                                 'name':link.name,
                                 'description':link.name,
                                 'is_decision': True,
                                 'backtracks':backtracklink,
                                 'children':mychildren,
                                 'level':level+1})
        # we know we have several decision points which may merge in the future. The lists
        # should be identical except for the levels.
        # essentially, we want to find the list of ID's that are in each of the taskchildren's children
        # and remove that from each list.
        # in addition, this should be the same length on each end because of the sort above.
    # now that we have our children lists, we can remove the intersection of the group
    if tree.id not in  [x['id'] for x in output]:
        snip_lists = same_ending_length(taskchildren)
        merge_list = snip_same_ending(taskchildren, snip_lists)
        output.append({'id':tree.id,
                       'name':tree.name,
                       'description':tree.description,
                       'backtracks':None,
                       'is_decision':False,
                       'children':taskchildren,
                       'level':level+1})
        output =  output + merge_list
    found.add(tree.id)
    return output



class Workflow(object):

    """
    The engine that executes a workflow.
    It is a essentially a facility for managing all branches.
    A Workflow is also the place that holds the data of a running workflow.
    """

    def __init__(self, workflow_spec, deserializing=False, **kwargs):
        """
        Constructor.

        :type workflow_spec: specs.WorkflowSpec
        :param workflow_spec: The workflow specification.
        :type deserializing: bool
        :param deserializing: set to true when deserializing to avoid
          generating tasks twice (and associated problems with multiple
          hierarchies of tasks)
        """
        assert workflow_spec is not None
        LOG.debug("__init__ Workflow instance: %s" % self.__str__())
        self.spec = workflow_spec
        self.data = {}
        self.outer_workflow = kwargs.get('parent', self)
        self.locks = {}
        self.last_task = None
        if deserializing:
            assert 'Root' in workflow_spec.task_specs
            root = workflow_spec.task_specs['Root']  # Probably deserialized
        else:
            if 'Root' in workflow_spec.task_specs:
                root = workflow_spec.task_specs['Root']
            else:
                root = specs.Simple(workflow_spec, 'Root')
        self.task_tree = Task(self, root)
        self.success = True
        self.debug = False

        # Events.
        self.completed_event = Event()

        # Prevent the root task from being executed.
        self.task_tree.state = Task.COMPLETED
        start = self.task_tree._add_child(self.spec.start, state=Task.FUTURE)

        self.spec.start._predict(start)
        if 'parent' not in kwargs:
            start.task_spec._update(start)
        # start.dump()

    def is_completed(self):
        """
        Returns True if the entire Workflow is completed, False otherwise.

        :rtype: bool
        :return: Whether the workflow is completed.
        """
        mask = Task.NOT_FINISHED_MASK
        iter = Task.Iterator(self.task_tree, mask)
        try:
            next(iter)
        except StopIteration:
            # No waiting tasks found.
            return True
        return False

    def _get_waiting_tasks(self):
        waiting = Task.Iterator(self.task_tree, Task.WAITING)
        return [w for w in waiting]

    def _task_completed_notify(self, task):
        if task.get_name() == 'End':
            self.data.update(task.data)
        # Update the state of every WAITING task.
        for thetask in self._get_waiting_tasks():
            thetask.task_spec._update(thetask)
        if self.completed_event.n_subscribers() == 0:
            # Since is_completed() is expensive it makes sense to bail
            # out if calling it is not necessary.
            return
        if self.is_completed():
            self.completed_event(self)

    def _get_mutex(self, name):
        if name not in self.locks:
            self.locks[name] = mutex()
        return self.locks[name]

    def get_data(self, name, default=None):
        """
        Returns the value of the data field with the given name, or the given
        default value if the data field does not exist.

        :type  name: str
        :param name: A data field name.
        :type  default: obj
        :param default: Return this value if the data field does not exist.
        :rtype:  obj
        :returns: The value of the data field.
        """
        return self.data.get(name, default)

    def cancel(self, success=False):
        """
        Cancels all open tasks in the workflow.

        :type  success: bool
        :param success: Whether the Workflow should be marked as successfully
                        completed.
        """
        self.success = success
        cancel = []
        mask = Task.NOT_FINISHED_MASK
        for task in Task.Iterator(self.task_tree, mask):
            cancel.append(task)
        for task in cancel:
            task.cancel()

    def get_task_spec_from_name(self, name):
        """
        Returns the task spec with the given name.

        :type  name: str
        :param name: The name of the task.
        :rtype:  TaskSpec
        :returns: The task spec with the given name.
        """
        return self.spec.get_task_spec_from_name(name)

    def get_task(self, id):
        """
        Returns the task with the given id.

        :type id:integer
        :param id: The id of a task.
        :rtype: Task
        :returns: The task with the given id.
        """
        tasks = [task for task in self.get_tasks() if task.id == id]
        return tasks[0] if len(tasks) == 1 else None

    def get_tasks_from_spec_name(self, name):
        """
        Returns all tasks whose spec has the given name.

        :type name: str
        :param name: The name of a task spec.
        :rtype: Task
        :return: The task that relates to the spec with the given name.
        """
        return [task for task in self.get_tasks()
                if task.task_spec.name == name]

    def empty(self,str):
        if str == None:
            return True
        if str == '':
            return True
        return False

    def get_nav_list(self):
        """
        Return a list of waypoints for this workflow along with some key metrics
        - Each list item has :
               id               -   TaskSpec or Sequence flow id
               task_id          -   The uuid of the actual task instance, if it exists.
               name             -   The name of the task spec (or sequence)
               description      -   Text description
               backtracks       -   Boolean, if this backtracks back up the list or not
               level            -   Depth in the tree - probably not needed
               indent           -   A hint for indentation
               child_count       -   The number of children that should be associated with
                                    this item.
               state            -   Text based state (may be half baked in the case that we have
                                    more than one state for a task spec - but I don't think those
                                    are being reported in the list, so it may not matter)

                Any task with a blank or None as the description are excluded from the list (i.e. gateways)
        """
        # get the top of our list
        top = self.task_tree.children[0].task_spec.outputs[0]

        # traverse the tree
        l = follow_tree(top,output=[],found=set())

        # make sure things get presented in order - I may need to take another
        # look at why this is needed. Ideally, it would come out of the traversal in
        # the correct order
        l = sorted(l,key = lambda x: x['level'])

        # flatten the list to aid in display -
        # if I don't provide a new output, it just
        # appends.
        l = flatten(l,output=[])

        # Get all of our current tasks
        task_list = self.get_tasks()

        # look up task status for each item in the list
        for task_spec in l:

            # get a list of statuses for the current task_spec
            # we may have more than one task for each
            status = [x.state_names[x.state]
                      for x
                      in task_list
                      if x.task_spec.id == task_spec['id']]
            taskids = [x.id
                      for x
                      in task_list
                      if x.task_spec.id == task_spec['id']]
            if len(status)==0:
                # Sequence flows will not be in this list -
                # we will not find any status
                if task_spec.get('is_decision') is not None:
                    task_spec['state'] = 'NOOP'
                else:
                    task_spec['state'] = 'None'
                task_spec['task_id'] = None
            else:
                if all(status):
                    # if all of the statuses are the same,
                    # we just pull the first one
                    task_spec['state'] = status[0]
                    task_spec['task_id'] = taskids[0]
                else:
                    # The statuses are not all the same,
                    # in some conditions we may have to decide, but for the
                    # moment, the ones that would fall under this won't be
                    # displayed (i.e. closing parallel gateway that is either
                    # 'future' or 'waiting'
                    # for now, just grab one.
                    print(task_spec['id'])
                    task_spec['state'] = status[0]
                    task_spec['task_id'] = taskids[0]
        return l


    def get_tasks(self, state=Task.ANY_MASK):
        """
        Returns a list of Task objects with the given state.

        :type  state: integer
        :param state: A bitmask of states.
        :rtype:  list[Task]
        :returns: A list of tasks.
        """
        return [t for t in Task.Iterator(self.task_tree, state)]

    def reset_task_from_id(self, task_id):
        """
        Runs the task with the given id.

        :type  task_id: integer
        :param task_id: The id of the Task object.
        """
        if task_id is None:
            raise WorkflowException(self.spec, 'task_id is None')
        for task in self.task_tree:
            if task.id == task_id:
                return task.reset_token()
        msg = 'A task with the given task_id (%s) was not found' % task_id
        raise WorkflowException(self.spec, msg)




    def complete_task_from_id(self, task_id):
        """
        Runs the task with the given id.

        :type  task_id: integer
        :param task_id: The id of the Task object.
        """
        if task_id is None:
            raise WorkflowException(self.spec, 'task_id is None')
        for task in self.task_tree:
            if task.id == task_id:
                return task.complete()
        msg = 'A task with the given task_id (%s) was not found' % task_id
        raise WorkflowException(self.spec, msg)

    def complete_next(self, pick_up=True, halt_on_manual=True):
        """
        Runs the next task.
        Returns True if completed, False otherwise.

        :type  pick_up: bool
        :param pick_up: When True, this method attempts to choose the next
                        task not by searching beginning at the root, but by
                        searching from the position at which the last call
                        of complete_next() left off.
        :type  halt_on_manual: bool
        :param halt_on_manual: When True, this method will not attempt to
                        complete any tasks that have manual=True.
                        See :meth:`SpiffWorkflow.specs.TaskSpec.__init__`
        :rtype:  bool
        :returns: True if all tasks were completed, False otherwise.
        """
        # Try to pick up where we left off.
        blacklist = []
        if pick_up and self.last_task is not None:
            try:
                iter = Task.Iterator(self.last_task, Task.READY)
                task = next(iter)
            except StopIteration:
                task = None
            self.last_task = None
            if task is not None:
                if not (halt_on_manual and task.task_spec.manual):
                    if task.complete():
                        self.last_task = task
                        return True
                blacklist.append(task)

        # Walk through all ready tasks.
        for task in Task.Iterator(self.task_tree, Task.READY):
            for blacklisted_task in blacklist:
                if task._is_descendant_of(blacklisted_task):
                    continue
            if not (halt_on_manual and task.task_spec.manual):
                if task.complete():
                    self.last_task = task
                    return True
            blacklist.append(task)

        # Walk through all waiting tasks.
        for task in Task.Iterator(self.task_tree, Task.WAITING):
            task.task_spec._update(task)
            if not task._has_state(Task.WAITING):
                self.last_task = task
                return True
        return False

    def complete_all(self, pick_up=True, halt_on_manual=True):
        """
        Runs all branches until completion. This is a convenience wrapper
        around :meth:`complete_next`, and the pick_up argument is passed
        along.

        :type  pick_up: bool
        :param pick_up: Passed on to each call of complete_next().
        :type  halt_on_manual: bool
        :param halt_on_manual: When True, this method will not attempt to
                        complete any tasks that have manual=True.
                        See :meth:`SpiffWorkflow.specs.TaskSpec.__init__`
        """
        while self.complete_next(pick_up, halt_on_manual):
            pass

    def get_dump(self):
        """
        Returns a complete dump of the current internal task tree for
        debugging.

        :rtype:  str
        :returns: The debug information.
        """
        return self.task_tree.get_dump()

    def dump(self):
        """
        Like :meth:`get_dump`, but prints the output to the terminal instead
        of returning it.
        """
        print(self.task_tree.dump())

    def serialize(self, serializer, **kwargs):
        """
        Serializes a Workflow instance using the provided serializer.

        :type  serializer: :class:`SpiffWorkflow.serializer.base.Serializer`
        :param serializer: The serializer to use.
        :type  kwargs: dict
        :param kwargs: Passed to the serializer.
        :rtype:  object
        :returns: The serialized workflow.
        """
        return serializer.serialize_workflow(self, **kwargs)

    @classmethod
    def deserialize(cls, serializer, s_state, **kwargs):
        """
        Deserializes a Workflow instance using the provided serializer.

        :type  serializer: :class:`SpiffWorkflow.serializer.base.Serializer`
        :param serializer: The serializer to use.
        :type  s_state: object
        :param s_state: The serialized workflow.
        :type  kwargs: dict
        :param kwargs: Passed to the serializer.
        :rtype:  Workflow
        :returns: The workflow instance.
        """
        return serializer.deserialize_workflow(s_state, **kwargs)
