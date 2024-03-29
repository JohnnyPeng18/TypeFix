# -*- coding: utf-8 -*-

# Import Python libs
from __future__ import absolute_import
from distutils.version import LooseVersion  # pylint: disable=import-error,no-name-in-module
import json
import random
import string

# Import Salt Testing libs
from salttesting.unit import skipIf, TestCase
from salttesting.mock import NO_MOCK, NO_MOCK_REASON, patch
from salttesting.helpers import ensure_in_syspath

ensure_in_syspath('../../')

# Import Salt libs
import salt.config
import salt.loader

# Import 3rd-party libs
import logging

# Import Mock libraries
from salttesting.mock import NO_MOCK, NO_MOCK_REASON, MagicMock, patch

# pylint: disable=import-error,no-name-in-module
from unit.modules.boto_lambda_test import BotoLambdaTestCaseMixin, TempZipFile

# Import 3rd-party libs
try:
    import boto3
    from botocore.exceptions import ClientError
    HAS_BOTO = True
except ImportError:
    HAS_BOTO = False

# pylint: enable=import-error,no-name-in-module

# the boto_lambda module relies on the connect_to_region() method
# which was added in boto 2.8.0
# https://github.com/boto/boto/commit/33ac26b416fbb48a60602542b4ce15dcc7029f12
required_boto3_version = '1.2.1'

region = 'us-east-1'
access_key = 'GKTADJGHEIQSXMKKRBJ08H'
secret_key = 'askdjghsdfjkghWupUjasdflkdfklgjsdfjajkghs'
conn_parameters = {'region': region, 'key': access_key, 'keyid': secret_key, 'profile': {}}
error_message = 'An error occurred (101) when calling the {0} operation: Test-defined error'
error_content = {
  'Error': {
    'Code': 101,
    'Message': "Test-defined error"
  }
}
function_ret = dict(FunctionName='testfunction',
                    Runtime='python2.7',
                    Role='arn:aws:iam::1234:role/functionrole',
                    Handler='handler',
                    Description='abcdefg',
                    Timeout=5,
                    MemorySize=128,
                    CodeSha256='abcdef',
                    CodeSize=199,
                    FunctionArn='arn:lambda:us-east-1:1234:Something',
                    LastModified='yes')
alias_ret = dict(AliasArn='arn:lambda:us-east-1:1234:Something',
                 Name='testalias',
                 FunctionVersion='3',
                 Description='Alias description')
event_source_mapping_ret = dict(UUID='1234-1-123',
                                BatchSize=123,
                                EventSourceArn='arn:aws:dynamodb:us-east-1:1234::Something',
                                FunctionArn='arn:aws:lambda:us-east-1:1234:function:myfunc',
                                LastModified='yes',
                                LastProcessingResult='SUCCESS',
                                State='Enabled',
                                StateTransitionReason='Random')

log = logging.getLogger(__name__)

opts = salt.config.DEFAULT_MINION_OPTS
context = {}
utils = salt.loader.utils(opts, whitelist=['boto3'], context=context)
serializers = salt.loader.serializers(opts)
funcs = salt.loader.minion_mods(opts, context=context, utils=utils, whitelist=['boto_lambda'])
salt_states = salt.loader.states(opts=opts, functions=funcs, utils=utils, whitelist=['boto_lambda'], serializers=serializers)


def _has_required_boto():
    '''
    Returns True/False boolean depending on if Boto is installed and correct
    version.
    '''
    if not HAS_BOTO:
        return False
    elif LooseVersion(boto3.__version__) < LooseVersion(required_boto3_version):
        return False
    else:
        return True


class BotoLambdaStateTestCaseBase(TestCase):
    conn = None

    # Set up MagicMock to replace the boto3 session
    def setUp(self):
        context.clear()
        # connections keep getting cached from prior tests, can't find the
        # correct context object to clear it. So randomize the cache key, to prevent any
        # cache hits
        conn_parameters['key'] = ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(50))

        self.patcher = patch('boto3.session.Session')
        self.addCleanup(self.patcher.stop)
        mock_session = self.patcher.start()

        session_instance = mock_session.return_value
        self.conn = MagicMock()
        session_instance.client.return_value = self.conn


