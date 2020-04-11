from __future__ import unicode_literals

import copy
import logging

from six.moves import html_parser

HTMLP = html_parser.HTMLParser()

log = logging.getLogger(__name__)


class QueryList:
    """Query a SugarCRM module for specific entries."""

    def __init__(self, entry, query='', order_by='', limit='', offset='', fields=None, links_to_names=None):
        """Constructor for QueryList.

        Keyword arguments:
        entry -- SugarEntry object to query
        query -- SQL query to be passed to the API
        """

        self.model = entry
        self._query = query
        self._order_by = order_by
        self._result_cache = None
        self.low_mark, self.high_mark = 0, None  # Used for offset/limit
        self._limit = limit
        self._offset = offset
        self._total = -1
        self._sent = 0
        self._fields = fields
        self._links_to_names = links_to_names

    def __deepcopy__(self, memo):
        """Don't populate the QuerySet's cache."""
        obj = self.__class__()
        for k, v in self.__dict__.items():
            if k == '_result_cache':
                obj.__dict__[k] = None
            else:
                obj.__dict__[k] = copy.deepcopy(v, memo)
        return obj

    def __repr__(self):
        return '<%s %s>' % (self.__class__.__name__, self.model.module_name)

    def _fetch_all(self):
        # run query
        if self._result_cache is None:
            result = self.model._search(self._query, self._order_by, self._offset, self._limit, self._fields,
                                        self._links_to_names)
            self._result_cache = result.get('entries', [])

    def __len__(self):
        if self._result_cache is None:
            self._fetch_all()
        return len(self._result_cache)

    def __iter__(self):
        self._fetch_all()
        return iter(self._result_cache)

    def __bool__(self):
        self._fetch_all()
        return bool(self._result_cache)

    def __getitem__(self, k):
        self.clear_limits()
        """Retrieve an item or slice from the set of results."""
        if not isinstance(k, (int, slice)):
            raise TypeError(
                'QuerySet indices must be integers or slices, not %s.'
                % type(k).__name__
            )
        assert ((not isinstance(k, slice) and (k >= 0)) or
                (isinstance(k, slice) and (k.start is None or k.start >= 0) and
                 (k.stop is None or k.stop >= 0))), \
            "Negative indexing is not supported."

        if self._result_cache is not None:
            return self._result_cache[k]

        if isinstance(k, slice):
            qs = self._chain()
            if k.start is not None:
                start = int(k.start)
            else:
                start = None
            if k.stop is not None:
                stop = int(k.stop)
            else:
                stop = None

            qs.set_limits(start, stop)
            qs._fetch_all()
            return qs._result_cache[::k.step] if k.step else qs._result_cache

        qs = self._chain()
        qs.set_limits(k, k + 1)
        qs._fetch_all()
        return qs._result_cache[0]

    def _chain(self, **kwargs):
        """
        Return a copy of the current QuerySet that's ready for another
        operation.
        """
        obj = self._clone()
        obj.__dict__.update(kwargs)
        return obj

    def _clone(self):
        """
        Return a copy of the current QuerySet. A lightweight alternative
        to deepcopy().
        """
        return QueryList(self.model,
                         query=self._query,
                         order_by=self._order_by,
                         limit=self._limit,
                         offset=self._offset,
                         fields=self._fields,
                         links_to_names=self._links_to_names)

    def set_limits(self, low=None, high=None):
        """
        Adjust the limits on the rows retrieved. Use low/high to set these,
        as it makes it more Pythonic to read and write. When the SQL query is
        created, convert them to the appropriate offset and limit values.

        Apply any limits passed in here to the existing constraints. Add low
        to the current low value and clamp both to any existing high value.
        """
        if high is not None:
            if self.high_mark is not None:
                self.high_mark = min(self.high_mark, self.low_mark + high)
            else:
                self.high_mark = self.low_mark + high
        if low is not None:
            if self.high_mark is not None:
                self.low_mark = min(self.high_mark, self.low_mark + low)
            else:
                self.low_mark = self.low_mark + low

        if self.low_mark == self.high_mark:
            # clear limit offset
            self.clear_limits()

        if self.low_mark != self.high_mark:
            self._limit, self._offset = self._get_limit_offset_params(self.low_mark, self.high_mark)

    def clear_limits(self):
        self._limit, self._offset = None, 0

    @staticmethod
    def _get_limit_offset_params(low_mark, high_mark):
        offset = low_mark or 0
        if high_mark is not None:
            return (high_mark - offset), offset
        return None, offset

    def _build_query(self, **query):
        """Build the API query string.
        """

        available_fields = list(self.model._available_fields.keys())

        q_str = ''
        for key, val in list(query.items()):
            # Get the field and the operator from the query
            key_field, key_sep, key_oper = key.partition('__')

            if key_field == 'pk' and 'id' not in query:
                key_field = 'id'

            if key_field in available_fields:
                if q_str != '':
                    q_str += ' AND '

                if_cstm = ''
                if key_field.endswith('_c'):
                    if_cstm = '_cstm'

                field = self.model._table + if_cstm + '.' + key_field

                if key_oper in ('exact', 'eq') or (not key_oper and not key_sep):
                    q_str += '%s = "%s"' % (field, val)
                elif key_oper == 'contains':
                    q_str += '%s LIKE "%%%s%%"' % (field, val)
                elif key_oper == 'startswith':
                    q_str += '%s LIKE "%s%%"' % (field, val)
                elif key_oper == 'in':
                    q_str += '%s IN (' % field
                    for elem in val:
                        q_str += "'%s'," % elem
                    q_str = q_str.rstrip(',')
                    q_str += ')'
                elif key_oper == 'gt':
                    q_str += '%s > "%s"' % (field, val)
                elif key_oper == 'gte':
                    q_str += '%s >= "%s"' % (field, val)
                elif key_oper == 'lt':
                    q_str += '%s < "%s"' % (field, val)
                elif key_oper == 'lte':
                    q_str += '%s <= "%s"' % (field, val)
                else:
                    raise LookupError('Unsupported operator')

        return q_str

    def get(self, **query):
        query = self._build_query(**query)

        qs = QueryList(self.model,
                       query,
                       order_by='',
                       limit='',
                       offset='',
                       fields=self._fields,
                       links_to_names=self._links_to_names)
        num = len(qs)
        if num == 1:
            return qs.first()
        if not num:
            raise self.model.DoesNotExist(
                "%s matching query does not exist." %
                self.model.module_name
            )
        raise self.model.MultipleObjectsReturned(
            'get() returned more than one %s -- it returned %s!' % (
                self.model.module_name,
                num,
            )
        )

    def filter(self, **query):
        """Filter this QueryList, returning a new QueryList.

        Keyword arguments:
        query -- kwargs dictionary where the filters are specified:
            The keys should be some of the entry's field names, suffixed by
            '__' and one of the following operators: 'exact', 'contains', 'in',
            'gt', 'gte', 'lt' or 'lte'. When the operator is 'in', the
            corresponding value MUST be a list.
        """

        if self._query != '':
            query = '(%s) AND (%s)' % (self._query, self._build_query(**query))
        else:
            query = self._build_query(**query)

        return QueryList(self.model,
                         query,
                         order_by=self._order_by,
                         limit=self._limit,
                         offset=self._offset,
                         fields=self._fields,
                         links_to_names=self._links_to_names)

    def all(self):
        return QueryList(self.model,
                         self._query,
                         order_by=self._order_by,
                         limit=self._limit,
                         offset=self._offset,
                         fields=self._fields,
                         links_to_names=self._links_to_names)

    def exclude(self, **query):
        """Filter this QueryList, returning a new QueryList, as in filter(),
        but excluding the entries that match the query.
        """

        if self._query != '':
            query = '(%s) AND NOT (%s)' % (self._query, self._build_query(**query))
        else:
            query = 'NOT (%s)' % self._build_query(**query)

        return QueryList(self.model,
                         query,
                         order_by=self._order_by,
                         fields=self._fields,
                         limit=self._limit,
                         offset=self._offset,
                         links_to_names=self._links_to_names)

    def remove_invalid_fields(self, fields):
        valid_fields = []
        available_fields = list(self.model._available_fields.keys())
        for field in fields:
            if field in available_fields:
                valid_fields.append(field)
        return valid_fields

    def _get_ordering_field(self, value):
        desc = False
        field_name = value

        if field_name.startswith('-'):
            desc = True
            field_name = field_name[1:]

        if field_name == 'pk':
            field_name = 'id'

        valid_fields = self.remove_invalid_fields([field_name, ])
        if field_name in valid_fields:
            return field_name, desc

        return None, None

    def order_by(self, value):
        field_name, desc = self._get_ordering_field(value)
        order_by = self._order_by

        if field_name is not None:
            order_by = field_name
            if desc:
                order_by = f'{order_by} desc'

        return QueryList(self.model,
                         self._query,
                         order_by=order_by,
                         fields=self._fields,
                         limit=self._limit,
                         offset=self._offset,
                         links_to_names=self._links_to_names)

    def count(self):
        if self._total == -1:
            result = self.model._connection.get_entries_count(self.model.module_name, self._query, 0)

            self._total = int(result['result_count'], 10)
        return self._total

    def first(self):
        if self._result_cache is None:
            self._fetch_all()
        for obj in self._result_cache[:1]:
            return obj

    def only(self, *_fields):
        fields = self._fields
        valid_fields = self.remove_invalid_fields(_fields)

        if valid_fields:
            fields = valid_fields

        return QueryList(self.model,
                         self._query,
                         order_by=self._order_by,
                         fields=fields,
                         limit=self._limit,
                         offset=self._offset,
                         links_to_names=self._links_to_names)

    def links_to_names(self, *_links_to_names):
        links_to_names = self._links_to_names

        if _links_to_names:
            links_to_names = _links_to_names

        return QueryList(self.model,
                         self._query,
                         order_by=self._order_by,
                         fields=self._fields,
                         limit=self._limit,
                         offset=self._offset,
                         links_to_names=links_to_names)
