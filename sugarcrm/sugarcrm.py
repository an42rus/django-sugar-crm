from six.moves import urllib
import hashlib
import json

from .sugarerror import SugarError, SugarUnhandledException, is_error
from .settings import API_URL, USERNAME, PASSWORD


class Sugarcrm:
    """Sugarcrm main interface class.

    This class is what is used to connect to and interact with the SugarCRM
    server.
    """

    def __init__(self, url, username, password, is_ldap_member=False):
        """Constructor for Sugarcrm connection.

        Keyword arguments:
        url -- string URL of the sugarcrm REST API
        username -- username to allow login upon construction
        password -- password to allow login upon construction
        """
        # url which is is called every time a request is made.
        self._url = url

        self._username = username
        self._password = password
        self._isldap = is_ldap_member

        # String which holds the session id of the connection, required at
        # every call after 'login'.
        # Attempt to login.
        self._session = self.login()

        # Add modules containers
        self.modules = {}
        self.rst_modules = dict((m['module_key'], m)
                                for m in self.get_available_modules()['modules'])

    def __getitem__(self, key):
        if key not in self.rst_modules:
            raise KeyError("Invalid Key '%s'" % key)
        if key in self.rst_modules and key not in self.modules:
            from .sugarentry import SugarEntry
            self.modules[key] = SugarEntry(self, key)
        return self.modules[key]

    def get_user_id(self, *args):
        return self._method_call('get_user_id', *args)

    def get_user_team_id(self, *args):
        return self._method_call('get_user_team_id', *args)

    def get_available_modules(self, *args):
        return self._method_call('get_available_modules', *args)

    def get_module_fields(self, *args):
        return self._method_call('get_module_fields', *args)

    def get_entries_count(self, *args):
        return self._method_call('get_entries_count', *args)

    def get_entry(self, *args):
        return self._method_call('get_entry', *args)

    def get_entries(self, *args):
        return self._method_call('get_entries', *args)

    def get_entry_list(self, *args):
        return self._method_call('get_entry_list', *args)

    def set_entry(self, *args):
        return self._method_call('set_entry', *args)

    def set_entries(self, *args):
        return self._method_call('set_entries', *args)

    def set_relationship(self, *args):
        return self._method_call('set_relationship', *args)

    def set_relationships(self, *args):
        return self._method_call('set_relationships', *args)

    def get_relationships(self, *args):
        return self._method_call('get_relationships', *args)

    def get_server_info(self, *args):
        return self._method_call('get_server_info', *args)

    def set_note_attachment(self, *args):
        return self._method_call('set_note_attachment', *args)

    def get_note_attachment(self, *args):
        return self._method_call('get_note_attachment', *args)

    def set_document_revision(self, *args):
        return self._method_call('set_document_revision', *args)

    def get_document_revision(self, *args):
        return self._method_call('get_document_revision', *args)

    def search_by_module(self, *args):
        return self._method_call('search_by_module', *args)

    def get_report_entries(self, *args):
        return self._method_call('get_report_entries', *args)

    def login(self):
        """
            Establish connection to the server.
        """

        args = {'user_auth': {'user_name': self._username,
                              'password': self.password}}

        x = self._sendRequest('login', args)
        try:
            return x['id']
        except KeyError:
            raise SugarUnhandledException

    def logout(self, *args):
        return self._method_call('logout', args)

    def _method_call(self, method_name, *args):
        try:
            result = self._sendRequest(method_name,
                                       [self._session] + list(args))
        except SugarError as error:
            if error.is_invalid_session:
                # Try to recover if session ID was lost
                self._session = self.login()
                result = self._sendRequest(method_name,
                                           [self._session] + list(args))
            elif error.is_missing_module:
                return None
            elif error.is_null_response:
                return None
            elif error.is_invalid_request:
                print(method_name, args)
            else:
                raise SugarUnhandledException('%d, %s - %s' %
                                              (error.number,
                                               error.name,
                                               error.description))

        return result

    def _sendRequest(self, method, data):
        """Sends an API request to the server, returns a dictionary with the
        server's response.

        It should not need to be called explicitly by the user, but rather by
        the other functions.

        Keyword arguments:
        method -- name of the method being called.
        data -- parameters to the function being called, should be in a list
                sorted by order of items
        """
        data = json.dumps(data)
        args = {'method': method, 'input_type': 'json',
                'response_type': 'json', 'rest_data': data}
        params = urllib.parse.urlencode(args).encode('utf-8')
        response = urllib.request.urlopen(self._url, params)
        response = response.read().strip()
        if not response:
            raise SugarError({'name': 'Empty Result',
                              'description': 'No data from SugarCRM.',
                              'number': 0})
        try:
            result = json.loads(response.decode('utf-8'))
        except:
            raise Exception(response.decode('utf-8'))
        if is_error(result):
            raise SugarError(result)
        return result

    def relate(self, main, *secondary, **kwargs):
        """
          Relate two or more SugarEntry objects.

          Supported Keywords:
          relateby -> iterable of relationship names.  Should match the
                      length of *secondary.  Defaults to secondary
                      module table names (appropriate for most
                      predefined relationships).
        """

        relateby = kwargs.pop('relateby', [s._table for s in secondary])
        args = [[main.module_name] * len(secondary),
                [main['id']] * len(secondary),
                relateby,
                [[s['id']] for s in secondary]]
        # Required for Sugar Bug 32064.
        if main.module_name == 'ProductBundles':
            args.append([[{'name': 'product_index',
                           'value': '%d' % (i + 1)}] for i in range(len(secondary))])
        return self.set_relationships(*args)

    @property
    def password(self):
        """
            Returns an appropriately encoded password for this connection.
            - md5 hash for standard login.
            - plain text for ldap users
        """
        if self._isldap:
            return self._password
        encode = hashlib.md5(self._password.encode('utf-8'))
        result = encode.hexdigest()
        return result


def get_connection(url=API_URL, username=USERNAME, password=PASSWORD):
    if url and username and password:
        return Sugarcrm(url, username, password)
    raise SugarError({'name': 'Empty connection settings',
                      'description': 'Empty connection settings',
                      'number': 10})