@skipIf(HAS_BOTO is False, 'The boto module must be installed.')
@skipIf(_has_required_boto() is False, 'The boto3 module must be greater than'
                                       ' or equal to version {0}'
        .format(required_boto3_version))
@skipIf(NO_MOCK, NO_MOCK_REASON)
class BotoLambdaFunctionTestCase(BotoLambdaStateTestCaseBase, BotoLambdaTestCaseMixin):
    '''
    TestCase for salt.modules.boto_lambda state.module
    '''

    def test_present_when_function_does_not_exist(self):
        '''
        Tests present on a function that does not exist.
        '''
        self.conn.list_functions.side_effect = [{'Functions': []}, {'Functions': [function_ret]}]
        self.conn.create_function.return_value = function_ret
        with patch.dict(funcs, {'boto_iam.get_account_id': MagicMock(return_value='1234')}):
            with TempZipFile() as zipfile:
                result = salt_states['boto_lambda.function_present'](
                         'function present',
                         FunctionName=function_ret['FunctionName'],
                         Runtime=function_ret['Runtime'],
                         Role=function_ret['Role'],
                         Handler=function_ret['Handler'],
                         ZipFile=zipfile)

        self.assertTrue(result['result'])
        self.assertEqual(result['changes']['new']['function']['FunctionName'],
                         function_ret['FunctionName'])

    def test_present_when_function_exists(self):
        self.conn.list_functions.return_value = {'Functions': [function_ret]}
        self.conn.update_function_code.return_value = function_ret

        with patch.dict(funcs, {'boto_iam.get_account_id': MagicMock(return_value='1234')}):
            with TempZipFile() as zipfile:
                with patch('hashlib.sha256') as sha256:
                    with patch('os.path.getsize', return_value=199):
                        sha = sha256()
                        digest = sha.digest()
                        encoded = sha.encode()
                        encoded.strip.return_value = function_ret['CodeSha256']
                        result = salt_states['boto_lambda.function_present'](
                                     'function present',
                                     FunctionName=function_ret['FunctionName'],
                                     Runtime=function_ret['Runtime'],
                                     Role=function_ret['Role'],
                                     Handler=function_ret['Handler'],
                                     ZipFile=zipfile,
                                     Description=function_ret['Description'],
                                     Timeout=function_ret['Timeout'])
        self.assertTrue(result['result'])
        self.assertEqual(result['changes'], {})

    def test_present_with_failure(self):
        self.conn.list_functions.side_effect = [{'Functions': []}, {'Functions': [function_ret]}]
        self.conn.create_function.side_effect = ClientError(error_content, 'create_function')
        with patch.dict(funcs, {'boto_iam.get_account_id': MagicMock(return_value='1234')}):
            with TempZipFile() as zipfile:
                with patch('hashlib.sha256') as sha256:
                    with patch('os.path.getsize', return_value=199):
                        sha = sha256()
                        digest = sha.digest()
                        encoded = sha.encode()
                        encoded.strip.return_value = function_ret['CodeSha256']
                        result = salt_states['boto_lambda.function_present'](
                                     'function present',
                                     FunctionName=function_ret['FunctionName'],
                                     Runtime=function_ret['Runtime'],
                                     Role=function_ret['Role'],
                                     Handler=function_ret['Handler'],
                                     ZipFile=zipfile,
                                     Description=function_ret['Description'],
                                     Timeout=function_ret['Timeout'])
        self.assertFalse(result['result'])
        self.assertTrue('An error occurred' in result['comment'])

    def test_absent_when_function_does_not_exist(self):
        '''
        Tests absent on a function that does not exist.
        '''
        self.conn.list_functions.return_value = {'Functions': [function_ret]}
        result = salt_states['boto_lambda.function_absent']('test', 'myfunc')
        self.assertTrue(result['result'])
        self.assertEqual(result['changes'], {})

    def test_absent_when_function_exists(self):
        self.conn.list_functions.return_value = {'Functions': [function_ret]}
        result = salt_states['boto_lambda.function_absent']('test', function_ret['FunctionName'])
        self.assertTrue(result['result'])
        self.assertEqual(result['changes']['new']['function'], None)

    def test_absent_with_failure(self):
        self.conn.list_functions.return_value = {'Functions': [function_ret]}
        self.conn.delete_function.side_effect = ClientError(error_content, 'delete_function')
        result = salt_states['boto_lambda.function_absent']('test', function_ret['FunctionName'])
        self.assertFalse(result['result'])
        self.assertTrue('An error occurred' in result['comment'])

    def test_present_when_function_exists_and_permissions(self):
        self.conn.list_functions.return_value = {'Functions': [function_ret]}
        self.conn.update_function_code.return_value = function_ret
        self.conn.get_policy.return_value = {
          "Policy": json.dumps(
            {"Version": "2012-10-17",
             "Statement": [
               {"Condition":
                {"ArnLike": {"AWS:SourceArn": "arn:aws:events:us-east-1:9999999999:rule/fooo"}},
                "Action": "lambda:InvokeFunction",
                "Resource": "arn:aws:lambda:us-east-1:999999999999:function:testfunction",
                "Effect": "Allow",
                "Principal": {"Service": "events.amazonaws.com"},
                "Sid": "AWSEvents_foo-bar999999999999"}],
             "Id": "default"})
        }

        with patch.dict(funcs, {'boto_iam.get_account_id': MagicMock(return_value='1234')}):
            with TempZipFile() as zipfile:
                with patch('hashlib.sha256') as sha256:
                    with patch('os.path.getsize', return_value=199):
                        sha = sha256()
                        digest = sha.digest()
                        encoded = sha.encode()
                        encoded.strip.return_value = function_ret['CodeSha256']
                        result = salt_states['boto_lambda.function_present'](
                                     'function present',
                                     FunctionName=function_ret['FunctionName'],
                                     Runtime=function_ret['Runtime'],
                                     Role=function_ret['Role'],
                                     Handler=function_ret['Handler'],
                                     ZipFile=zipfile,
                                     Description=function_ret['Description'],
                                     Timeout=function_ret['Timeout'])
        self.assertTrue(result['result'])
        self.assertEqual(result['changes'], {
          'old': {
            'Permissions': {
              'AWSEvents_foo-bar999999999999':
              {'Action': 'lambda:InvokeFunction',
               'Principal': 'events.amazonaws.com',
               'SourceArn': 'arn:aws:events:us-east-1:9999999999:rule/fooo'}}},
          'new': {
            'Permissions': {
              'AWSEvents_foo-bar999999999999': {}}}})

    def test_present_when_function_exists_and_permissions_noassert(self):
        self.conn.list_functions.return_value = {'Functions': [function_ret]}
        self.conn.update_function_code.return_value = function_ret
        self.conn.get_policy.return_value = {
          "Policy": json.dumps(
            {"Version": "2012-10-17",
             "Statement": [
               {"Condition":
                {"ArnLike": {"AWS:SourceArn": "arn:aws:events:us-east-1:9999999999:rule/fooo"}},
                "Action": "lambda:InvokeFunction",
                "Resource": "arn:aws:lambda:us-east-1:999999999999:function:testfunction",
                "Effect": "Allow",
                "Principal": {"Service": "events.amazonaws.com"},
                "Sid": "AWSEvents_foo-bar999999999999"}],
             "Id": "default"})
        }

        with patch.dict(funcs, {'boto_iam.get_account_id': MagicMock(return_value='1234')}):
            with TempZipFile() as zipfile:
                with patch('hashlib.sha256') as sha256:
                    with patch('os.path.getsize', return_value=199):
                        sha = sha256()
                        digest = sha.digest()
                        encoded = sha.encode()
                        encoded.strip.return_value = function_ret['CodeSha256']
                        result = salt_states['boto_lambda.function_present'](
                                     'function present',
                                     FunctionName=function_ret['FunctionName'],
                                     Runtime=function_ret['Runtime'],
                                     Role=function_ret['Role'],
                                     Handler=function_ret['Handler'],
                                     ZipFile=zipfile,
                                     Description=function_ret['Description'],
                                     Timeout=function_ret['Timeout'])
        #self.assertTrue(result['result'])
        #self.assertEqual(result['changes'], {
        #  'old': {
        #    'Permissions': {
        #      'AWSEvents_foo-bar999999999999':
        #      {'Action': 'lambda:InvokeFunction',
        #       'Principal': 'events.amazonaws.com',
        #       'SourceArn': 'arn:aws:events:us-east-1:9999999999:rule/fooo'}}},
        #  'new': {
        #    'Permissions': {
        #      'AWSEvents_foo-bar999999999999': {}}}})



