from __future__ import print_function

import logging

import six
from six.moves.html_parser import HTMLParser
from collections import defaultdict
from itertools import count

from .sugarcrm import get_connection
from .sugarquerylist import QueryList
from .sugarerror import ObjectDoesNotExist, MultipleObjectsReturned

from .rest_framework import Meta


HTMLP = HTMLParser()

log = logging.getLogger(__name__)


class SugarEntry:
    """Define an entry of a SugarCRM module."""
    _hashes = defaultdict(count(1).next if hasattr(count(1), 'next') else count(1).__next__)

    def __init__(self, connection=None, module_name=None, **initial_values):
        """Represents a new or an existing entry.

        Keyword arguments:
        connection -- Sugarcrm object to connect to a server
        name -- name of SugarCRM module that this class will represent
        initial_values -- initial field values
        """

        if module_name:
            self.module_name = module_name

        self._meta = Meta(self.module_name)

        if connection:
            self._connection = connection
        else:
            self._connection = get_connection()

        # Get the module fields through SugarCRM API.
        result = self._connection.get_module_fields(self.module_name)
        if result is None:
            return

        self._available_fields = result['module_fields']

        # In order to ensure that queries target the correct tables.
        # Necessary to replace a call to self.module_name.lower() which
        # was resulting in broken modules (ProductTemplates, etc).
        self._table = result['table_name']
        # If there aren't relationships the result here is an empty list
        # which has no copy method.  Fixing to provide an empty default.
        self._relationships = (result['link_fields'] or {}).copy()

        # Keep a mapping 'field_name' => value for every valid field retrieved.
        self._fields = {}
        self._dirty_fields = []

        # Allow initial fields in constructor.
        if initial_values is not None:
            for key, value in initial_values.items():
                setattr(self, key, value)
            # self._fields.update(initial_values)

        # Make sure that the 'id' field is always defined.
        if 'id' not in list(self._fields.keys()):
            self._fields['id'] = ''

    def __new__(cls, *args, **kwargs):
        new_class = super().__new__(cls)
        setattr(new_class, 'DoesNotExist', ObjectDoesNotExist)
        setattr(new_class, 'MultipleObjectsReturned', MultipleObjectsReturned)
        return new_class

    def __hash__(self):
        return self._hashes['%s-%s' % (self.module_name, self['id'])]

    def __unicode__(self):
        return "<SugarCRM %s entry '%s'>" % \
               (self.module_name.rstrip('s'), self['name'])

    def __str__(self):
        return f'<{self.module_name} {self["id"]}>'

    def __contains__(self, key):
        return key in self._available_fields

    def _retrieve(self, fieldlist, force=False):
        qstring = "%s.id = '%s'" % (self._table, self['id'])
        if not force:
            fieldlist = set(fieldlist) - set(self._fields.keys())
        if not fieldlist:
            return
        res = self._connection.get_entry_list(self.module_name,
                                                      qstring, '', 0,
                                                      list(fieldlist), 1, 0)
        if not res['entry_list'] or not res['entry_list'][0]['name_value_list']:
            for field in fieldlist:
                self[field] = ''
            return
        for prop, obj in list(res['entry_list'][0]['name_value_list'].items()):
            if obj['value']:
                self[prop] = HTMLP.unescape(obj['value'])
            else:
                self[prop] = ''

    def __getitem__(self, field_name):
        """Return the value of the field 'field_name' of this SugarEntry.

        Keyword arguments:
        field_name -- name of the field to be retrieved. Supports a tuple
                      of fields, in which case the return is a tuple.
        """

        if isinstance(field_name, tuple):
            self._retrieve(field_name)
            return tuple(self[n] for n in field_name)

        if field_name not in self._available_fields:
            raise AttributeError("Invalid field '%s'" % field_name)

        if field_name not in self._fields:
            self._retrieve([field_name])
        return self._fields[field_name]
    
    def __setattr__(self, key, value):
        if hasattr(self, '_available_fields') and key in self._available_fields:
            self.__dict__[key] = value
            self._fields[key] = value
            if key not in self._dirty_fields:
                self._dirty_fields.append(key)
        else:
            super(SugarEntry, self).__setattr__(key, value)

    def __setitem__(self, field_name, value):
        """Set the value of a field of this SugarEntry.

        Keyword arguments:
        field_name -- name of the field to be updated
        value -- new value for the field
        """

        if field_name in self._available_fields:
            self.__dict__[field_name] = value
            self._fields[field_name] = value
            if field_name not in self._dirty_fields:
                self._dirty_fields.append(field_name)
        else:
            raise AttributeError("Invalid field '%s'" % field_name)

    def _search(self, query_str, order_by='', offset='', limit='', fields=None, links_to_names=None):
        """
          Return a dictionary of records as well as pertinent query
          statistics.


        Keyword arguments:
        query_str -- SQL query to be passed to the API
        offset -- Record offset to start from
        limit -- Maximum number of results to return
        fields -- If set, return only the specified fields
        links_to_fields -- if set, retrieve related entries from link with fields specified.
        query -- The actual query class instance.
        """

        if fields is None:
            fields = list(self._available_fields.keys())
        if links_to_names is None:
            links_to_names = []

        result = {}

        entry_list = []
        resp_data = self._connection.get_entry_list(self.module_name,
                                                    query_str, order_by, offset, fields,
                                                    links_to_names, limit, 0)
        if resp_data['total_count']:
            try:
                result['total'] = int(resp_data['total_count'], 10)
            except TypeError as e:
                log.error(resp_data)
                log.exception(e)
        else:
            result['total'] = 0

        for idx, record in enumerate(resp_data['entry_list']):
            entry = SugarEntry(self._connection, self.module_name)
            for key, obj in list(record['name_value_list'].items()):
                val = obj['value']
                setattr(entry, key, val)
            entry.related_beans = defaultdict(list)
            try:
                linked = resp_data['relationship_list'][idx]
                for block in linked['link_list']:
                    entry.related_beans[block['name']].extend(block['records'])
            except:
                pass
            entry_list.append(entry)
        result['entries'] = entry_list
        return result

    def fields(self):
        return self._fields

    def save(self):
        """Save this entry in the SugarCRM server.

        If the 'id' field is blank, it creates a new entry and sets the
        'id' value.
        """
        is_new_object = True

        # If 'id' wasn't blank, it's added to the list of dirty fields; this
        # way the entry will be updated in the SugarCRM connection.
        if self['id'] != '':
            self._dirty_fields.append('id')
            is_new_object = False

        # nvl is the name_value_list, which has the list of attributes.
        nvl = []
        for field in set(self._dirty_fields):
            # Define an individual name_value record.
            nv = dict(name=field, value=self[field])
            nvl.append(nv)

        # Use the API's set_entry to update the entry in SugarCRM.
        result = self._connection.set_entry(self.module_name, nvl)
        try:
            setattr(self, 'id', result['id'])
        except:
            print(result)

        # fetch all fields for new object
        if is_new_object:
            obj = self.objects.get(id=self.id)

            for field, value in obj.fields().items():
                setattr(self, field, value)
        self._dirty_fields = []

    def delete(self):
        self.deleted = 1
        self.save()

    def relate(self, *related, **kwargs):
        """
		Relate this SugarEntry with other Sugar Entries.

		Positional Arguments:
		  related -- Secondary SugarEntry Object(s) to relate to this entry.
		Keyword arguments:
          relateby -> iterable of relationship names.  Should match the
                      length of *secondary.  Defaults to secondary
                      module table names (appropriate for most
                      predefined relationships).
        """

        self._connection.relate(self, *related, **kwargs)

    def get_related(self, module, fields=None, relateby=None, links_to_fields=None):
        """Return the related entries in another module.

        Keyword arguments:
        module -- related SugarModule object
        relateby -- custom relationship name (defaults to module.lower())
        links_to_fields -- Allows retrieval of related fields from addtional related modules for retrieved records.
        """

        if fields is None:
            fields = ['id']
        if links_to_fields is None:
            links_to_fields = []
        connection = self._connection
        # Accomodate retrieval of modules by name.
        if isinstance(module, six.string_types):
            module = connection[module]
        result = connection.get_relationships(self.module_name,
                                              self['id'],
                                              relateby or module.module_name.lower(),
                                              '',  # Where clause placeholder.
                                              fields,
                                              links_to_fields)
        entries = []
        for idx, elem in enumerate(result['entry_list']):
            entry = SugarEntry(module)
            for name, field in list(elem['name_value_list'].items()):
                val = field['value']
                entry._fields[name] = HTMLP.unescape(val) if isinstance(val, basestring) else val
                entry.related_beans = defaultdict(list)
                #                 try:
                linked = result['relationship_list'][idx]
                for relmod in linked:
                    for record in relmod['records']:
                        relentry = {}
                        for fname, fmap in record.items():
                            rfield = fmap['value']
                            relentry[fname] = HTMLP.unescape(rfield) if isinstance(rfield, six.string_types) else val
                        entry.related_beans[relmod['name']].append(relentry)
                        #                 except:
                        #                     pass

            entries.append(entry)

        return entries

    @property
    def objects(self):
        """
        Return a QueryList object for this SugarModule.

        Initially, it describes all the objects in the module. One can find
        specific objects by calling 'filter' and 'exclude' on the returned
        object.
        """
        return QueryList(self, fields=None, links_to_names=None)


class Call(SugarEntry):
    module_name = "Calls"


class Campaign(SugarEntry):
    module_name = "Campaigns"


class Contact(SugarEntry):
    module_name = "Contacts"


class Document(SugarEntry):
    module_name = "Documents"


class Email(SugarEntry):
    module_name = "Emails"


class Lead(SugarEntry):
    module_name = "Leads"


class Module(SugarEntry):
    module_name = "Modules"


class Note(SugarEntry):
    module_name = "Notes"


class Opportunity(SugarEntry):
    module_name = "Opportunities"


class Product(SugarEntry):
    module_name = "Products"


class Prospect(SugarEntry):
    module_name = "Prospects"


class ProspectList(SugarEntry):
    module_name = "ProspectLists"


class Quote(SugarEntry):
    module_name = "Quotes"


class Report(SugarEntry):
    module_name = "Reports"


class User(SugarEntry):
    module_name = "Users"


class Task(SugarEntry):
    module_name = "Tasks"


class Account(SugarEntry):
    module_name = "Accounts"
