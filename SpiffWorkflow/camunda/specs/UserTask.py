# -*- coding: utf-8 -*-
from __future__ import division

from SpiffWorkflow.bpmn.specs.UserTask import UserTask
from SpiffWorkflow.bpmn.specs.BpmnSpecMixin import BpmnSpecMixin
from SpiffWorkflow.specs import Simple


class UserTask(UserTask, BpmnSpecMixin):

    def __init__(self, wf_spec, name, form, **kwargs):
        """
        Constructor.
        :param form: the information that needs to be provided by the user,
        as parsed from the camunda xml file's form details.
        """
        super(UserTask, self).__init__(wf_spec, name, **kwargs)
        self.form = form


    """
    Task Spec for a bpmn:userTask node.
    """

    def _on_trigger(self, my_task):
        pass

    def is_engine_task(self):
        return False


class FormField(object):
    def __init__(self, form_type="text"):
        self.id = ""
        self.type = form_type
        self.label = ""
        self.defaultValue = ""
        self.properties = []
        self.validation = []

    def add_property(self, property_id, value):
        self.properties.append(FormFieldProperty(property_id, value))

    def add_validation(self, name, config):
        self.validation.append(FormFieldValidation(name, config))

    def get_property(self, property_id):
        for prop in self.properties:
            if prop.id == property_id:
                return prop.value

    def has_property(self, property_id):
        return self.get_property(property_id) is not None

    def jsonable(self):
        return self.__dict__

class EnumFormField(FormField):
    def __init__(self):
        super(EnumFormField, self).__init__("enum")
        self.options = []

    def add_option(self, option_id, name):
        self.options.append(EnumFormFieldOption(option_id, name))

    def jsonable(self):
        return self.__dict__


class EnumFormFieldOption:
    def __init__(self, option_id, name):
        self.id = option_id
        self.name = name

    def jsonable(self):
        return self.__dict__


class FormFieldProperty:
    def __init__(self, property_id, value):
        self.id = property_id
        self.value = value

    def jsonable(self):
        return self.__dict__


class FormFieldValidation:
    def __init__(self, name, config):
        self.name = name
        self.config = config

    def jsonable(self):
        return self.__dict__


class Form:
    def __init__(self):
        self.key = ""
        self.fields = []

    def add_field(self, field):
        self.fields.append(field)

    def jsonable(self):
        return self.__dict__