@skipIf(HAS_BOTO is False, 'The boto module must be installed.')
@skipIf(_has_required_boto() is False, 'The boto3 module must be greater than'
                                       ' or equal to version {0}'
        .format(required_boto3_version))
@skipIf(NO_MOCK, NO_MOCK_REASON)
class BotoLambdaAliasTestCase(BotoLambdaStateTestCaseBase, BotoLambdaTestCaseMixin):
    '''
    TestCase for salt.modules.boto_lambda state.module aliases
    '''

    def test_present_when_alias_does_not_exist(self):
        '''
        Tests present on a alias that does not exist.
        '''
        self.conn.list_aliases.side_effect = [{'Aliases': []}, {'Aliases': [alias_ret]}]
        self.conn.create_alias.return_value = alias_ret
        result = salt_states['boto_lambda.alias_present'](
                         'alias present',
                         FunctionName='testfunc',
                         Name=alias_ret['Name'],
                         FunctionVersion=alias_ret['FunctionVersion'])

        self.assertTrue(result['result'])
        self.assertEqual(result['changes']['new']['alias']['Name'],
                         alias_ret['Name'])

    def test_present_when_alias_exists(self):
        self.conn.list_aliases.return_value = {'Aliases': [alias_ret]}
        self.conn.create_alias.return_value = alias_ret
        result = salt_states['boto_lambda.alias_present'](
                         'alias present',
                         FunctionName='testfunc',
                         Name=alias_ret['Name'],
                         FunctionVersion=alias_ret['FunctionVersion'],
                         Description=alias_ret['Description'])
        self.assertTrue(result['result'])
        self.assertEqual(result['changes'], {})

    def test_present_with_failure(self):
        self.conn.list_aliases.side_effect = [{'Aliases': []}, {'Aliases': [alias_ret]}]
        self.conn.create_alias.side_effect = ClientError(error_content, 'create_alias')
        result = salt_states['boto_lambda.alias_present'](
                         'alias present',
                         FunctionName='testfunc',
                         Name=alias_ret['Name'],
                         FunctionVersion=alias_ret['FunctionVersion'])
        self.assertFalse(result['result'])
        self.assertTrue('An error occurred' in result['comment'])

    def test_absent_when_alias_does_not_exist(self):
        '''
        Tests absent on a alias that does not exist.
        '''
        self.conn.list_aliases.return_value = {'Aliases': [alias_ret]}
        result = salt_states['boto_lambda.alias_absent'](
                         'alias absent',
                         FunctionName='testfunc',
                         Name='myalias')
        self.assertTrue(result['result'])
        self.assertEqual(result['changes'], {})

    def test_absent_when_alias_exists(self):
        self.conn.list_aliases.return_value = {'Aliases': [alias_ret]}
        result = salt_states['boto_lambda.alias_absent'](
                         'alias absent',
                         FunctionName='testfunc',
                         Name=alias_ret['Name'])
        self.assertTrue(result['result'])
        self.assertEqual(result['changes']['new']['alias'], None)

    def test_absent_with_failure(self):
        self.conn.list_aliases.return_value = {'Aliases': [alias_ret]}
        self.conn.delete_alias.side_effect = ClientError(error_content, 'delete_alias')
        result = salt_states['boto_lambda.alias_absent'](
                         'alias absent',
                         FunctionName='testfunc',
                         Name=alias_ret['Name'])
        self.assertFalse(result['result'])
        self.assertTrue('An error occurred' in result['comment'])


@skipIf(HAS_BOTO is False, 'The boto module must be installed.')
@skipIf(_has_required_boto() is False, 'The boto3 module must be greater than'
                                       ' or equal to version {0}'
        .format(required_boto3_version))
@skipIf(NO_MOCK, NO_MOCK_REASON)
class BotoLambdaEventSourceMappingTestCase(BotoLambdaStateTestCaseBase, BotoLambdaTestCaseMixin):
    '''
    TestCase for salt.modules.boto_lambda state.module event_source_mappings
    '''

    def test_present_when_event_source_mapping_does_not_exist(self):
        '''
        Tests present on a event_source_mapping that does not exist.
        '''
        self.conn.list_event_source_mappings.side_effect = [{'EventSourceMappings': []}, {'EventSourceMappings': [event_source_mapping_ret]}]
        self.conn.get_event_source_mapping.return_value = event_source_mapping_ret
        self.conn.create_event_source_mapping.return_value = event_source_mapping_ret
        result = salt_states['boto_lambda.event_source_mapping_present'](
                         'event source mapping present',
                         EventSourceArn=event_source_mapping_ret['EventSourceArn'],
                         FunctionName='myfunc',
                         StartingPosition='LATEST')

        self.assertTrue(result['result'])
        self.assertEqual(result['changes']['new']['event_source_mapping']['UUID'],
                         event_source_mapping_ret['UUID'])

    def test_present_when_event_source_mapping_exists(self):
        self.conn.list_event_source_mappings.return_value = {'EventSourceMappings': [event_source_mapping_ret]}
        self.conn.get_event_source_mapping.return_value = event_source_mapping_ret
        self.conn.create_event_source_mapping.return_value = event_source_mapping_ret
        result = salt_states['boto_lambda.event_source_mapping_present'](
                         'event source mapping present',
                         EventSourceArn=event_source_mapping_ret['EventSourceArn'],
                         FunctionName=event_source_mapping_ret['FunctionArn'],
                         StartingPosition='LATEST',
                         BatchSize=event_source_mapping_ret['BatchSize'])
        self.assertTrue(result['result'])
        self.assertEqual(result['changes'], {})

    def test_present_with_failure(self):
        self.conn.list_event_source_mappings.side_effect = [{'EventSourceMappings': []}, {'EventSourceMappings': [event_source_mapping_ret]}]
        self.conn.get_event_source_mapping.return_value = event_source_mapping_ret
        self.conn.create_event_source_mapping.side_effect = ClientError(error_content, 'create_event_source_mapping')
        result = salt_states['boto_lambda.event_source_mapping_present'](
                         'event source mapping present',
                         EventSourceArn=event_source_mapping_ret['EventSourceArn'],
                         FunctionName=event_source_mapping_ret['FunctionArn'],
                         StartingPosition='LATEST',
                         BatchSize=event_source_mapping_ret['BatchSize'])
        self.assertFalse(result['result'])
        self.assertTrue('An error occurred' in result['comment'])

    def test_absent_when_event_source_mapping_does_not_exist(self):
        '''
        Tests absent on a event_source_mapping that does not exist.
        '''
        self.conn.list_event_source_mappings.return_value = {'EventSourceMappings': []}
        result = salt_states['boto_lambda.event_source_mapping_absent'](
                         'event source mapping absent',
                         EventSourceArn=event_source_mapping_ret['EventSourceArn'],
                         FunctionName='myfunc')
        self.assertTrue(result['result'])
        self.assertEqual(result['changes'], {})

    def test_absent_when_event_source_mapping_exists(self):
        self.conn.list_event_source_mappings.return_value = {'EventSourceMappings': [event_source_mapping_ret]}
        self.conn.get_event_source_mapping.return_value = event_source_mapping_ret
        result = salt_states['boto_lambda.event_source_mapping_absent'](
                         'event source mapping absent',
                         EventSourceArn=event_source_mapping_ret['EventSourceArn'],
                         FunctionName='myfunc')
        self.assertTrue(result['result'])
        self.assertEqual(result['changes']['new']['event_source_mapping'], None)

    def test_absent_with_failure(self):
        self.conn.list_event_source_mappings.return_value = {'EventSourceMappings': [event_source_mapping_ret]}
        self.conn.get_event_source_mapping.return_value = event_source_mapping_ret
        self.conn.delete_event_source_mapping.side_effect = ClientError(error_content, 'delete_event_source_mapping')
        result = salt_states['boto_lambda.event_source_mapping_absent'](
                         'event source mapping absent',
                         EventSourceArn=event_source_mapping_ret['EventSourceArn'],
                         FunctionName='myfunc')
        self.assertFalse(result['result'])
        self.assertTrue('An error occurred' in result['comment'])
